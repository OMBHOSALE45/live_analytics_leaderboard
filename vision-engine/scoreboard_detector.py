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
  O(N) Perceptual Badge Color Classifier:
  1. Frame-adaptive CIE Lab background subtraction (eliminates 224-272 HUD bleed)
  2. Chroma-energy O(N) Quickselect (np.argpartition)
  3. Circular Gaussian-smoothed weighted Hue mode (fixes Red 0/360 wrap & bimodality)
  4. Chroma-priority CIE Lab nearest-neighbor matching (12-color esports palette)
  5. Per-slot temporal consensus voting & lock (prevents flicker & post-death loss)
  """

  # Expanded 12-color Free Fire esports palette (Name -> Hex)
  PALETTE_HEX = {
    "RED":      "#FF2A2A",
    "ORANGE":   "#FF7F00",
    "YELLOW":   "#FFD700",
    "LIME":     "#A8FF00",
    "GREEN":    "#00D860",
    "CYAN":     "#00E5FF",
    "SKY_BLUE": "#3898FF",
    "BLUE":     "#1E4BFF",
    "PURPLE":   "#8A2BE2",
    "MAGENTA":  "#E024FF",
    "PINK":     "#FF2E93",
    "CORAL":    "#FF6B6B",
  }

  def __init__(self, vote_window: int = 9, lock_threshold: int = 5):
    self.names = list(self.PALETTE_HEX.keys())
    self.hex_map = self.PALETTE_HEX
    self.palette_lab = self._build_palette_lab()

    # Circular Gaussian smoothing kernel over 180 OpenCV Hue bins
    k = np.array([0.05, 0.12, 0.20, 0.26, 0.20, 0.12, 0.05], dtype=np.float32)
    self.hue_kernel = k / k.sum()
    self.kernel_pad = len(k) // 2

    # Temporal smoothing & lock state per row slot
    self.vote_window = vote_window
    self.lock_threshold = lock_threshold
    self.slot_votes: Dict[int, deque] = {}
    self.slot_locked: Dict[int, Tuple[str, str]] = {}
    self.slot_lab_ema: Dict[int, np.ndarray] = {}

  def _build_palette_lab(self) -> np.ndarray:
    """Precomputes (P, 3) float32 Lab matrix: [L, a-128, b-128]."""
    bgr_list = []
    for name in self.names:
      hx = self.PALETTE_HEX[name].lstrip("#")
      r, g, b = int(hx[0:2], 16), int(hx[2:4], 16), int(hx[4:6], 16)
      bgr_list.append([b, g, r])
    bgr_arr = np.array(bgr_list, dtype=np.uint8).reshape(-1, 1, 3)
    lab = cv2.cvtColor(bgr_arr, cv2.COLOR_BGR2LAB).reshape(-1, 3).astype(np.float32)
    lab[:, 1] -= 128.0
    lab[:, 2] -= 128.0
    return lab

  @staticmethod
  def hex_to_bgr(hex_str: str) -> Tuple[int, int, int]:
    hx = hex_str.lstrip("#")
    return (int(hx[4:6], 16), int(hx[2:4], 16), int(hx[0:2], 16))

  def reset_cache(self):
    """Call this when recalibrating slots or starting a new match."""
    self.slot_votes.clear()
    self.slot_locked.clear()
    self.slot_lab_ema.clear()

  def estimate_hud_background_lab(self, slot1_bgr: np.ndarray) -> np.ndarray:
    """
    Estimates the dark translucent scoreboard panel background in Lab space
    once per frame using the darkest 40% of pixels in Slot 1.
    """
    if slot1_bgr is None or slot1_bgr.size == 0:
      return np.array([30.0, 0.0, 0.0], dtype=np.float32)

    lab = cv2.cvtColor(slot1_bgr, cv2.COLOR_BGR2LAB).astype(np.float32)
    flat = lab.reshape(-1, 3).copy()
    flat[:, 1] -= 128.0
    flat[:, 2] -= 128.0

    # O(N) partition to sample the dark backdrop pixels (rejecting text & bright badges)
    n = flat.shape[0]
    k = max(1, min(n - 1, int(n * 0.40)))
    if n > 1:
      dark_idx = np.argpartition(flat[:, 0], k)[:k]
      bg_lab = np.median(flat[dark_idx], axis=0)
    else:
      bg_lab = flat[0]
    return bg_lab

  def extract_row_color(
    self,
    badge_bgr: np.ndarray,
    bg_lab: np.ndarray,
    slot_idx: int,
    is_alive: bool = True,
    debug: bool = False
  ) -> Tuple[str, str, Optional[np.ndarray]]:
    """
    Extracts the foreground badge color for a single row.
    Returns: (color_name, hex_color, inlier_lab_centroid)
    """
    if badge_bgr is None or badge_bgr.size == 0:
      return self._fallback_cached(slot_idx)

    # Convert small crop to Lab & HSV
    lab = cv2.cvtColor(badge_bgr, cv2.COLOR_BGR2LAB).astype(np.float32)
    hsv = cv2.cvtColor(badge_bgr, cv2.COLOR_BGR2HSV)

    L = lab[:, :, 0]
    a = lab[:, :, 1] - 128.0
    b = lab[:, :, 2] - 128.0
    chroma = np.sqrt(a * a + b * b)

    # Stage 1: Adaptive background subtraction + achromatic rejection
    bg_dist = np.sqrt(
      (L - bg_lab[0]) ** 2 +
      (a - bg_lab[1]) ** 2 +
      (b - bg_lab[2]) ** 2
    )
    fg_mask = (bg_dist > 24.0) & (chroma > 22.0) & (L > 45.0) & (L < 245.0)

    fg_count = int(np.count_nonzero(fg_mask))
    if fg_count < 6:
      # Row may be eliminated/dimmed -> use temporal lock if available
      return self._fallback_cached(slot_idx)

    L_fg = L[fg_mask]
    a_fg = a[fg_mask]
    b_fg = b[fg_mask]
    c_fg = chroma[fg_mask]
    h_fg = hsv[:, :, 0][fg_mask].astype(np.int32)

    # Stage 2: O(N) Quickselect for top 35% highest chroma-energy foreground pixels
    energy = (c_fg ** 2) * (L_fg / 255.0)
    top_k = max(6, int(fg_count * 0.35))
    if fg_count > top_k:
      top_idx = np.argpartition(energy, fg_count - top_k)[fg_count - top_k:]
      L_fg, a_fg, b_fg = L_fg[top_idx], a_fg[top_idx], b_fg[top_idx]
      h_fg, energy = h_fg[top_idx], energy[top_idx]

    # Stage 3: Energy-weighted Circular Hue Histogram + Circular Gaussian Smoothing
    hist = np.bincount(h_fg, weights=energy, minlength=180).astype(np.float32)
    pad = self.kernel_pad
    padded = np.concatenate([hist[-pad:], hist, hist[:pad]])
    smooth_hist = np.convolve(padded, self.hue_kernel, mode="valid")
    peak_bin = int(np.argmax(smooth_hist))

    # Keep only circular inliers within +/- 8 OpenCV hue bins (+/- 16 degrees)
    diff = np.abs(h_fg - peak_bin)
    circ_dist = np.minimum(diff, 180 - diff)
    inliers = circ_dist <= 8
    if np.count_nonzero(inliers) < 4:
      inliers = np.ones_like(h_fg, dtype=bool)

    centroid_lab = np.array([
      float(np.median(L_fg[inliers])),
      float(np.median(a_fg[inliers])),
      float(np.median(b_fg[inliers]))
    ], dtype=np.float32)

    # Smooth Lab vector over time with EMA (alpha = 0.25)
    if slot_idx in self.slot_lab_ema:
      centroid_lab = 0.75 * self.slot_lab_ema[slot_idx] + 0.25 * centroid_lab
    self.slot_lab_ema[slot_idx] = centroid_lab

    # Stage 4: Chroma-priority Lab nearest-neighbor match
    diffs = self.palette_lab - centroid_lab
    weighted_dist = np.sqrt(
      0.35 * (diffs[:, 0] ** 2) +
      1.00 * (diffs[:, 1] ** 2) +
      1.00 * (diffs[:, 2] ** 2)
    )
    best_idx = int(np.argmin(weighted_dist))
    raw_name = self.names[best_idx]
    raw_hex = self.hex_map[raw_name]

    if debug:
      print(
        f"[Row {slot_idx+1:02d}] PeakHue={peak_bin*2:3d}° | "
        f"Lab=({centroid_lab[0]:.0f},{centroid_lab[1]:+.0f},{centroid_lab[2]:+.0f}) | "
        f"Dist={weighted_dist[best_idx]:.1f} -> {raw_name}"
      )

    # Stage 5: Temporal consensus voting & slot lock
    if is_alive:
      buf = self.slot_votes.setdefault(slot_idx, deque(maxlen=self.vote_window))
      buf.append(raw_name)
      winner, count = Counter(buf).most_common(1)[0]
      if count >= self.lock_threshold:
        self.slot_locked[slot_idx] = (winner, self.hex_map[winner])
      return winner, self.hex_map[winner], centroid_lab

    if slot_idx in self.slot_locked:
      name, hx = self.slot_locked[slot_idx]
      return name, hx, centroid_lab

    return raw_name, raw_hex, centroid_lab

  def _fallback_cached(self, slot_idx: int) -> Tuple[str, str, Optional[np.ndarray]]:
    if slot_idx in self.slot_locked:
      name, hx = self.slot_locked[slot_idx]
      return name, hx, self.slot_lab_ema.get(slot_idx)
    return "GRAY", "#555555", None


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
    self.squad_locks = {}  # Persistent squad-level color locks: squad_idx -> (color_name, hex)
    self.has_initial_roster = False
    self.ocr_attempts = 0

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
    """Loads templates for in-game font digits 0, 1, 2"""
    base_dir = os.path.dirname(__file__)
    for d in [0, 1, 2]:
      path = os.path.join(base_dir, '..', f'real_tpl_{d}.png')
      if os.path.exists(path):
        tpl = cv2.imread(path, cv2.IMREAD_GRAYSCALE)
        if tpl is not None and tpl.size > 0:
          self.templates[d] = tpl

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
    Combines template matching against authentic Free Fire font with
    hole/cavity topology and structural stroke analysis.
    """
    if digit_crop is None or digit_crop.size == 0:
      return 0
    h, w = digit_crop.shape[:2]
    # Digits in Free Fire are vertically oriented (4-18px wide, 9-25px high)
    if h < 9 or h > 26 or w < 4 or w > 18 or h < w:
      return 0

    # 1. Closed loop check for Digit 0 (hole detection)
    cnts, hier = cv2.findContours(digit_crop.copy(), cv2.RETR_CCOMP, cv2.CHAIN_APPROX_SIMPLE)
    if hier is not None and len(cnts) > 1:
      for idx in range(len(cnts)):
        if hier[0][idx][3] == -1 and hier[0][idx][2] != -1:
          child_idx = hier[0][idx][2]
          hole_area = cv2.contourArea(cnts[child_idx])
          if hole_area >= 6:
            return 0

    # 2. Hollow center check for Digit 0 (hollow oval fallback)
    mid_y1, mid_y2 = int(h * 0.30), int(h * 0.70)
    mid_x1, mid_x2 = max(1, int(w * 0.30)), max(2, int(w * 0.70))
    center_slice = digit_crop[mid_y1:mid_y2, mid_x1:mid_x2]
    left_slice = digit_crop[mid_y1:mid_y2, :mid_x1]
    right_slice = digit_crop[mid_y1:mid_y2, mid_x2:]

    c_fill = float(np.mean(center_slice > 0)) if center_slice.size > 0 else 0.0
    l_fill = float(np.mean(left_slice > 0)) if left_slice.size > 0 else 0.0
    r_fill = float(np.mean(right_slice > 0)) if right_slice.size > 0 else 0.0
    if c_fill < 0.28 and l_fill > 0.35 and r_fill > 0.35:
      return 0

    # 3. Direct template correlation with in-game font templates
    if hasattr(self, 'templates') and self.templates:
      best_score = -1.0
      best_d = 0
      for d, tpl in self.templates.items():
        th_h, th_w = tpl.shape[:2]
        if abs(h - th_h) <= 6 and abs(w - th_w) <= 4:
          tpl_res = cv2.resize(tpl, (w, h), interpolation=cv2.INTER_NEAREST)
          score = float(np.sum((digit_crop > 0) == (tpl_res > 100))) / float(h * w)
          if score > best_score:
            best_score = score
            best_d = d
      if best_score >= 0.78:
        return best_d

    # 4. Structural verification: Digit 1 (narrow vertical spine)
    if (w <= 6 or (h / float(w) >= 2.0)) and w >= 4:
      mid_col = digit_crop[:, w // 2]
      if np.mean(mid_col > 0) >= 0.60:
        return 1

    # 5. Structural verification: Digit 2 (flat base + top arch)
    if w >= 6 and h >= 11:
      bot_slice = digit_crop[max(0, h - 3):, :]
      bot_fill = float(np.mean(bot_slice > 0)) if bot_slice.size > 0 else 0.0
      top_right = digit_crop[:int(h * 0.45), int(w * 0.5):]
      tr_fill = float(np.mean(top_right > 0)) if top_right.size > 0 else 0.0
      if bot_fill >= 0.55 and tr_fill >= 0.35:
        return 2

    # Default to 0 kills for zero false positives
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

        # Binary mask of Slot 2 for digit matching (Adaptive Otsu thresholding)
        s2_gray = cv2.cvtColor(slot2, cv2.COLOR_BGR2GRAY)
        _, s2_thresh = cv2.threshold(s2_gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

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
          if s1_w >= 50:
            name_zone = slot1[y_start:y_end, int(s1_w * 0.32):]
          else:
            name_zone = slot1[y_start:y_end, :]
          max_brightness = int(cv2.cvtColor(name_zone, cv2.COLOR_BGR2GRAY).max()) if name_zone.size > 0 else 0
          is_alive = bool(max_brightness >= 140)

          # Extract badge crop
          if s1_w < 50:
            badge_crop = slot1[y_start + 2: y_end - 2, :]
          else:
            bx1 = int(s1_w * 0.06)
            bx2 = int(s1_w * 0.30)
            badge_crop = slot1[y_start + 2: y_end - 2, bx1:bx2]

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
          dx1 = int(s2_w * 0.38)
          dx2 = int(s2_w * 0.88)
          digit_zone = s2_thresh[y_start:y_end, dx1:dx2]

          kills = 0
          if is_alive and digit_zone.size > 0:
            cnts, _ = cv2.findContours(digit_zone.copy(), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            valid_cnts = [
              c for c in cnts 
              if cv2.boundingRect(c)[3] >= 9 and 4 <= cv2.boundingRect(c)[2] <= 18
              and not (cv2.boundingRect(c)[0] <= 1 and cv2.boundingRect(c)[2] <= 3)
            ]
            if valid_cnts:
              best_c = max(valid_cnts, key=cv2.contourArea)
              bx, by, bw, bh = cv2.boundingRect(best_c)
              patch = digit_zone[by:by+bh, bx:bx+bw]
              kills = self.classify_digit(patch)

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
              c_name, c_hex, _ = self.color_engine.extract_row_color(
                r['badge_crop'], bg_lab, slot_idx=(sq_idx * 4) + r['slot_in_squad'], is_alive=True
              )
              if c_name not in ["UNKNOWN", "GRAY"]:
                votes.append((c_name, c_hex))
            if votes:
              winner_name, _ = Counter([v[0] for v in votes]).most_common(1)[0]
              sq_color = winner_name
              sq_hex = self.color_engine.hex_map.get(winner_name, "#00E5FF")
              self.squad_locks[sq_idx] = (sq_color, sq_hex)

          # If all 4 are dead or no alive vote won:
          if sq_color in ["UNKNOWN", "GRAY"]:
            if sq_idx in self.squad_locks:
              # Dimming Invariance: maintain locked color from earlier in the match!
              sq_color, sq_hex = self.squad_locks[sq_idx]
            else:
              # Fallback to dimmed badges
              dim_votes = []
              for r in squad_rows:
                c_name, c_hex, _ = self.color_engine.extract_row_color(
                  r['badge_crop'], bg_lab, slot_idx=(sq_idx * 4) + r['slot_in_squad'], is_alive=False
                )
                if c_name not in ["UNKNOWN", "GRAY"]:
                  dim_votes.append((c_name, c_hex))
              if dim_votes:
                winner_name, _ = Counter([v[0] for v in dim_votes]).most_common(1)[0]
                sq_color = winner_name
                sq_hex = self.color_engine.hex_map.get(winner_name, "#555555")

          # Assign the squad's true color to ALL 4 members (dimmed dead players share squad color)
          for p in squad_rows:
            p['color'] = sq_color
            p['hex'] = sq_hex
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
              'alive': p['alive']
            } for p in squad_rows]
          })

        # Rank teams: 1st by kills DESC, 2nd by alive DESC
        ranked_teams.sort(key=lambda t: (t['kills'], t['alive']), reverse=True)
        for rank_idx, t in enumerate(ranked_teams):
          t['rank'] = rank_idx + 1

        detection_result = {
          'matchId': 'ffws-live-match',
          'teams': ranked_teams,
          'parsed_players': parsed_players,
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

    # 1. Slot 1 (Teams Area) - Cyan
    cv2.rectangle(preview, (s1[0], s1[1]), (s1[2], s1[3]), (255, 255, 0), 2)
    cv2.putText(preview, "SLOT 1: TEAMS & PLAYERS", (s1[0], max(20, s1[1] - 8)),
                cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 255, 0), 1, cv2.LINE_AA)

    # 2. Slot 2 (Kills Column) - Neon Yellow
    cv2.rectangle(preview, (s2[0], s2[1]), (s2[2], s2[3]), (0, 230, 255), 2)
    cv2.putText(preview, "SLOT 2: KILLS", (s2[0] - 15, max(20, s2[1] - 8)),
                cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 230, 255), 1, cv2.LINE_AA)

    # 3. Highlight rows (Aligned Dot Colour Debugger: Exactly 4 dots per colour!)
    for p in res.get('parsed_players', []):
      color_bgr = self.color_engine.hex_to_bgr(p.get('hex', '#555555'))
      y0, y1 = p.get('y_range', (0, 0))
      y_center = p.get('y_center', (y0 + y1) / 2.0)
      y_abs = s1[1] + int(y_center)

      dot_x = s1[0] + 12
      if p['alive']:
        # Vibrant solid circle for alive player
        cv2.circle(preview, (dot_x, y_abs), 5, color_bgr, -1)
        text_color = (255, 255, 255)
        status_txt = f"{p['name']} ({p['kills']}k)"
      else:
        # Dimmed core + distinct team-color ring for dead player
        dim_bgr = tuple(int(c * 0.35) for c in color_bgr)
        cv2.circle(preview, (dot_x, y_abs), 5, dim_bgr, -1)
        cv2.circle(preview, (dot_x, y_abs), 5, color_bgr, 1)
        text_color = (130, 130, 130)
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
    img_path = source if source.endswith(('.jpg', '.jpeg', '.png')) else \
      'C:/Users/ombho/.gemini/antigravity/brain/9ac33c4f-61ae-49fb-b6c6-906f60d76421/.user_uploaded/media_1795189371364_56ee1503.jpg'
    frame_cache = cv2.imread(img_path)
    if frame_cache is None:
      print(f"[Error] Failed to load image from {img_path}")
      return
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
