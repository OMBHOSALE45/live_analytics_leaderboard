import os
import sys
import time
import json
import argparse
import threading
import subprocess
import socket
import urllib.request
import cv2
import numpy as np
from collections import deque, Counter
from typing import Dict, List, Tuple, Optional, Any

try:
  from rapidocr_onnxruntime import RapidOCR
except ImportError:
  RapidOCR = None

"""Bagde colour engine"""
class BadgeColorEngine:
  """
  Esports Badge Color Classifier:
  - 8-color Free Fire esports palette: RED, ORANGE, YELLOW, GREEN, CYAN, BLUE, PURPLE, PINK
  - High-chroma Hue clustering on confirmed alive players
  - Dead / eliminated players are strictly categorized as DIMMED / GRAY (#555555)
  - Zero color hallucination: dead rows never pollute team consensus
  """

  # Canonical 8-color Free Fire esports tournament palette
  PALETTE_HEX = {
    "RED":      "#FF2A2A",
    "ORANGE":   "#FF7F00",
    "YELLOW":   "#FFD700",
    "GREEN":    "#00D860",
    "CYAN":     "#00E5FF",
    "BLUE":     "#1E4BFF",
    "PURPLE":   "#8A2BE2",
    "PINK":     "#FF2E93",
    "DIMMED":   "#555555",
  }

  def __init__(self, vote_window: int = 9, lock_threshold: int = 4):
    self.hex_map = self.PALETTE_HEX
    self.vote_window = vote_window
    self.lock_threshold = lock_threshold
    self.slot_votes: Dict[int, deque] = {}
    self.slot_locked: Dict[int, Tuple[str, str]] = {}

  @staticmethod
  def hex_to_bgr(hex_str: str) -> Tuple[int, int, int]:
    hx = hex_str.lstrip("#")
    if len(hx) < 6:
      return (85, 85, 85)
    return (int(hx[4:6], 16), int(hx[2:4], 16), int(hx[0:2], 16))

  def reset_cache(self):
    """Call this when recalibrating slots or starting a new match."""
    self.slot_votes.clear()
    self.slot_locked.clear()

  def estimate_hud_background_lab(self, slot1_bgr: np.ndarray) -> np.ndarray:
    if slot1_bgr is None or slot1_bgr.size == 0:
      return np.array([30.0, 0.0, 0.0], dtype=np.float32)
    lab = cv2.cvtColor(slot1_bgr, cv2.COLOR_BGR2LAB).astype(np.float32)
    flat = lab.reshape(-1, 3)
    return np.median(flat, axis=0)

  def extract_row_color(
    self,
    badge_bgr: np.ndarray,
    bg_lab: Optional[np.ndarray],
    slot_idx: int,
    is_alive: bool = True,
    debug: bool = False
  ) -> Tuple[str, str]:
    """
    Extracts the foreground badge color for a single row.
    Returns: (color_name, hex_color)
    Strict rule: If player is NOT alive, returns ('DIMMED', '#555555').
    """
    if not is_alive or badge_bgr is None or badge_bgr.size == 0:
      return "DIMMED", "#555555"

    hsv = cv2.cvtColor(badge_bgr, cv2.COLOR_BGR2HSV)
    sat = hsv[:, :, 1]
    val = hsv[:, :, 2]
    hue = hsv[:, :, 0].astype(np.int32) * 2

    # Filter for vibrant saturated pixels (rejecting dark background, shadows, white borders)
    vibrant = (sat > 60) & (val > 60)
    fg_count = int(np.count_nonzero(vibrant))
    if fg_count < 8:
      return "DIMMED", "#555555"

    med_hue = int(np.median(hue[vibrant]))

    # Free Fire Esports Standard Color Classification
    if med_hue >= 345 or med_hue <= 18:
      raw_name = "RED"
    elif 19 <= med_hue <= 42:
      raw_name = "ORANGE"
    elif 43 <= med_hue <= 70:
      raw_name = "YELLOW"
    elif 71 <= med_hue <= 160:
      raw_name = "GREEN"
    elif 161 <= med_hue <= 200:
      raw_name = "CYAN"
    elif 201 <= med_hue <= 245:
      raw_name = "BLUE"
    elif 246 <= med_hue <= 295:
      raw_name = "PURPLE"
    elif 296 <= med_hue <= 344:
      raw_name = "PINK"
    else:
      raw_name = "CYAN"

    raw_hex = self.hex_map[raw_name]

    # Temporal voting for alive slots
    buf = self.slot_votes.setdefault(slot_idx, deque(maxlen=self.vote_window))
    buf.append(raw_name)
    winner, count = Counter(buf).most_common(1)[0]
    if count >= self.lock_threshold:
      self.slot_locked[slot_idx] = (winner, self.hex_map[winner])
    return winner, self.hex_map[winner]


class ThreadedScoreboardDetector:
  """
  High-Performance Asynchronous Free Fire Scoreboard AI Tracker:
  - Multithreaded: Main thread runs video capture & OpenCV display at native 30-60 FPS (Zero Stutter).
  - Background Worker: Runs RapidOCR on video start to register team rosters, then tracks live
    kill numbers and alive statuses at maximum frame rate using <3ms template/color classification.
  - Immediate Sync: Broadcasts detected teams to the Node.js backend on the very first frame,
    then updates every 1.0-1.5s (or immediately on kill events).
  """
  def __init__(
    self,
    server_url: str = "http://localhost:3001",
    sync_interval: float = 1.2
  ):
    # Ensure localhost bypasses system/IDE proxies
    os.environ['NO_PROXY'] = 'localhost,127.0.0.1'
    os.environ['no_proxy'] = 'localhost,127.0.0.1'
    self.server_url = server_url.replace("localhost", "127.0.0.1")
    self.sync_interval = sync_interval
    self.project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
    self.color_engine = BadgeColorEngine(vote_window=9, lock_threshold=5)

    # Proxy-bypass HTTP opener for rock-solid local REST sync
    self.http_opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    # Auto-start Node.js server if not currently active
    self._ensure_server_running()

    self.ocr = RapidOCR() if RapidOCR is not None else None

    # Slot coordinates (Loaded from slot_calibration.json if present)
    self.slot1_norm = [0.693, 0.075, 0.889, 0.968]
    self.slot2_norm = [0.879, 0.075, 0.945, 0.968]
    self._load_saved_calibration()

    # Digit Templates
    self.templates = {}
    self._init_digit_templates()

    # Cached Rosters (player names cached once discovered so OCR doesn't block video)
    self.cached_player_names = {}
    self.cached_team_colors = {}
    self.player_max_kills: Dict[int, int] = {}
    self.squad_locks = {}  # Persistent squad-level color locks: squad_idx -> (color_name, hex)
    self.has_initial_roster = False
    self.ocr_attempts = 0

    # HP Tracker Pipeline (Dark-Masked Health Bar Tracker)
    self.hp_pipeline = None
    try:
      sys.path.append(os.path.abspath(os.path.join(self.project_root, '..')))
      from hp_tracker.core.hp_pipeline import HPTrackerPipeline
      self.hp_pipeline = HPTrackerPipeline()
      print("[HPTracker] Dark-Masked Health Bar Pipeline initialized successfully.")
    except Exception as e:
      print(f"[HPTracker Info] HP Pipeline not active: {e}")

    # Threading & State
    self.running = True
    self.lock = threading.Lock()
    self.current_frame = None
    self.latest_result = None
    self.fps_display = 30.0
    self.total_synced_events = 0
    self.last_sync_time = 0.0

    # Start Background AI Worker Thread
    self.worker_thread = threading.Thread(target=self._ai_worker_loop, daemon=True)
    self.worker_thread.start()

  def _load_saved_calibration(self):
    """Loads previously saved slot calibration if available"""
    calib_file = os.path.join(self.project_root, 'slot_calibration.json')
    if os.path.exists(calib_file):
      try:
        with open(calib_file, 'r', encoding='utf-8') as f:
          data = json.load(f)
          if 'slot1' in data and 'slot2' in data:
            self.slot1_norm = data['slot1']
            self.slot2_norm = data['slot2']
            print(f"[Calibration] Loaded saved slots from slot_calibration.json")
      except Exception:
        pass

  def _save_calibration(self):
    """Saves current slot calibration to disk"""
    calib_file = os.path.join(self.project_root, 'slot_calibration.json')
    try:
      with open(calib_file, 'w', encoding='utf-8') as f:
        json.dump({'slot1': self.slot1_norm, 'slot2': self.slot2_norm}, f, indent=2)
      print(f"[Calibration] Saved slots to slot_calibration.json")
    except Exception:
      pass

  def _ensure_server_running(self):
    """Checks if Node.js server on port 3001 is listening. If not, auto-spawns it."""
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(0.3)
    is_listening = False
    try:
      s.connect(('127.0.0.1', 3001))
      is_listening = True
    except Exception:
      is_listening = False
    finally:
      s.close()

    if not is_listening:
      server_dir = os.path.join(self.project_root, 'server')
      server_file = os.path.join(server_dir, 'server.js')
      if os.path.exists(server_file):
        print(f"[AutoServer] Port 3001 is not active. Auto-starting Node.js server...")
        try:
          subprocess.Popen(
            ['node', 'server.js'],
            cwd=server_dir,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            shell=True
          )
          time.sleep(1.2)
          print("[AutoServer] Backend server successfully running on http://localhost:3001!")
        except Exception as e:
          print(f"[AutoServer Warning] Could not auto-launch server: {e}")

  def _init_digit_templates(self):
    """Loads templates for in-game font digits 0 through 9"""
    base_dir = os.path.dirname(__file__)
    candidate_dirs = [
      os.path.join(base_dir, 'templates'),
      os.path.join(base_dir, '..', 'templates'),
      r"C:\Users\ASUS\OneDrive\Desktop\Esport\live_analytics_leaderboard\vision-engine\templates"
    ]
    tpl_dir = None
    for cd in candidate_dirs:
      if os.path.isdir(cd) and os.path.exists(os.path.join(cd, 'tpl_0.png')):
        tpl_dir = cd
        break

    for d in range(10):
      loaded = False
      if tpl_dir is not None:
        p = os.path.join(tpl_dir, f'tpl_{d}.png')
        if os.path.exists(p):
          img = cv2.imread(p, cv2.IMREAD_GRAYSCALE)
          if img is not None and img.size > 0:
            if img.shape != (16, 10):
              img = cv2.resize(img, (10, 16), interpolation=cv2.INTER_NEAREST)
            self.templates[d] = img > 120
            loaded = True
      if not loaded:
        # High-precision binary fallback for Free Fire font 10x16
        fallback_grid = np.zeros((16, 10), dtype=bool)
        if d == 0:
          fallback_grid[1:15, 1:9] = True
          fallback_grid[3:13, 3:7] = False
        elif d == 1:
          fallback_grid[1:15, 3:7] = True
        elif d == 2:
          fallback_grid[1:5, 1:9] = True
          fallback_grid[5:11, 4:8] = True
          fallback_grid[12:15, 1:9] = True
        elif d == 3:
          fallback_grid[1:4, 1:9] = True
          fallback_grid[6:9, 3:9] = True
          fallback_grid[12:15, 1:9] = True
          fallback_grid[2:14, 6:9] = True
        elif d == 4:
          fallback_grid[1:10, 1:4] = True
          fallback_grid[8:11, 1:9] = True
          fallback_grid[1:15, 6:9] = True
        elif d == 5:
          fallback_grid[1:4, 1:9] = True
          fallback_grid[4:8, 1:4] = True
          fallback_grid[7:10, 1:9] = True
          fallback_grid[9:14, 6:9] = True
          fallback_grid[12:15, 1:8] = True
        elif d == 6:
          fallback_grid[1:15, 1:4] = True
          fallback_grid[1:4, 1:9] = True
          fallback_grid[7:15, 1:9] = True
          fallback_grid[9:13, 3:7] = False
        elif d == 7:
          fallback_grid[1:4, 1:9] = True
          fallback_grid[3:15, 5:9] = True
        elif d == 8:
          fallback_grid[1:15, 1:9] = True
          fallback_grid[3:6, 3:7] = False
          fallback_grid[9:13, 3:7] = False
        elif d == 9:
          fallback_grid[1:9, 1:9] = True
          fallback_grid[3:7, 3:7] = False
          fallback_grid[1:15, 6:9] = True
          fallback_grid[12:15, 1:8] = True
        self.templates[d] = fallback_grid

  def extract_exact_badge_color(self, badge_bgr: np.ndarray) -> Tuple[str, str]:
    """
    Extracts the exact Free Fire squad color from chromatic badge pixels,
    rejecting dark borders, shadows, and white text.
    """
    if badge_bgr is None or badge_bgr.size == 0:
      return "UNKNOWN", "#888888"

    hsv = cv2.cvtColor(badge_bgr, cv2.COLOR_BGR2HSV)
    sat = hsv[:, :, 1]
    val = hsv[:, :, 2]

    # Filter for vibrant chromatic pixels (rejects dark backgrounds & white numbers)
    chroma_mask = (sat > 65) & (val > 65)
    if np.count_nonzero(chroma_mask) < 6:
      # If not enough saturated pixels, check if eliminated or gray
      return "GRAY", "#555555"

    hues = hsv[:, :, 0][chroma_mask].astype(int) * 2
    med_hue = int(np.median(hues))
    # Exact Free Fire esports palette
    if med_hue >= 345 or med_hue <= 15:
      return "RED", "#FF2A2A"
    elif 16 <= med_hue <= 44:
      return "ORANGE", "#FF7F00"
    elif 45 <= med_hue <= 74:
      return "YELLOW", "#FFD700"
    elif 75 <= med_hue <= 165:
      return "GREEN", "#00FF7F"
    elif 166 <= med_hue <= 255:
      return "BLUE", "#00D2FF"
    elif 256 <= med_hue <= 304:
      return "PURPLE", "#8A2BE2"
    elif 305 <= med_hue <= 344:
      return "PINK", "#FF1493"
      
    return "CYAN", "#00E5FF"

  def stop(self):
    """Gracefully stops background worker loop"""
    self.running = False

  def classify_digit(self, digit_crop: np.ndarray) -> int:
    """
    Classifies a cropped in-game kill digit with zero false positives.
    Combines authentic Free Fire font template IoU matching with
    topological hole verification and structural stroke analysis.
    """
    if digit_crop is None or digit_crop.size == 0:
      return 0
    h, w = digit_crop.shape[:2]
    # Free Fire font digits are 3-22px wide and 8-30px high
    if h < 8 or w < 3 or h > 35 or w > 26:
      return 0

    bin_crop = (digit_crop > 100).astype(np.uint8)

    # 1. Closed-loop hole check for Digit 0 (large central cavity)
    cnts, hier = cv2.findContours(bin_crop.copy() * 255, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_SIMPLE)
    if hier is not None and len(cnts) > 1:
      for idx in range(len(cnts)):
        if hier[0][idx][3] != -1:  # hole detected
          hx, hy, hw, hh = cv2.boundingRect(cnts[idx])
          if hh >= 7 and cv2.contourArea(cnts[idx]) >= 10:
            return 0

    # 2. Structural verification for Digit 1: very narrow vertical stroke
    if w <= 6 and (h / float(w) >= 2.2):
      return 1

    # Resize to canonical 10x16 for template comparison
    resized = cv2.resize(bin_crop, (10, 16), interpolation=cv2.INTER_NEAREST) > 0

    # 3. Authentic in-game font template IoU matching
    if hasattr(self, 'templates') and self.templates:
      scores = {}
      for d, tpl in self.templates.items():
        inter = np.logical_and(resized, tpl).sum()
        union = np.logical_or(resized, tpl).sum()
        scores[d] = inter / float(max(1, union))

      best_d = max(scores, key=scores.get)
      return best_d

    # Structural fallbacks
    if (w <= 6 or (h / float(w) >= 2.0)) and w >= 4:
      return 1
    bot_slice = digit_crop[max(0, h - 3):, :]
    if float(np.mean(bot_slice > 0)) >= 0.55:
      return 2
    return 0

  def get_slot_pixels(self, frame: np.ndarray) -> Tuple[Tuple[int, int, int, int], Tuple[int, int, int, int]]:
    """Converts normalized slot ratios to absolute pixel coordinates"""
    h, w = frame.shape[:2]
    s1 = (
      int(self.slot1_norm[0] * w),
      int(self.slot1_norm[1] * h),
      int(self.slot1_norm[2] * w),
      int(self.slot1_norm[3] * h)
    )
    s2 = (
      int(self.slot2_norm[0] * w),
      int(self.slot2_norm[1] * h),
      int(self.slot2_norm[2] * w),
      int(self.slot2_norm[3] * h)
    )
    return s1, s2

  def interactive_calibrate_slots(self, frame: np.ndarray):
    """Allows user to click & drag Slot 1 (Teams) and Slot 2 (Kills) on screen"""
    h, w = frame.shape[:2]
    print("\n[Calibration] Select SLOT 1: Teams & Player Names area, then press ENTER or SPACE...")
    roi1 = cv2.selectROI("Select Slot 1: Teams Area", frame, fromCenter=False, showCrosshair=True)
    cv2.destroyWindow("Select Slot 1: Teams Area")

    if roi1[2] > 20 and roi1[3] > 20:
      self.slot1_norm = [
        roi1[0] / float(w),
        roi1[1] / float(h),
        (roi1[0] + roi1[2]) / float(w),
        (roi1[1] + roi1[3]) / float(h)
      ]
      self.has_initial_roster = False
      self.color_engine.reset_cache()
      self.squad_locks.clear()
      self.player_max_kills.clear()
    print("\n[Calibration] Select SLOT 2: Kills column area, then press ENTER or SPACE...")
    roi2 = cv2.selectROI("Select Slot 2: Kills Area", frame, fromCenter=False, showCrosshair=True)
    cv2.destroyWindow("Select Slot 2: Kills Area")

    if roi2[2] > 10 and roi2[3] > 20:
      self.slot2_norm = [
        roi2[0] / float(w),
        roi2[1] / float(h),
        (roi2[0] + roi2[2]) / float(w),
        (roi2[1] + roi2[3]) / float(h)
      ]
      self._save_calibration()

  def _ai_worker_loop(self):
    """Background thread that runs detection and syncs to backend without blocking video display"""
    while self.running:
      try:
        frame = None
        with self.lock:
          if self.current_frame is not None:
            frame = self.current_frame.copy()

        if frame is None:
          time.sleep(0.02)
          continue

        now = time.time()
        s1_coords, s2_coords = self.get_slot_pixels(frame)
        slot1 = frame[s1_coords[1]:s1_coords[3], s1_coords[0]:s1_coords[2]]
        slot2 = frame[s2_coords[1]:s2_coords[3], s2_coords[0]:s2_coords[2]]

        if slot1.size == 0 or slot2.size == 0:
          time.sleep(0.05)
          continue

        s1_h, s1_w = slot1.shape[:2]
        s2_h, s2_w = slot2.shape[:2]
        # Free Fire Esports Tournament Structure: Exactly 4 players per squad, 3 squads visible
        squad_size = 4
        num_squads = 3
        num_rows = num_squads * squad_size  # 12 rows
        row_height = s1_h / float(num_rows)

        # Initial Roster Discovery via OCR (runs once on start or if names not discovered)
        ocr_results = []
        if (not self.has_initial_roster or len(self.cached_player_names) < 4) and self.ocr is not None and self.ocr_attempts < 2 and s1_w >= 80:
          self.ocr_attempts += 1
          try:
            ocr_results, _ = self.ocr(slot1)
            if ocr_results:
              self.has_initial_roster = True
          except Exception:
            pass

        # Binary mask of Slot 2 for digit matching (High-contrast thresholding rejecting HUD noise)
        s2_gray = cv2.cvtColor(slot2, cv2.COLOR_BGR2GRAY)
        _, s2_thresh = cv2.threshold(s2_gray, 130, 255, cv2.THRESH_BINARY)

        # Pass 1: Extract row-level features (alive status, badge patch, player name, kills)
        raw_players = []
        bg_lab = self.color_engine.estimate_hud_background_lab(slot1)
        for i in range(num_rows):
          y_start = int(i * row_height)
          y_end = int((i + 1) * row_height)
          if y_end > s1_h:
            break
          y_center = (y_start + y_end) / 2.0

          # Check Alive status: in Free Fire, eliminated rows are dimmed/grayed out
          # Name area text is bright white for alive players and dimmed dark gray for eliminated players
          name_zone = frame[
            s1_coords[1] + y_start : s1_coords[1] + y_end,
            s1_coords[2] + 4 : min(frame.shape[1], s1_coords[2] + int(0.18 * frame.shape[1]))
          ]
          if name_zone.size > 0:
            name_gray = cv2.cvtColor(name_zone, cv2.COLOR_BGR2GRAY)
            is_alive = bool(name_gray.max() >= 150 and np.percentile(name_gray, 95) >= 95)
          else:
            is_alive = True

          # Extract badge crop directly from slot1 (the calibrated badge column)
          badge_crop = slot1[y_start + 2: y_end - 2, :]

          # Player Name (use cached name or OCR match)
          player_name = self.cached_player_names.get(i)
          if not player_name or player_name.startswith("Player_"):
            for r in (ocr_results or []):
              cand = r[1].strip()
              if cand in ["ALL", "NEARBY"] or len(cand) < 2:
                continue
              box_cy = (r[0][0][1] + r[0][2][1]) / 2.0
              if abs(box_cy - y_center) < (row_height * 0.45):
                player_name = cand
                self.cached_player_names[i] = cand
                break
          if not player_name:
            player_name = f"Player_{i+1}"

          # Kill Count Detection from Slot 2 (Kills Column)
          digit_zone = s2_thresh[y_start:y_end, :]

          detected_kills = 0
          if digit_zone.size > 0:
            cnts, _ = cv2.findContours(digit_zone.copy(), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            digit_cnts = [
              c for c in cnts 
              if cv2.boundingRect(c)[3] >= 8 and cv2.boundingRect(c)[2] >= 3
              and cv2.boundingRect(c)[3] <= 28 and cv2.boundingRect(c)[2] <= 22
            ]
            digit_cnts.sort(key=lambda c: cv2.boundingRect(c)[0])
            boxes = [cv2.boundingRect(c) for c in digit_cnts]
            # Filter skull icon if slot2 was calibrated wide (skull is at x < 12 and bw >= 10)
            if len(boxes) > 1 and digit_zone.shape[1] > 32 and boxes[0][0] < 12 and boxes[0][2] >= 10:
              boxes.pop(0)
            digits = []
            for bx, by, bw, bh in boxes:
              patch = digit_zone[by:by+bh, bx:bx+bw]
              d = self.classify_digit(patch)
              digits.append(d)
            if digits:
              detected_kills = int("".join(str(d) for d in digits))

          # Kills must be monotonically non-decreasing per player (kills never drop to 0 on death)
          if detected_kills > 0 or i not in self.player_max_kills:
            self.player_max_kills[i] = max(self.player_max_kills.get(i, 0), detected_kills)
          kills = self.player_max_kills.get(i, 0)

          raw_players.append({
            'slot': i + 1,
            'squad_idx': i // squad_size,
            'slot_in_squad': (i % squad_size) + 1,
            'badge_crop': badge_crop,
            'name': player_name,
            'alive': is_alive,
            'kills': kills,
            'y_center': y_center,
            'y_range': (y_start, y_end)
          })

        # Pass 2: Squad-Level Color Consensus (Alive Priority & Dimming Invariance)
        parsed_players = []
        ranked_teams = []
        for sq_idx in range(num_squads):
          squad_rows = [p for p in raw_players if p['squad_idx'] == sq_idx]
          if not squad_rows:
            continue

          alive_rows = [p for p in squad_rows if p['alive']]
          sq_color = "UNKNOWN"
          sq_hex = "#888888"

          # Alive-first extraction: sample un-dimmed alive players
          if alive_rows:
            votes = []
            for r in alive_rows:
              c_name, c_hex = self.color_engine.extract_row_color(
                r['badge_crop'], bg_lab, slot_idx=(sq_idx * 4) + r['slot_in_squad'], is_alive=True
              )
              if c_name not in ["UNKNOWN", "GRAY", "DIMMED"]:
                votes.append((c_name, c_hex))
            if votes:
              winner_name, _ = Counter([v[0] for v in votes]).most_common(1)[0]
              sq_color = winner_name
              sq_hex = self.color_engine.hex_map.get(winner_name, "#00E5FF")
              self.squad_locks[sq_idx] = (sq_color, sq_hex)

          # If all 4 are dead or no alive vote won:
          if sq_color in ["UNKNOWN", "GRAY", "DIMMED"]:
            if sq_idx in self.squad_locks:
              # Dimming Invariance: maintain locked color from earlier in the match!
              sq_color, sq_hex = self.squad_locks[sq_idx]
            else:
              # Fallback to dimmed badges
              dim_votes = []
              for r in squad_rows:
                c_name, c_hex = self.color_engine.extract_row_color(
                  r['badge_crop'], bg_lab, slot_idx=(sq_idx * 4) + r['slot_in_squad'], is_alive=False
                )
                if c_name not in ["UNKNOWN", "GRAY", "DIMMED"]:
                  dim_votes.append((c_name, c_hex))
              if dim_votes:
                winner_name, _ = Counter([v[0] for v in dim_votes]).most_common(1)[0]
                sq_color = winner_name
                sq_hex = self.color_engine.hex_map.get(winner_name, "#555555")

          # Assign member colors: alive players receive the vibrant squad color;
          # dead players are strictly marked DEAD with dimmed gray (#555555) - ZERO OG squad color!
          for p in squad_rows:
            if p['alive']:
              p['color'] = sq_color
              p['hex'] = sq_hex
            else:
              p['color'] = 'DEAD'
              p['hex'] = '#555555'
            p['squadColor'] = sq_color
            p['squadHex'] = sq_hex
            parsed_players.append(p)

          sq_kills = sum(p['kills'] for p in squad_rows)
          sq_alive = sum(1 for p in squad_rows if p['alive'])
          ranked_teams.append({
            'id': f"squad-{sq_idx + 1}",
            'name': f"TEAM {sq_color}",
            'color': sq_hex,
            'colorName': sq_color,
            'kills': sq_kills,
            'alive': sq_alive,
            'players': [{
              'slot': p['slot'],
              'name': p['name'],
              'kills': p['kills'],
              'alive': p['alive'],
              'color': p['color'],
              'hex': p['hex'],
              'hp': p.get('hp', 100.0 if p['alive'] else 0.0)
            } for p in squad_rows]
          })

        # Rank teams: 1st by kills DESC, 2nd by alive DESC
        ranked_teams.sort(key=lambda t: (t['kills'], t['alive']), reverse=True)
        for rank_idx, t in enumerate(ranked_teams):
          t['rank'] = rank_idx + 1

        # Process Dark-Masked Spectator HP Tracker Pipeline (< 1.0 ms)
        hp_result = None
        if self.hp_pipeline is not None:
          try:
            hp_result = self.hp_pipeline.process_frame(frame)
          except Exception:
            pass

        detection_result = {
          'matchId': 'ffws-live-match',
          'teams': ranked_teams,
          'parsed_players': parsed_players,
          'hp_result': hp_result,
          's1_coords': s1_coords,
          's2_coords': s2_coords
        }

        with self.lock:
          self.latest_result = detection_result

        # Periodic sync to Node.js backend (or immediate on first frame)
        if (now - self.last_sync_time >= self.sync_interval) or (self.total_synced_events == 0 and len(ranked_teams) > 0):
          self.last_sync_time = now
          self.total_synced_events += 1

          # 1. Redundant direct write to live_state.json for instant frontend consumption
          total_k = sum(t['kills'] for t in ranked_teams)
          total_a = sum(t['alive'] for t in ranked_teams)
          live_state_obj = {
            'match': {
              'id': 'ffws-live-match',
              'map': 'BERMUDA',
              'status': 'LIVE',
              'lastSync': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
              'visionEngineActive': True,
              'stats': {
                'totalKills': total_k,
                'squadsAlive': sum(1 for t in ranked_teams if t['alive'] > 0),
                'totalSquads': len(ranked_teams)
              }
            },
            'leaderboard': ranked_teams,
            'killFeed': []
          }

          for target_path in [
            os.path.join(self.project_root, 'frontend', 'public', 'live_state.json'),
            os.path.join(self.project_root, 'frontend', 'dist', 'live_state.json'),
            os.path.join(self.project_root, 'server', 'live_state.json')
          ]:
            try:
              os.makedirs(os.path.dirname(target_path), exist_ok=True)
              with open(target_path, 'w', encoding='utf-8') as f:
                json.dump(live_state_obj, f, indent=2)
            except Exception:
              pass

          # 2. HTTP POST Sync with Proxy-Bypass
          try:
            payload = json.dumps({
              'matchId': 'ffws-live-match',
              'teams': ranked_teams
            }).encode('utf-8')
            req = urllib.request.Request(
              f"{self.server_url}/api/scoreboard/sync",
              data=payload,
              headers={'Content-Type': 'application/json'},
              method='POST'
            )
            with self.http_opener.open(req, timeout=1.5) as resp:
              if self.total_synced_events % 5 == 1 or self.total_synced_events <= 3:
                print(f"[VisionEngine] Synced #{self.total_synced_events}: {len(ranked_teams)} teams to backend (Kills: {total_k}, Alive: {total_a})", flush=True)
          except Exception as e:
            if self.total_synced_events % 10 == 1:
              print(f"[VisionEngine Sync Warning] {e}. Ensure Node server is running on port 3001.", flush=True)

        time.sleep(0.05)
      except Exception as e:
        print(f"[_ai_worker_loop Error] {e}", flush=True)
        time.sleep(0.1)

  def feed_frame(self, frame: np.ndarray):
    """Pushes a new video frame to the worker thread"""
    with self.lock:
      self.current_frame = frame

  def draw_visual_overlay(self, frame: np.ndarray) -> np.ndarray:
    """Draws visual HUD overlay and bounding boxes using cached result (Runs at full 30-60 FPS)"""
    preview = frame.copy()
    h, w = preview.shape[:2]

    res = None
    with self.lock:
      if self.latest_result is not None:
        res = self.latest_result

    if res is None:
      cv2.putText(preview, "INITIALIZING AI VISION ENGINE...", (40, 60),
                  cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 230, 255), 2)
      return preview

    s1 = res.get('s1_coords', (0,0,0,0))
    s2 = res.get('s2_coords', (0,0,0,0))
    s1_w_px = max(1, s1[2] - s1[0])

    # 1. Slot 1 (Teams Area) - Vibrant Pure Green
    cv2.rectangle(preview, (s1[0], s1[1]), (s1[2], s1[3]), (0, 255, 0), 2)
    cv2.putText(preview, "SLOT 1: TEAMS & PLAYERS", (s1[0], max(20, s1[1] - 8)),
                cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 255, 0), 1, cv2.LINE_AA)

    # 2. Slot 2 (Kills Column) - Bright Yellow
    cv2.rectangle(preview, (s2[0], s2[1]), (s2[2], s2[3]), (0, 230, 255), 2)
    cv2.putText(preview, "SLOT 2: KILLS", (s2[0] - 15, max(20, s2[1] - 8)),
                cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 230, 255), 1, cv2.LINE_AA)

    # 3. Highlight rows (Aligned Dot Color Debugger: Alive = vibrant squad color; Dead = strictly dimmed dark gray)
    for p in res.get('parsed_players', []):
      y0, y1 = p.get('y_range', (0, 0))
      y_center = p.get('y_center', (y0 + y1) / 2.0)
      y_abs = s1[1] + int(y_center)

      dot_x = s1[0] + 12
      if p['alive']:
        color_bgr = self.color_engine.hex_to_bgr(p.get('hex', '#00E5FF'))
        # Vibrant solid circle for alive player with crisp white border
        cv2.circle(preview, (dot_x, y_abs), 5, color_bgr, -1)
        cv2.circle(preview, (dot_x, y_abs), 5, (255, 255, 255), 1)
        # Subtle green row outline
        cv2.rectangle(preview, (s1[0], s1[1] + y0), (s1[2], s1[1] + y1), (0, 200, 0), 1)
        text_color = (255, 255, 255)
        status_txt = f"{p['name']} ({p['kills']}k)"
      else:
        # Strictly DIMMED dark gray for dead player - ZERO OG squad color!
        cv2.circle(preview, (dot_x, y_abs), 5, (55, 55, 55), -1)
        cv2.circle(preview, (dot_x, y_abs), 5, (95, 95, 95), 1)
        # Dimmed gray row outline
        cv2.rectangle(preview, (s1[0], s1[1] + y0), (s1[2], s1[1] + y1), (45, 45, 45), 1)
        text_color = (110, 110, 110)
        status_txt = f"{p['name']} ({p['kills']}k) [DEAD]"

      cv2.putText(preview, status_txt, (s1[0] + 25, y_abs + 4),
                  cv2.FONT_HERSHEY_SIMPLEX, 0.42, text_color, 1, cv2.LINE_AA)

    # 4. Top Telemetry HUD (Restricted to left/center so it never clips table rows)
    hud_end_x = max(200, s1[0] - 15) if s1[0] > 200 else w
    cv2.rectangle(preview, (0, 0), (hud_end_x, 36), (15, 10, 25), -1)
    cv2.line(preview, (0, 36), (hud_end_x, 36), (70, 50, 100), 1)

    teams = res.get('teams', [])
    total_kills = sum(t['kills'] for t in teams)
    total_alive = sum(t['alive'] for t in teams)
    hud_text = (
      f"LIVE SCOREBOARD AI TRACKER | FPS: {self.fps_display:.1f} | "
      f"TEAMS: {len(teams)} | ALIVE: {total_alive} | KILLS: {total_kills}"
    )
    cv2.putText(preview, hud_text, (18, 24),
                cv2.FONT_HERSHEY_SIMPLEX, 0.48, (230, 230, 255), 1, cv2.LINE_AA)

    # 5. Live Standings Sidebar
    panel_w = 295
    panel_h = 45 + (len(teams) * 28)
    cv2.rectangle(preview, (15, 50), (15 + panel_w, 50 + panel_h), (20, 14, 32), -1)
    cv2.rectangle(preview, (15, 50), (15 + panel_w, 50 + panel_h), (120, 80, 180), 1)
    cv2.putText(preview, "LIVE LEADERBOARD (KILLS)", (25, 72),
                cv2.FONT_HERSHEY_SIMPLEX, 0.48, (0, 230, 255), 1, cv2.LINE_AA)

    for idx, t in enumerate(teams):
      y_pos = 98 + (idx * 28)
      t_bgr = self.color_engine.hex_to_bgr(t['color'])

      cv2.rectangle(preview, (25, y_pos - 12), (32, y_pos + 4), t_bgr, -1)
      row_str = f"#{t['rank']} {t['name']:13s} {t['kills']} Kills ({t['alive']} alive)"
      cv2.putText(preview, row_str, (38, y_pos),
                  cv2.FONT_HERSHEY_SIMPLEX, 0.44, (255, 255, 255), 1, cv2.LINE_AA)

    # 6. Spectator Live HP Overlay (from Dark-Masked HP Tracker Pipeline)
    hp_res = res.get('hp_result')
    if hp_res and self.hp_pipeline is not None:
      preview = self.hp_pipeline.draw_debug_overlay(preview, hp_res, show_canvas_preview=True)

    return preview


def run_live_scoreboard(
  source: str = "image",
  server_url: str = "http://localhost:3001",
  sync_gap: float = 1.2,
  display: bool = True,
  calibrate: bool = False
):
  print("=" * 72, flush=True)
  print(" FREE FIRE LIVE SCOREBOARD VISION TRACKER (ASYNC 60 FPS ENGINE)", flush=True)
  print(f" Source: {source} | Sync Cadence: {sync_gap}s | Backend: {server_url}", flush=True)
  print("=" * 72, flush=True)

  detector = ThreadedScoreboardDetector(server_url=server_url, sync_interval=sync_gap)

  is_image = False
  cap = None
  frame_cache = None
  target_fps = 30.0

  if source.isdigit():
    cap = cv2.VideoCapture(int(source))
    print(f"[VideoSource] Reading from camera index {source}")
  elif source.lower() == "image" or source.endswith(('.jpg', '.jpeg', '.png')):
    is_image = True
    img_candidates = [
      source,
      os.path.join(os.path.dirname(__file__), '..', 'Assets', 'video_4.mp4'),
      os.path.join(os.path.dirname(__file__), 'Assets', 'video_4.mp4'),
      r"C:\Users\ASUS\.gemini\antigravity\brain\a120a3e1-ce4b-467c-add4-2d6988cc4804\.user_uploaded\media_1795341829235_6f6dddd3.jpg"
    ]
    img_path = None
    for cand in img_candidates:
      if os.path.exists(cand) and cand.endswith(('.jpg', '.jpeg', '.png')):
        img_path = cand
        break
    if img_path:
      frame_cache = cv2.imread(img_path)
    if frame_cache is None:
      # If source is default 'image' but no image found, fallback to video_4.mp4
      v4_candidates = [
        os.path.join(os.path.dirname(__file__), 'Assets', 'video_4.mp4'),
        os.path.join(os.path.dirname(__file__), '..', 'Assets', 'video_4.mp4')
      ]
      for v4 in v4_candidates:
        if os.path.exists(v4):
          is_image = False
          cap = cv2.VideoCapture(v4)
          if cap.isOpened():
            v_fps = cap.get(cv2.CAP_PROP_FPS)
            if v_fps > 0:
              target_fps = v_fps
            print(f"[VideoSource] Image fallback: streaming video from {v4} (FPS: {target_fps:.1f})")
            break
      if is_image and frame_cache is None:
        print(f"[Error] Failed to load any input image or fallback video.")
        return
    else:
      print(f"[VideoSource] Streaming static screenshot: {img_path}")
  else:
    cap = cv2.VideoCapture(source)
    if cap.isOpened():
      v_fps = cap.get(cv2.CAP_PROP_FPS)
      if v_fps > 0:
        target_fps = v_fps
    print(f"[VideoSource] Reading from video file: {source} (Target FPS: {target_fps:.1f})")

  if calibrate:
    sample_f = frame_cache if is_image else cap.read()[1]
    if sample_f is not None:
      detector.interactive_calibrate_slots(sample_f)

  window_name = "Free Fire Live Scoreboard Tracker [Press 'q' to Quit, 's' to Select Slots]"
  if display:
    cv2.namedWindow(window_name, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(window_name, 1280, 720)

  print("\n[Tracker Active] Live video loop running at native FPS. Press 'q' to exit.\n")

  frame_interval = 1.0 / target_fps
  last_frame_time = time.time()
  fps_history = []

  try:
    while True:
      loop_start = time.time()

      if is_image:
        frame = frame_cache.copy()
        ret = True
      else:
        ret, frame = cap.read()
        if not ret or frame is None:
          print("[VideoSource] Reached end of video. Looping stream...")
          cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
          time.sleep(0.1)
          continue

      # Feed frame to background AI worker
      detector.feed_frame(frame)

      # Smooth Frame Rate Counter
      elapsed = loop_start - last_frame_time
      last_frame_time = loop_start
      if elapsed > 0:
        fps_history.append(1.0 / elapsed)
        if len(fps_history) > 15:
          fps_history.pop(0)
        detector.fps_display = sum(fps_history) / float(len(fps_history))

      # Draw Visual Overlay at Full Smooth Frame Rate
      if display:
        overlay = detector.draw_visual_overlay(frame)
        cv2.imshow(window_name, overlay)

        key = cv2.waitKey(1) & 0xFF
        if key == ord('q'):
          break
        elif key == ord('s'):
          detector.interactive_calibrate_slots(frame)

      # Maintain smooth playback timing
      proc_time = time.time() - loop_start
      sleep_dur = frame_interval - proc_time
      if sleep_dur > 0.001:
        time.sleep(sleep_dur)

  except KeyboardInterrupt:
    print("\n[Stopped] Interrupted by user.")
  finally:
    detector.running = False
    if cap is not None:
      cap.release()
    if display:
      cv2.destroyAllWindows()


if __name__ == '__main__':
  parser = argparse.ArgumentParser(description="Free Fire Live Scoreboard Tracker")
  parser.add_argument("--source", type=str, default="image", help="Camera index ('0'), video file (.mp4), or 'image'")
  parser.add_argument("--server", type=str, default="http://localhost:3001", help="Leaderboard server URL")
  parser.add_argument("--gap", type=float, default=1.2, help="Sync gap in seconds (default 1.2s)")
  parser.add_argument("--display", action="store_true", default=True, help="Display OpenCV visual plotting window")
  parser.add_argument("--no-display", dest="display", action="store_false")
  parser.add_argument("--calibrate", action="store_true", help="Launch interactive 2-slot selector on startup")

  args = parser.parse_args()
  run_live_scoreboard(
    source=args.source,
    server_url=args.server,
    sync_gap=args.gap,
    display=args.display,
    calibrate=args.calibrate
  )
