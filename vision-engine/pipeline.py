import os
import sys
import json
import time
import urllib.request
import cv2
import numpy as np
from typing import Dict, List, Optional, Tuple, Any

from capture import ROICaptureManager
from detector import ChangeGatedDetector
from matcher import RosterMatcher
from consensus import TemporalConsensusEngine

try:
  from rapidocr_onnxruntime import RapidOCR
except ImportError:
  RapidOCR = None

class LiveKillDetectionPipeline:
  """
  End-to-End 6-Stage Video Detection Pipeline (plan.md & tech_stack.md):
  Stage 1: Closed-set Roster Manifest & Skeleton Normalization (48 players, 12 teams)
  Stage 2: High-Signal Video Ingestion & Coordinate Blueprint Masking
  Stage 3: Change-Gated Row Parsing, SSIM diff, and Action Icon Detection
  Stage 4: OCR & Roster-Constrained Fuzzy Matching (3-tier confidence routing)
  Stage 5: Temporal Consensus (2-of-3 frames) & 15s Revival-Aware Deduplication
  Stage 6: Real-time Event Emission to Node.js / SQLite Leaderboard
  """
  def __init__(
    self,
    roster_path: Optional[str] = None,
    roi_preset_path: Optional[str] = None,
    server_url: str = "http://localhost:3001",
    resolution: str = "1080p",
    cooldown_seconds: float = 15.0,
    diff_threshold: float = 3.5
  ):
    base_dir = os.path.dirname(__file__)
    if roster_path is None:
      roster_path = os.path.join(base_dir, '..', 'config', 'sample_roster.json')
    if roi_preset_path is None:
      roi_preset_path = os.path.join(base_dir, '..', 'config', 'roi_presets.json')

    # Stage 1: Load Roster Manifest (Ground Truth)
    with open(roster_path, 'r', encoding='utf-8') as f:
      self.roster = json.load(f)
    self.match_id = self.roster.get('matchId', 'ffws-2025-gf-match-4')

    # Initialize Components
    self.server_url = server_url
    self.matcher = RosterMatcher(self.roster)
    self.capture_mgr = ROICaptureManager(roi_preset_path, resolution=resolution)
    self.detector = ChangeGatedDetector(diff_threshold=diff_threshold)
    self.consensus = TemporalConsensusEngine(cooldown_seconds=cooldown_seconds)

    # Initialize ONNX RapidOCR
    if RapidOCR is not None:
      self.ocr = RapidOCR()
    else:
      self.ocr = None
      print("[Warning] RapidOCR not installed, using mock text reader.")

    # Telemetry State
    self.frames_processed = 0
    self.static_frames_skipped = 0
    self.kills_detected = 0
    self.last_alive_count = 48
    self.last_committed_kills = []

  def check_game_state_guard(self, frame: np.ndarray) -> bool:
    """Stage 2 ROI C: Checks if game is in replay, lobby, or transition screen"""
    guard_roi = self.capture_mgr.crop_roi(frame, 'game_state_guard')
    if guard_roi is None or guard_roi.size == 0:
      return True

    std_val = float(np.std(guard_roi))
    if std_val < 3.0:
      return False  # Replay slate or transition stinger

    return True

  def check_alive_counter(self, frame: np.ndarray) -> int:
    """Stage 2 ROI B: Reads global Alive counter as independent sanity check"""
    alive_roi = self.capture_mgr.crop_roi(frame, 'alive_counter')
    if alive_roi is None or alive_roi.size == 0 or self.ocr is None:
      return self.last_alive_count

    try:
      results, _ = self.ocr(alive_roi)
      if results:
        full_text = " ".join([item[1] for item in results])
        digits = "".join([c for c in full_text if c.isdigit()])
        if digits and 1 <= int(digits) <= 48:
          self.last_alive_count = int(digits)
    except Exception:
      pass

    return self.last_alive_count

  def emit_event_to_backend(self, event_data: dict) -> dict:
    """Stage 6: Emits verified kill event to Event-Sourced Ledger Backend"""
    try:
      payload = json.dumps(event_data).encode('utf-8')
      url = f"{self.server_url}/api/kill"
      req = urllib.request.Request(
        url,
        data=payload,
        headers={'Content-Type': 'application/json'},
        method='POST'
      )
      with urllib.request.urlopen(req, timeout=1.5) as resp:
        return json.loads(resp.read().decode('utf-8'))
    except Exception as e:
      return {'status': 'OFFLINE_BUFFERED', 'error': str(e)}

  def process_frame(self, frame: np.ndarray, timestamp_sec: float = 0.0) -> Dict[str, Any]:
    """
    Full frame processing loop called on every sampled frame (4-5 FPS):
    - Change gating via pixel difference
    - RapidOCR text detection and Y-axis row clustering
    - Knockdown filtering
    - Roster normalization and fuzzy matching
    - 2-of-3 consensus voting & 15s revival cooldown
    - Real-time emission to leaderboard backend
    """
    self.frames_processed += 1
    events_found = []

    # 1. Game State Guard (ROI C)
    if not self.check_game_state_guard(frame):
      return {
        'status': 'PAUSED_GUARD_ACTIVE',
        'events': [],
        'frames_processed': self.frames_processed
      }

    # 2. Global Alive Counter (ROI B)
    alive_count = self.check_alive_counter(frame)

    # 3. Killfeed ROI Extraction & Change Gating (ROI A)
    killfeed_roi = self.capture_mgr.crop_roi(frame, 'killfeed')
    if killfeed_roi is None or killfeed_roi.size == 0:
      return {
        'status': 'INVALID_FRAME',
        'events': [],
        'frames_processed': self.frames_processed
      }

    # Pixel Diff Gate: Skip OCR if feed is static (saves 70-85% CPU)
    if not self.detector.has_killfeed_changed(killfeed_roi):
      self.static_frames_skipped += 1
      return {
        'status': 'STATIC_SKIPPED',
        'events': [],
        'frames_processed': self.frames_processed,
        'static_frames_skipped': self.static_frames_skipped
      }

    # 4. RapidOCR Detection on Active Killfeed Zone
    if self.ocr is None:
      return {'status': 'OCR_UNAVAILABLE', 'events': []}

    ocr_results, _ = self.ocr(killfeed_roi)
    if not ocr_results:
      return {
        'status': 'NO_TEXT_IN_FEED',
        'events': [],
        'frames_processed': self.frames_processed
      }

    # 5. Cluster text boxes into horizontal notification rows by Y-center
    rows: Dict[float, List[Dict[str, Any]]] = {}
    for box, text, score in ocr_results:
      text = text.strip()
      if not text or 'ALIVE' in text.upper():
        continue

      y_center = (box[0][1] + box[2][1]) / 2.0
      x_center = (box[0][0] + box[2][0]) / 2.0

      matched_row_y = None
      for ry in rows:
        if abs(ry - y_center) < 22:
          matched_row_y = ry
          break

      if matched_row_y is None:
        matched_row_y = y_center
        rows[matched_row_y] = []

      rows[matched_row_y].append({
        'text': text,
        'x': x_center,
        'score': float(score) if score is not None else 1.0
      })

    # 6. Parse Each Row: [Killer] [Weapon / Action Icon] [Victim]
    for ry, tokens in sorted(rows.items()):
      tokens.sort(key=lambda t: t['x'])
      if len(tokens) < 2:
        continue

      # Check for Knockdown indicator in any token
      is_knockdown = any(k in t['text'].upper() for t in tokens for k in ['KNOCK', 'DOWN', 'KNOCKED', 'BLEED'])
      if is_knockdown:
        # Stage 3 requirement: Immediately discard knockdowns before committing kill
        continue

      raw_killer = tokens[0]['text']
      raw_victim = tokens[-1]['text']
      weapon = tokens[1]['text'] if len(tokens) >= 3 else 'WEAPON'

      # Check for environmental kill (Zone / Fall / Red Zone)
      is_env_kill = any(w in raw_killer.lower() for w in ['zone', 'fall', 'playzone', 'eliminated', 'red zone'])

      matched_killer = None
      conf_killer = 1.0

      if not is_env_kill:
        matched_killer, conf_killer, _ = self.matcher.match_ocr_text(raw_killer)

      matched_victim, conf_victim, _ = self.matcher.match_ocr_text(raw_victim)

      if not matched_victim:
        continue

      # Prevent self-kill from inflating squad kill points
      if matched_killer and matched_killer['team_id'] == matched_victim['team_id']:
        continue

      overall_confidence = round((conf_killer if matched_killer else 1.0) * conf_victim, 2)
      killer_id = matched_killer['id'] if matched_killer else None
      victim_id = matched_victim['id']

      # Stage 5: Temporal Consensus & Revival-Aware Cooldown
      is_confirmed, consensus_reason = self.consensus.record_observation(
        killer_id=killer_id,
        victim_id=victim_id,
        confidence=overall_confidence
      )

      if is_confirmed:
        self.kills_detected += 1
        event_payload = {
          'matchId': self.match_id,
          'killerTeamId': matched_killer['team_id'] if matched_killer else None,
          'killerPlayerId': killer_id,
          'victimTeamId': matched_victim['team_id'],
          'victimPlayerId': victim_id,
          'weapon': weapon,
          'confidence': overall_confidence,
          'source': 'VISION_AI',
          'status': 'ACTIVE' if overall_confidence >= 0.85 else 'PENDING_REVIEW'
        }

        # Stage 6: Real-Time Event Emission to Leaderboard Backend
        server_res = self.emit_event_to_backend(event_payload)
        event_payload['server_response'] = server_res
        events_found.append(event_payload)
        self.last_committed_kills.append(event_payload)

    return {
      'status': 'ACTIVE_PROCESSED',
      'events': events_found,
      'alive_count': alive_count,
      'active_rows_count': len(rows),
      'frames_processed': self.frames_processed,
      'static_frames_skipped': self.static_frames_skipped,
      'kills_detected': self.kills_detected
    }
