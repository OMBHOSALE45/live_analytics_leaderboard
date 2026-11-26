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


"""Badge colour engine"""
class BadgeColorEngine:
  """
  Esports Badge Color Classifier:
  - 11-color Free Fire esports palette: RED, ORANGE, YELLOW, GREEN, MINT GREEN, CYAN, BLUE, PURPLE, PINK, BROWN, GRAY
  - Strict chroma + RGB-spread gating prevents cool-gray/silver badges from leaking into BLUE/CYAN
  - Dead / eliminated players are strictly categorized as DIMMED (#555555)
  - Zero color hallucination: dead rows never pollute team consensus
  """

  # Canonical Free Fire esports tournament palette (including MINT GREEN, BROWN, GRAY)
  PALETTE_HEX = {
    "RED":        "#FF2A2A",
    "ORANGE":     "#FF7F00",
    "YELLOW":     "#FFD700",
    "GREEN":      "#00D860",
    "MINT GREEN": "#5ED4AA",
    "CYAN":       "#00E5FF",
    "BLUE":       "#1E4BFF",
    "PURPLE":     "#8A2BE2",
    "PINK":       "#FF2E93",
    "BROWN":      "#8A631A",
    "GRAY":       "#9EA7B0",
    "DIMMED":     "#555555",
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
    """Call this when recalibrating slots, scrolling, or starting a new match."""
    self.slot_votes.clear()
    self.slot_locked.clear()

  def estimate_hud_background_lab(self, slot1_bgr: np.ndarray) -> np.ndarray:
    if slot1_bgr is None or slot1_bgr.size == 0:
      return np.array([30.0, 0.0, 0.0], dtype=np.float32)
    lab = cv2.cvtColor(slot1_bgr, cv2.COLOR_BGR2LAB).astype(np.float32)
    flat = lab.reshape(-1, 3)
    return np.median(flat, axis=0)

  @staticmethod
  def _crop_badge_interior(badge_bgr: np.ndarray) -> np.ndarray:
    """Trims outer 15% borders to reject row dividers, highlights, and edge bleed."""
    if badge_bgr is None or badge_bgr.size == 0:
      return badge_bgr
    bh, bw = badge_bgr.shape[:2]
    mx = max(1, int(bw * 0.15)) if bw >= 10 else 0
    my = max(1, int(bh * 0.15)) if bh >= 10 else 0
    inner = badge_bgr[my:bh - my, mx:bw - mx]
    return inner if inner.size > 0 else badge_bgr

  @classmethod
  def measure_badge_chroma(cls, badge_bgr: np.ndarray) -> Tuple[float, float, float]:
    """
    Measures chromatic strength of a badge interior.
    Returns: (vibrant_ratio, median_sat_of_bright, median_rgb_spread_of_bright)
    """
    if badge_bgr is None or badge_bgr.size == 0:
      return 0.0, 0.0, 0.0

    inner = cls._crop_badge_interior(badge_bgr)
    hsv = cv2.cvtColor(inner, cv2.COLOR_BGR2HSV)
    sat = hsv[:, :, 1].astype(np.float32)
    val = hsv[:, :, 2].astype(np.float32)

    b_ch = inner[:, :, 0].astype(np.int16)
    g_ch = inner[:, :, 1].astype(np.int16)
    r_ch = inner[:, :, 2].astype(np.int16)
    spread = (np.maximum(np.maximum(b_ch, g_ch), r_ch) - np.minimum(np.minimum(b_ch, g_ch), r_ch)).astype(np.float32)

    vibrant = (sat >= 105.0) & (val >= 65.0) & (spread >= 42.0)
    total_px = float(max(1, inner.shape[0] * inner.shape[1]))
    vibrant_ratio = float(np.count_nonzero(vibrant)) / total_px

    bright = val >= 75.0
    if np.any(bright):
      med_sat = float(np.median(sat[bright]))
      med_spread = float(np.median(spread[bright]))
    else:
      med_sat = 0.0
      med_spread = 0.0

    return vibrant_ratio, med_sat, med_spread

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
    Strict rules:
      - If player is NOT alive -> ('DIMMED', '#555555').
      - If player IS alive and badge is achromatic/low-saturation -> ('GRAY', '#9EA7B0').
      - Never allows cool-gray/silver compression tint to leak into BLUE/CYAN.
    """
    if not is_alive or badge_bgr is None or badge_bgr.size == 0:
      return "DIMMED", "#555555"

    inner = self._crop_badge_interior(badge_bgr)
    hsv = cv2.cvtColor(inner, cv2.COLOR_BGR2HSV)
    sat = hsv[:, :, 1]
    val = hsv[:, :, 2]
    hue = hsv[:, :, 0].astype(np.int32) * 2

    # RGB channel spread rejects cool-gray/silver badges that have low R/G/B separation
    b_ch = inner[:, :, 0].astype(np.int16)
    g_ch = inner[:, :, 1].astype(np.int16)
    r_ch = inner[:, :, 2].astype(np.int16)
    spread = np.maximum(np.maximum(b_ch, g_ch), r_ch) - np.minimum(np.minimum(b_ch, g_ch), r_ch)

    total_px = max(1, inner.shape[0] * inner.shape[1])

    # Strict vibrant chromatic mask (rejects gray/silver badges, dark shadows, white digits)
    vibrant = (sat >= 105) & (val >= 65) & (spread >= 42)
    fg_count = int(np.count_nonzero(vibrant))
    fg_ratio = fg_count / float(total_px)

    if fg_count < 10 or fg_ratio < 0.16:
      raw_name = "GRAY"
    else:
      med_hue = int(np.median(hue[vibrant]))
      med_sat = float(np.median(sat[vibrant]))
      med_val = float(np.median(val[vibrant]))
      med_spread = float(np.median(spread[vibrant]))

      # Free Fire Esports Standard Color Classification (11-color palette)
      if med_hue >= 345 or med_hue <= 18:
        raw_name = "RED"
      elif 19 <= med_hue <= 50 and med_val < 175:
        raw_name = "BROWN"
      elif 19 <= med_hue <= 42:
        raw_name = "ORANGE"
      elif 43 <= med_hue <= 70:
        raw_name = "YELLOW"
      elif 71 <= med_hue <= 149:
        raw_name = "GREEN"
      elif 150 <= med_hue <= 168:
        raw_name = "MINT GREEN"
      elif 169 <= med_hue <= 200:
        raw_name = "CYAN"
      elif 201 <= med_hue <= 245:
        raw_name = "BLUE"
      elif 246 <= med_hue <= 295:
        raw_name = "PURPLE"
      elif 296 <= med_hue <= 344:
        raw_name = "PINK"
      else:
        raw_name = "CYAN"

      # Extra guard: cool-gray/silver badges under H.264 drift into 180-245 hue with weak sat/spread
      if raw_name in ("BLUE", "CYAN") and (med_sat < 115.0 or med_spread < 48.0):
        raw_name = "GRAY"

    buf = self.slot_votes.setdefault(slot_idx, deque(maxlen=self.vote_window))
    buf.append(raw_name)
    winner, count = Counter(buf).most_common(1)[0]
    if count >= self.lock_threshold:
      self.slot_locked[slot_idx] = (winner, self.hex_map[winner])
    return winner, self.hex_map[winner]


class PlayerKillState:
  """
  Per-row temporal kill state machine:
  - Eliminates single-frame hallucinations (never locks on a single spike)
  - Fast confirmation for realistic +1 increments (~0.15-0.25s)
  - Strict verification for multi-kill jumps (+2..+4 or larger)
  - Self-healing downward correction if an initial reading was ever wrong
  """
  def __init__(self):
    self.confirmed_kills: int = 0
    self.initialized: bool = False
    self.recent_reads: deque = deque(maxlen=11)  # (val, weight, is_ocr)
    self.candidate_val: Optional[int] = None
    self.candidate_streak: int = 0
    self.candidate_ocr_confirmed: bool = False
    self.lower_val: Optional[int] = None
    self.lower_streak: int = 0
    self.lower_ocr_confirmed: bool = False
    self.last_raw: Optional[int] = None
    self.last_conf: float = 0.0

  def reset(self):
    self.confirmed_kills = 0
    self.initialized = False
    self.recent_reads.clear()
    self.candidate_val = None
    self.candidate_streak = 0
    self.candidate_ocr_confirmed = False
    self.lower_val = None
    self.lower_streak = 0
    self.lower_ocr_confirmed = False
    self.last_raw = None
    self.last_conf = 0.0

  def update(self, raw_val: Optional[int], conf: float, ocr_val: Optional[int] = None, ocr_conf: float = 0.0) -> int:
    if raw_val is None and ocr_val is None:
      return self.confirmed_kills

    fused_val = raw_val
    fused_conf = conf
    ocr_agrees = False

    if ocr_val is not None and ocr_conf >= 0.72:
      if raw_val is None:
        fused_val = ocr_val
        fused_conf = ocr_conf
        ocr_agrees = True
      elif ocr_val == raw_val:
        fused_val = raw_val
        fused_conf = min(1.0, max(conf, ocr_conf) + 0.15)
        ocr_agrees = True
      else:
        if ocr_conf >= 0.90 and conf < 0.80:
          fused_val = ocr_val
          fused_conf = ocr_conf
          ocr_agrees = True
        elif conf >= 0.88 and ocr_conf < 0.82:
          fused_val = raw_val
          fused_conf = conf
        else:
          return self.confirmed_kills

    if fused_val is None or fused_val < 0 or fused_val > 45:
      return self.confirmed_kills

    self.last_raw = fused_val
    self.last_conf = fused_conf
    weight = 2.0 if ocr_agrees else max(0.5, fused_conf)
    self.recent_reads.append((fused_val, weight, ocr_agrees))

    if not self.initialized:
      scores: Dict[int, float] = {}
      counts: Dict[int, int] = {}
      has_ocr: Dict[int, bool] = {}
      for v, w, is_o in self.recent_reads:
        scores[v] = scores.get(v, 0.0) + w
        counts[v] = counts.get(v, 0) + 1
        if is_o:
          has_ocr[v] = True
      best_v = max(scores, key=scores.get)
      if counts[best_v] >= 3 or (counts[best_v] >= 2 and has_ocr.get(best_v, False)):
        self.confirmed_kills = best_v
        self.initialized = True
        self.candidate_val = None
        self.candidate_streak = 0
        self.lower_val = None
        self.lower_streak = 0
        return self.confirmed_kills
      if counts[best_v] >= 2 or fused_conf >= 0.82:
        return best_v
      return self.confirmed_kills

    if fused_val == self.confirmed_kills:
      self.candidate_val = None
      self.candidate_streak = 0
      self.candidate_ocr_confirmed = False
      self.lower_val = None
      self.lower_streak = 0
      self.lower_ocr_confirmed = False
      return self.confirmed_kills

    if fused_val > self.confirmed_kills:
      self.lower_val = None
      self.lower_streak = 0
      self.lower_ocr_confirmed = False

      delta = fused_val - self.confirmed_kills
      if self.candidate_val == fused_val:
        self.candidate_streak += 1
        if ocr_agrees:
          self.candidate_ocr_confirmed = True
      else:
        self.candidate_val = fused_val
        self.candidate_streak = 1
        self.candidate_ocr_confirmed = ocr_agrees

      if delta == 1:
        needed = 2 if self.candidate_ocr_confirmed else 3
      elif delta <= 3:
        needed = 3 if self.candidate_ocr_confirmed else 5
      else:
        needed = 5 if self.candidate_ocr_confirmed else 10

      if self.candidate_streak >= needed:
        self.confirmed_kills = fused_val
        self.candidate_val = None
        self.candidate_streak = 0
        self.candidate_ocr_confirmed = False
      return self.confirmed_kills

    if fused_val < self.confirmed_kills:
      self.candidate_val = None
      self.candidate_streak = 0
      self.candidate_ocr_confirmed = False

      if self.lower_val == fused_val:
        self.lower_streak += 1
        if ocr_agrees:
          self.lower_ocr_confirmed = True
      else:
        self.lower_val = fused_val
        self.lower_streak = 1
        self.lower_ocr_confirmed = ocr_agrees

      needed_down = 8 if self.lower_ocr_confirmed else 16
      if self.lower_streak >= needed_down:
        self.confirmed_kills = fused_val
        self.lower_val = None
        self.lower_streak = 0
        self.lower_ocr_confirmed = False

    return self.confirmed_kills


class KillCountEngine:
  """
  Bulletproof Free Fire Scoreboard Kill Recognition Engine:
  1. Per-row dimming-invariant segmentation (works on bright alive AND dimmed dead rows).
  2. Padded vertical extraction + strict centroid ownership (zero digit clipping).
  3. High-chroma icon rejection (ignores orange spectator eye & left edge artifacts).
  4. Aspect-preserving Normalized Cross-Correlation against multi-style condensed templates
     + topological hole geometry + 6-zone ink profile (eliminates 4->0 and 3->8/9 confusions).
  5. Optional RapidOCR recognition-only verification on clean padded black-on-white crops.
  6. Per-row anti-poisoning temporal state machine with scoreboard-occlusion guard.
  """

  CANVAS_W = 28
  CANVAS_H = 36

  OCR_CHAR_MAP = {
    'O': '0', 'o': '0', 'D': '0', 'Q': '0',
    'I': '1', 'l': '1', 'i': '1', '|': '1', '!': '1', ']': '1', '[': '1',
    'Z': '2', 'z': '2',
    'S': '5', 's': '5',
    'G': '6', 'b': '6',
    'T': '7',
    'B': '8',
    'g': '9', 'q': '9',
  }

  def __init__(self, num_rows: int = 12, ocr_engine: Optional[Any] = None, template_dirs: Optional[List[str]] = None):
    self.num_rows = num_rows
    self.ocr = ocr_engine
    self.states: Dict[int, PlayerKillState] = {i: PlayerKillState() for i in range(num_rows)}
    self.template_bank: Dict[int, List[np.ndarray]] = {d: [] for d in range(10)}
    self.rr_cursor: int = 0
    self.frame_counter: int = 0
    self._build_template_bank(template_dirs or [])

  def reset(self):
    for st in self.states.values():
      st.reset()
    self.rr_cursor = 0
    self.frame_counter = 0

  @classmethod
  def _normalize_to_canvas(cls, mask_u8: np.ndarray) -> np.ndarray:
    h, w = mask_u8.shape[:2]
    if h == 0 or w == 0:
      return np.zeros((cls.CANVAS_H, cls.CANVAS_W), dtype=np.float32)

    target_h = cls.CANVAS_H - 4
    target_w = cls.CANVAS_W - 4
    scale = min(target_h / float(h), target_w / float(w))
    new_w = max(2, min(target_w, int(round(w * scale))))
    new_h = max(4, min(target_h, int(round(h * scale))))

    interp = cv2.INTER_AREA if scale < 1.0 else cv2.INTER_CUBIC
    resized = cv2.resize(mask_u8, (new_w, new_h), interpolation=interp)

    canvas = np.zeros((cls.CANVAS_H, cls.CANVAS_W), dtype=np.float32)
    x0 = (cls.CANVAS_W - new_w) // 2
    y0 = (cls.CANVAS_H - new_h) // 2
    canvas[y0:y0 + new_h, x0:x0 + new_w] = resized.astype(np.float32) / 255.0
    canvas = cv2.GaussianBlur(canvas, (3, 3), 0.7)
    return canvas

  def _draw_condensed_vector_digit(self, digit: int, variant: int = 0) -> np.ndarray:
    img = np.zeros((72, 48), dtype=np.uint8)
    t = 7 if variant == 0 else 6

    if digit == 0:
      cv2.ellipse(img, (24, 18), (13, 11), 0, 180, 360, 255, t, cv2.LINE_AA)
      cv2.ellipse(img, (24, 54), (13, 11), 0, 0, 180, 255, t, cv2.LINE_AA)
      cv2.line(img, (11, 18), (11, 54), 255, t, cv2.LINE_AA)
      cv2.line(img, (37, 18), (37, 54), 255, t, cv2.LINE_AA)
    elif digit == 1:
      cv2.line(img, (26, 8), (26, 64), 255, t, cv2.LINE_AA)
      if variant == 0:
        cv2.line(img, (17, 17), (26, 8), 255, t - 1, cv2.LINE_AA)
      else:
        cv2.line(img, (16, 15), (26, 9), 255, t - 1, cv2.LINE_AA)
        cv2.line(img, (16, 64), (35, 64), 255, t - 1, cv2.LINE_AA)
    elif digit == 2:
      cv2.ellipse(img, (24, 20), (13, 12), 0, 195, 360, 255, t, cv2.LINE_AA)
      cv2.line(img, (37, 20), (37, 25), 255, t, cv2.LINE_AA)
      cv2.line(img, (37, 25), (11, 62), 255, t, cv2.LINE_AA)
      cv2.line(img, (11, 63), (38, 63), 255, t, cv2.LINE_AA)
    elif digit == 3:
      cv2.ellipse(img, (23, 19), (13, 11), 0, 200, 360, 255, t, cv2.LINE_AA)
      cv2.ellipse(img, (23, 25), (13, 10), 0, 0, 90, 255, t, cv2.LINE_AA)
      cv2.line(img, (19, 35), (27, 35), 255, t, cv2.LINE_AA)
      cv2.ellipse(img, (23, 47), (14, 11), 0, 270, 360, 255, t, cv2.LINE_AA)
      cv2.ellipse(img, (23, 53), (14, 11), 0, 0, 165, 255, t, cv2.LINE_AA)
    elif digit == 4:
      if variant == 0:
        cv2.line(img, (32, 8), (32, 64), 255, t, cv2.LINE_AA)
        cv2.line(img, (31, 9), (9, 46), 255, t, cv2.LINE_AA)
        cv2.line(img, (9, 46), (39, 46), 255, t, cv2.LINE_AA)
      else:
        cv2.line(img, (12, 8), (12, 45), 255, t, cv2.LINE_AA)
        cv2.line(img, (12, 45), (38, 45), 255, t, cv2.LINE_AA)
        cv2.line(img, (32, 8), (32, 64), 255, t, cv2.LINE_AA)
    elif digit == 5:
      cv2.line(img, (12, 9), (37, 9), 255, t, cv2.LINE_AA)
      cv2.line(img, (12, 9), (12, 34), 255, t, cv2.LINE_AA)
      cv2.line(img, (12, 34), (27, 34), 255, t, cv2.LINE_AA)
      cv2.ellipse(img, (24, 49), (13, 15), 0, 270, 360, 255, t, cv2.LINE_AA)
      cv2.ellipse(img, (24, 51), (13, 13), 0, 0, 165, 255, t, cv2.LINE_AA)
    elif digit == 6:
      cv2.ellipse(img, (24, 20), (13, 12), 0, 180, 340, 255, t, cv2.LINE_AA)
      cv2.line(img, (11, 20), (11, 52), 255, t, cv2.LINE_AA)
      cv2.ellipse(img, (24, 48), (13, 15), 0, 0, 360, 255, t, cv2.LINE_AA)
    elif digit == 7:
      cv2.line(img, (10, 9), (38, 9), 255, t, cv2.LINE_AA)
      cv2.line(img, (37, 10), (18, 64), 255, t, cv2.LINE_AA)
    elif digit == 8:
      cv2.ellipse(img, (24, 21), (12, 13), 0, 0, 360, 255, t, cv2.LINE_AA)
      cv2.ellipse(img, (24, 49), (13, 15), 0, 0, 360, 255, t, cv2.LINE_AA)
    elif digit == 9:
      cv2.ellipse(img, (24, 24), (13, 15), 0, 0, 360, 255, t, cv2.LINE_AA)
      cv2.line(img, (37, 24), (37, 52), 255, t, cv2.LINE_AA)
      cv2.ellipse(img, (24, 52), (13, 12), 0, 0, 165, 255, t, cv2.LINE_AA)

    ys, xs = np.where(img > 40)
    if len(xs) == 0 or len(ys) == 0:
      return np.zeros((self.CANVAS_H, self.CANVAS_W), dtype=np.float32)
    crop = img[ys.min():ys.max() + 1, xs.min():xs.max() + 1]
    return self._normalize_to_canvas(crop)

  def _render_opencv_font_digit(self, digit: int, font_face: int, thickness: int, condense_x: float = 0.72) -> np.ndarray:
    canvas = np.zeros((90, 90), dtype=np.uint8)
    cv2.putText(canvas, str(digit), (18, 68), font_face, 2.0, 255, thickness, cv2.LINE_AA)
    ys, xs = np.where(canvas > 40)
    if len(xs) == 0 or len(ys) == 0:
      return np.zeros((self.CANVAS_H, self.CANVAS_W), dtype=np.float32)
    crop = canvas[ys.min():ys.max() + 1, xs.min():xs.max() + 1]
    if condense_x < 0.99 and digit != 1:
      ch, cw = crop.shape[:2]
      new_cw = max(3, int(round(cw * condense_x)))
      crop = cv2.resize(crop, (new_cw, ch), interpolation=cv2.INTER_AREA)
    return self._normalize_to_canvas(crop)

  def _build_template_bank(self, candidate_dirs: List[str]):
    tpl_dir = None
    for cd in candidate_dirs:
      if os.path.isdir(cd) and os.path.exists(os.path.join(cd, 'tpl_0.png')):
        tpl_dir = cd
        break

    for d in range(10):
      if tpl_dir is not None:
        p = os.path.join(tpl_dir, f'tpl_{d}.png')
        if os.path.exists(p):
          img = cv2.imread(p, cv2.IMREAD_GRAYSCALE)
          if img is not None and img.size > 0:
            ys, xs = np.where(img > 90)
            if len(xs) > 0 and len(ys) > 0:
              crop = img[ys.min():ys.max() + 1, xs.min():xs.max() + 1]
              self.template_bank[d].append(self._normalize_to_canvas(crop))

      self.template_bank[d].append(self._draw_condensed_vector_digit(d, variant=0))
      if d in (1, 4):
        self.template_bank[d].append(self._draw_condensed_vector_digit(d, variant=1))

      self.template_bank[d].append(self._render_opencv_font_digit(d, cv2.FONT_HERSHEY_SIMPLEX, 4, condense_x=0.72))
      self.template_bank[d].append(self._render_opencv_font_digit(d, cv2.FONT_HERSHEY_DUPLEX, 3, condense_x=0.74))

  def _structural_adjustments(self, bin_patch: np.ndarray, orig_w: int, orig_h: int) -> Dict[int, float]:
    adj = {d: 0.0 for d in range(10)}
    h, w = bin_patch.shape[:2]
    aspect = orig_w / float(max(1, orig_h))

    padded = cv2.copyMakeBorder(bin_patch, 2, 2, 2, 2, cv2.BORDER_CONSTANT, value=0)
    cnts, hier = cv2.findContours(padded, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_SIMPLE)

    holes = []
    if hier is not None and len(cnts) > 1:
      patch_area = float(max(1, h * w))
      for idx in range(len(cnts)):
        if hier[0][idx][3] != -1:
          area = cv2.contourArea(cnts[idx])
          hx, hy, hw, hh = cv2.boundingRect(cnts[idx])
          if area >= max(6.0, 0.018 * patch_area) and hh >= max(3, int(0.10 * h)):
            cy_rel = ((hy - 2) + hh / 2.0) / float(max(1, h))
            h_rel = hh / float(max(1, h))
            holes.append((cy_rel, h_rel, area / patch_area))

    num_holes = len(holes)

    grid = (cv2.resize(bin_patch, (18, 24), interpolation=cv2.INTER_AREA) > 100).astype(np.float32)
    top_left = float(np.mean(grid[0:7, 0:7]))
    top_bar = float(np.mean(grid[0:5, 3:15]))
    mid_left = float(np.mean(grid[7:17, 0:6]))
    mid_right = float(np.mean(grid[7:17, 12:18]))
    bot_left = float(np.mean(grid[17:24, 0:7]))
    bot_bar = float(np.mean(grid[19:24, 3:15]))
    upper_left_gap = float(np.mean(grid[5:11, 0:5]))
    lower_left_gap = float(np.mean(grid[13:19, 0:5]))
    upper_right_gap = float(np.mean(grid[5:11, 13:18]))
    center_core = float(np.mean(grid[7:17, 6:12]))

    if aspect <= 0.42:
      adj[1] += 0.35
      for d in (0, 2, 3, 4, 5, 6, 8, 9):
        adj[d] -= 0.25
    elif aspect >= 0.56:
      adj[1] -= 0.30

    if num_holes == 0:
      for d in (1, 2, 3, 5, 7):
        adj[d] += 0.10
      adj[8] -= 0.28
      adj[0] -= 0.22
    elif num_holes == 1:
      cy_rel, h_rel, _ = holes[0]
      adj[8] -= 0.12
      adj[1] -= 0.25
      adj[2] -= 0.14
      adj[3] -= 0.18
      adj[5] -= 0.14
      adj[7] -= 0.20

      if h_rel >= 0.42 and 0.36 <= cy_rel <= 0.64:
        if bot_left >= 0.25 and top_left >= 0.25 and center_core <= 0.18:
          adj[0] += 0.28
        else:
          adj[0] -= 0.18

      if cy_rel <= 0.56:
        adj[6] -= 0.16
        if bot_left <= 0.16 and bot_bar <= 0.28:
          adj[4] += 0.28
          adj[0] -= 0.32
          adj[9] -= 0.10
        if top_bar >= 0.45 and top_left >= 0.28:
          adj[9] += 0.16
          adj[4] -= 0.08
      else:
        adj[6] += 0.24
        adj[9] -= 0.18
        adj[4] -= 0.22
        adj[0] -= 0.14
    elif num_holes >= 2:
      adj[8] += 0.28
      for d in (1, 2, 3, 4, 5, 7):
        adj[d] -= 0.22
      adj[0] -= 0.18

    if upper_left_gap <= 0.16 and lower_left_gap <= 0.16 and mid_right >= 0.38:
      adj[3] += 0.20
      adj[8] -= 0.22
      adj[0] -= 0.24
      adj[6] -= 0.20
      adj[9] -= 0.14

    if bot_left <= 0.14 and bot_bar <= 0.30:
      adj[4] += 0.16
      adj[0] -= 0.24
      adj[2] -= 0.20
      adj[3] -= 0.12
      adj[6] -= 0.22
      adj[8] -= 0.22

    if top_bar >= 0.48 and mid_left <= 0.14 and bot_bar <= 0.28 and num_holes == 0:
      adj[7] += 0.18
      adj[2] -= 0.14
      adj[3] -= 0.10

    if upper_right_gap <= 0.16 and bot_bar >= 0.35:
      adj[6] += 0.12
      adj[8] -= 0.10
      adj[0] -= 0.12

    return adj

  def classify_digit_patch(self, gray_patch: np.ndarray, bin_patch: np.ndarray, orig_w: int, orig_h: int) -> Tuple[int, float]:
    if bin_patch is None or bin_patch.size == 0:
      return 0, 0.0

    canvas_bin = self._normalize_to_canvas(bin_patch)
    if float(np.std(canvas_bin)) < 1e-4:
      return 0, 0.0

    g_min, g_max = float(gray_patch.min()), float(gray_patch.max())
    if g_max - g_min > 10.0:
      soft_u8 = np.clip((gray_patch.astype(np.float32) - g_min) * (255.0 / (g_max - g_min)), 0, 255).astype(np.uint8)
      canvas_soft = self._normalize_to_canvas(soft_u8)
      use_soft = float(np.std(canvas_soft)) >= 1e-4
    else:
      canvas_soft = canvas_bin
      use_soft = False

    struct_adj = self._structural_adjustments(bin_patch, orig_w, orig_h)
    best_scores: Dict[int, float] = {}

    for d, tpls in self.template_bank.items():
      max_ncc = -1.0
      for tpl in tpls:
        if float(np.std(tpl)) < 1e-4:
          continue
        res_b = cv2.matchTemplate(canvas_bin, tpl, cv2.TM_CCOEFF_NORMED)
        val_b = float(res_b[0, 0]) if np.isfinite(res_b[0, 0]) else -1.0
        if use_soft:
          res_s = cv2.matchTemplate(canvas_soft, tpl, cv2.TM_CCOEFF_NORMED)
          val_s = float(res_s[0, 0]) if np.isfinite(res_s[0, 0]) else val_b
          val = 0.65 * val_b + 0.35 * val_s
        else:
          val = val_b
        if val > max_ncc:
          max_ncc = val
      best_scores[d] = max_ncc + struct_adj[d]

    ranked = sorted(best_scores.items(), key=lambda kv: kv[1], reverse=True)
    best_d, best_s = ranked[0]
    second_s = ranked[1][1] if len(ranked) > 1 else -1.0

    margin = max(0.0, best_s - second_s)
    conf = float(np.clip(0.55 * max(0.0, best_s) + 0.90 * min(0.5, margin), 0.0, 1.0))
    return best_d, conf

  def _ocr_verify_cluster(self, clean_bin_cluster: np.ndarray) -> Tuple[Optional[int], float]:
    if self.ocr is None or clean_bin_cluster is None or clean_bin_cluster.size == 0:
      return None, 0.0

    ch, cw = clean_bin_cluster.shape[:2]
    if ch < 4 or cw < 2:
      return None, 0.0

    target_h = 36
    target_w = max(8, int(round(cw * (target_h / float(ch)))))
    fg = cv2.resize(clean_bin_cluster, (target_w, target_h), interpolation=cv2.INTER_CUBIC)
    inv = 255 - fg
    padded = cv2.copyMakeBorder(inv, 18, 18, 22, 22, cv2.BORDER_CONSTANT, value=255)
    padded_bgr = cv2.cvtColor(padded, cv2.COLOR_GRAY2BGR)

    res = None
    try:
      res, _ = self.ocr(padded_bgr, use_det=False, use_cls=False, use_rec=True)
    except TypeError:
      try:
        res, _ = self.ocr(padded_bgr)
      except Exception:
        return None, 0.0
    except Exception:
      return None, 0.0

    if not res:
      return None, 0.0

    raw_txt = ""
    score = 0.0
    first = res[0]
    if isinstance(first, (list, tuple)):
      if len(first) == 2 and isinstance(first[0], str):
        raw_txt, score = first[0], float(first[1])
      elif len(first) >= 3 and isinstance(first[1], str):
        raw_txt, score = first[1], float(first[2])

    cleaned = ""
    for ch_c in raw_txt.strip():
      if ch_c.isdigit():
        cleaned += ch_c
      elif ch_c in self.OCR_CHAR_MAP:
        cleaned += self.OCR_CHAR_MAP[ch_c]

    if not cleaned or len(cleaned) > 2:
      return None, 0.0

    val = int(cleaned)
    if val < 0 or val > 45:
      return None, 0.0
    return val, score

  def _extract_row_observation(
    self,
    frame: np.ndarray,
    s2_coords: Tuple[int, int, int, int],
    row_idx: int
  ) -> Tuple[Optional[int], float, Optional[np.ndarray]]:
    fh, fw = frame.shape[:2]
    sx0, sy0, sx1, sy1 = s2_coords
    sx0 = max(0, min(fw - 1, sx0))
    sx1 = max(sx0 + 2, min(fw, sx1))
    sy0 = max(0, min(fh - 1, sy0))
    sy1 = max(sy0 + self.num_rows, min(fh, sy1))

    s2_h = sy1 - sy0
    s2_w = sx1 - sx0
    row_h = s2_h / float(self.num_rows)

    own_y0 = sy0 + row_idx * row_h
    own_y1 = sy0 + (row_idx + 1) * row_h

    pad_y = max(3, int(round(row_h * 0.20)))
    ext_y0 = max(0, int(np.floor(own_y0)) - pad_y)
    ext_y1 = min(fh, int(np.ceil(own_y1)) + pad_y)

    row_bgr = frame[ext_y0:ext_y1, sx0:sx1]
    if row_bgr.size == 0:
      return None, 0.0, None

    scale = 3
    up_bgr = cv2.resize(row_bgr, (s2_w * scale, (ext_y1 - ext_y0) * scale), interpolation=cv2.INTER_CUBIC)
    up_gray = cv2.cvtColor(up_bgr, cv2.COLOR_BGR2GRAY)
    up_hsv = cv2.cvtColor(up_bgr, cv2.COLOR_BGR2HSV)

    bg_val = float(np.percentile(up_gray, 25))
    sat = up_hsv[:, :, 1]
    colored_icon_mask = (sat > 90)
    clean_gray = up_gray.copy()
    clean_gray[colored_icon_mask] = int(bg_val)

    rel_own_y0 = (own_y0 - ext_y0) * scale
    rel_own_y1 = (own_y1 - ext_y0) * scale
    iy0 = max(0, int(round(rel_own_y0)))
    iy1 = min(clean_gray.shape[0], int(round(rel_own_y1)))
    core_gray = clean_gray[iy0:iy1, :]
    if core_gray.size == 0:
      return None, 0.0, None

    local_bg = float(np.percentile(core_gray, 25))
    local_fg = float(np.percentile(core_gray, 98.5))
    contrast = local_fg - local_bg
    if contrast < 20.0:
      return None, 0.0, None

    thr_val = local_bg + 0.46 * contrast
    thr_val = max(local_bg + 15.0, min(local_fg - 10.0, thr_val))
    bin_mask = (clean_gray >= thr_val).astype(np.uint8) * 255

    cnts, _ = cv2.findContours(bin_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    up_row_h = row_h * scale
    up_w = s2_w * scale

    min_h = max(8.0, 0.34 * up_row_h)
    max_h = 0.88 * up_row_h
    min_w = max(4.0, 0.06 * up_row_h)
    max_w = 0.78 * up_row_h

    candidates = []
    for c in cnts:
      bx, by, bw, bh = cv2.boundingRect(c)
      if bh < min_h or bh > max_h or bw < min_w or bw > max_w:
        continue
      ar = bh / float(max(1, bw))
      if ar < 0.95 or ar > 6.5:
        continue
      cy = by + bh * 0.5
      if cy < rel_own_y0 or cy >= rel_own_y1:
        continue
      if (bx <= 1 or (bx + bw) >= up_w - 1) and bw < 0.18 * up_row_h:
        continue
      fill = cv2.contourArea(c) / float(max(1, bw * bh))
      if fill < 0.14:
        continue
      candidates.append((bx, by, bw, bh))

    if not candidates:
      return None, 0.0, None

    candidates.sort(key=lambda b: b[0])

    while len(candidates) > 1:
      b0 = candidates[0]
      b1 = candidates[1]
      gap = b1[0] - (b0[0] + b0[2])
      if gap > 0.45 * up_row_h or (up_w > 1.45 * up_row_h and b0[0] < 0.25 * up_w and gap > 0.22 * up_row_h):
        candidates.pop(0)
      else:
        break

    if len(candidates) > 2:
      candidates = candidates[-2:]

    if len(candidates) == 2:
      b0, b1 = candidates[0], candidates[1]
      gap = b1[0] - (b0[0] + b0[2])
      h_ratio = min(b0[3], b1[3]) / float(max(b0[3], b1[3]))
      if gap > 0.45 * up_row_h or h_ratio < 0.72:
        center_x = up_w * 0.55
        candidates = [min(candidates, key=lambda b: abs((b[0] + b[2] * 0.5) - center_x))]

    digits = []
    confs = []
    for bx, by, bw, bh in candidates:
      g_patch = clean_gray[by:by + bh, bx:bx + bw]
      b_patch = bin_mask[by:by + bh, bx:bx + bw]
      d, c_score = self.classify_digit_patch(g_patch, b_patch, bw, bh)
      digits.append(d)
      confs.append(c_score)

    if not digits:
      return None, 0.0, None

    detected_val = int("".join(str(d) for d in digits))
    min_conf = float(min(confs))

    cx0 = min(b[0] for b in candidates)
    cy0 = min(b[1] for b in candidates)
    cx1 = max(b[0] + b[2] for b in candidates)
    cy1 = max(b[1] + b[3] for b in candidates)
    cluster_mask = bin_mask[cy0:cy1, cx0:cx1]

    return detected_val, min_conf, cluster_mask

  def process_frame(
    self,
    frame: np.ndarray,
    s2_coords: Tuple[int, int, int, int]
  ) -> List[Dict[str, Any]]:
    self.frame_counter += 1
    observations = []
    valid_rows = 0

    for i in range(self.num_rows):
      raw_val, conf, cluster_mask = self._extract_row_observation(frame, s2_coords, i)
      observations.append((raw_val, conf, cluster_mask))
      if raw_val is not None:
        valid_rows += 1

    if valid_rows < 4:
      return [
        {
          'kills': self.states[i].confirmed_kills,
          'raw': None,
          'conf': 0.0,
          'locked': self.states[i].initialized
        }
        for i in range(self.num_rows)
      ]

    ocr_budget = 2 if self.ocr is not None else 0
    ocr_targets = set()

    if ocr_budget > 0:
      for i in range(self.num_rows):
        raw_val, conf, cluster_mask = observations[i]
        if raw_val is None or cluster_mask is None:
          continue
        st = self.states[i]
        needs_check = (
          (not st.initialized and raw_val > 0) or
          (st.initialized and raw_val != st.confirmed_kills) or
          (conf < 0.68)
        )
        if needs_check:
          ocr_targets.add(i)
          if len(ocr_targets) >= ocr_budget:
            break

      if len(ocr_targets) < ocr_budget:
        for _ in range(self.num_rows):
          idx = self.rr_cursor % self.num_rows
          self.rr_cursor += 1
          if idx not in ocr_targets and observations[idx][2] is not None:
            ocr_targets.add(idx)
            if len(ocr_targets) >= ocr_budget:
              break

    results = []
    for i in range(self.num_rows):
      raw_val, conf, cluster_mask = observations[i]
      ocr_val, ocr_conf = None, 0.0
      if i in ocr_targets and cluster_mask is not None:
        ocr_val, ocr_conf = self._ocr_verify_cluster(cluster_mask)

      confirmed = self.states[i].update(raw_val, conf, ocr_val=ocr_val, ocr_conf=ocr_conf)
      results.append({
        'kills': confirmed,
        'raw': raw_val,
        'conf': conf,
        'locked': self.states[i].initialized
      })

    return results


class ThreadedScoreboardDetector:
  """
  High-Performance Asynchronous Free Fire Scoreboard AI Tracker:
  - Lobby Registration -> Match Lock ('l' key): Scroll through all teams in the lobby
    to register them permanently, then press 'l' to lock the roster for the match.
  - Zero Duplicates: Canonical color keying updates existing teams in-place on return.
  - Permanent Dead Teams: Eliminated squads stay on the leaderboard at 0 alive / 0.0 HP [DEAD].
  - 12-Team OpenCV Leaderboard: Displays up to 12 tracked teams simultaneously on screen.
  """
  def __init__(
    self,
    server_url: str = "http://localhost:3001",
    sync_interval: float = 1.2,
    max_display_teams: int = 12,
    stream_id: str = "default",
    write_local_json: bool = True,
    calibration_file: Optional[str] = None
  ):
    os.environ['NO_PROXY'] = 'localhost,127.0.0.1'
    os.environ['no_proxy'] = 'localhost,127.0.0.1'
    self.server_url = server_url.replace("localhost", "127.0.0.1")
    self.sync_interval = sync_interval
    self.max_display_teams = max(1, int(max_display_teams))
    self.stream_id = (stream_id or "default").strip() or "default"
    self.write_local_json = bool(write_local_json)
    self.calibration_file = calibration_file
    self.project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
    self.color_engine = BadgeColorEngine(vote_window=9, lock_threshold=5)

    self.http_opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    self._ensure_server_running()

    self.ocr = RapidOCR() if RapidOCR is not None else None

    self.slot1_norm = [0.693, 0.075, 0.889, 0.968]
    self.slot2_norm = [0.879, 0.075, 0.945, 0.968]
    self._load_saved_calibration()

    base_dir = os.path.dirname(__file__)
    tpl_dirs = [
      os.path.join(base_dir, 'templates'),
      os.path.join(base_dir, '..', 'templates'),
      r"C:\Users\ASUS\OneDrive\Desktop\Esport\live_analytics_leaderboard\vision-engine\templates"
    ]
    self.kill_engine = KillCountEngine(num_rows=12, ocr_engine=self.ocr, template_dirs=tpl_dirs)

    self.cached_player_names = {}
    self.cached_team_colors = {}
    self.squad_locks = {}
    self.has_initial_roster = False
    self.ocr_attempts = 0

    # Persistent team memory across scoreboard scrolls: canonical colorName -> team dict
    self.persistent_teams: Dict[str, Dict[str, Any]] = {}
    self.roster_locked: bool = False  # False = Lobby Registration, True = Match Locked
    self.prev_slot1_small: Optional[np.ndarray] = None
    self.scroll_settling_frames: int = 0
    self.scroll_diff_threshold: float = 14.0

    self.hp_pipeline = None
    try:
      sys.path.append(os.path.abspath(self.project_root))
      sys.path.append(os.path.abspath(os.path.join(self.project_root, '..')))
      from hp_tracker.core.hp_pipeline import HPTrackerPipeline
      self.hp_pipeline = HPTrackerPipeline()
      print("[HPTracker] Dark-Masked Health Bar Pipeline initialized successfully.")
    except Exception as e:
      print(f"[HPTracker Info] HP Pipeline not active: {e}")

    self.running = True
    self.lock = threading.Lock()
    self.current_frame = None
    self.latest_result = None
    self.fps_display = 30.0
    self.total_synced_events = 0
    self.last_sync_time = 0.0
    self.last_synced_total_kills = -1

    self.worker_thread = threading.Thread(target=self._ai_worker_loop, daemon=True)
    self.worker_thread.start()

  def reset_kill_tracker(self):
    with self.lock:
      self.kill_engine.reset()
      self.last_synced_total_kills = -1

  def clear_persistent_teams(self):
    """Clears all stored teams and unlocks back to Lobby Registration Mode."""
    with self.lock:
      self.persistent_teams.clear()
      self.roster_locked = False
      self.kill_engine.reset()
      self.color_engine.reset_cache()
      self.squad_locks.clear()
      self.cached_player_names.clear()
      self.last_synced_total_kills = -1
    print("[Leaderboard] Cleared teams -> LOBBY REGISTRATION MODE.", flush=True)

  def toggle_roster_lock(self):
    """Locks registered lobby teams for the match (press 'l')."""
    with self.lock:
      self.roster_locked = not self.roster_locked
      state = "MATCH LOCKED" if self.roster_locked else "LOBBY REGISTRATION"
      print(f"[Leaderboard] Mode -> {state} ({len(self.persistent_teams)} teams registered)", flush=True)

  def _resolve_calibration_path(self, for_save: bool = False) -> str:
    if self.calibration_file:
      return self.calibration_file if os.path.isabs(self.calibration_file) else os.path.join(self.project_root, self.calibration_file)
    default_path = os.path.join(self.project_root, 'slot_calibration.json')
    if self.stream_id != "default":
      stream_path = os.path.join(self.project_root, f'slot_calibration_{self.stream_id}.json')
      if for_save or os.path.exists(stream_path):
        return stream_path
    return default_path

  def _load_saved_calibration(self):
    calib_file = self._resolve_calibration_path(for_save=False)
    if os.path.exists(calib_file):
      try:
        with open(calib_file, 'r', encoding='utf-8') as f:
          data = json.load(f)
          if 'slot1' in data and 'slot2' in data:
            self.slot1_norm = data['slot1']
            self.slot2_norm = data['slot2']
            print(f"[Calibration:{self.stream_id}] Loaded saved slots from {os.path.basename(calib_file)}")
      except Exception:
        pass

  def _save_calibration(self):
    calib_file = self._resolve_calibration_path(for_save=True)
    try:
      with open(calib_file, 'w', encoding='utf-8') as f:
        json.dump({'slot1': self.slot1_norm, 'slot2': self.slot2_norm}, f, indent=2)
      print(f"[Calibration:{self.stream_id}] Saved slots to {os.path.basename(calib_file)}")
    except Exception:
      pass

  def _ensure_server_running(self):
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
        print("[AutoServer] Port 3001 is not active. Auto-starting Node.js server...")
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

  def extract_exact_badge_color(self, badge_bgr: np.ndarray) -> Tuple[str, str]:
    if badge_bgr is None or badge_bgr.size == 0:
      return "UNKNOWN", "#888888"

    inner = self.color_engine._crop_badge_interior(badge_bgr)
    hsv = cv2.cvtColor(inner, cv2.COLOR_BGR2HSV)
    sat = hsv[:, :, 1]
    val = hsv[:, :, 2]

    b_ch = inner[:, :, 0].astype(np.int16)
    g_ch = inner[:, :, 1].astype(np.int16)
    r_ch = inner[:, :, 2].astype(np.int16)
    spread = np.maximum(np.maximum(b_ch, g_ch), r_ch) - np.minimum(np.minimum(b_ch, g_ch), r_ch)

    total_px = max(1, inner.shape[0] * inner.shape[1])
    chroma_mask = (sat >= 105) & (val >= 65) & (spread >= 42)
    fg_count = int(np.count_nonzero(chroma_mask))
    if fg_count < 10 or (fg_count / float(total_px)) < 0.16:
      return "GRAY", "#9EA7B0"

    hues = hsv[:, :, 0][chroma_mask].astype(int) * 2
    med_hue = int(np.median(hues))
    med_sat = float(np.median(sat[chroma_mask]))
    med_val = float(np.median(val[chroma_mask]))
    med_spread = float(np.median(spread[chroma_mask]))

    if med_hue >= 345 or med_hue <= 18:
      return "RED", "#FF2A2A"
    elif 19 <= med_hue <= 50 and med_val < 175:
      return "BROWN", self.color_engine.hex_map.get("BROWN", "#8A631A")
    elif 19 <= med_hue <= 42:
      return "ORANGE", "#FF7F00"
    elif 43 <= med_hue <= 70:
      return "YELLOW", "#FFD700"
    elif 71 <= med_hue <= 149:
      return "GREEN", "#00D860"
    elif 150 <= med_hue <= 168:
      return "MINT GREEN", self.color_engine.hex_map.get("MINT GREEN", "#5ED4AA")
    elif 169 <= med_hue <= 245:
      if med_sat < 115.0 or med_spread < 48.0:
        return "GRAY", "#9EA7B0"
      return ("CYAN", "#00E5FF") if med_hue <= 200 else ("BLUE", "#1E4BFF")
    elif 246 <= med_hue <= 295:
      return "PURPLE", "#8A2BE2"
    elif 296 <= med_hue <= 344:
      return "PINK", "#FF2E93"

    return "GRAY", "#9EA7B0"

  def stop(self):
    self.running = False

  def get_slot_pixels(self, frame: np.ndarray) -> Tuple[Tuple[int, int, int, int], Tuple[int, int, int, int]]:
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
      self.ocr_attempts = 0
      self.cached_player_names.clear()
      self.color_engine.reset_cache()
      self.squad_locks.clear()
      self.prev_slot1_small = None
      self.reset_kill_tracker()

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
      self.reset_kill_tracker()
      self._save_calibration()

  def _detect_scoreboard_scroll(self, slot1_bgr: np.ndarray) -> bool:
    """
    Detects when the spectator scrolls the scoreboard list up or down.
    On scroll, resets row-level kill & color caches so old rows don't bleed into new teams,
    while keeping `self.persistent_teams` completely intact.
    """
    gray = cv2.cvtColor(slot1_bgr, cv2.COLOR_BGR2GRAY)
    small = cv2.resize(gray, (32, 120), interpolation=cv2.INTER_AREA)

    if self.prev_slot1_small is None:
      self.prev_slot1_small = small
      return False

    mean_diff = float(np.mean(cv2.absdiff(small, self.prev_slot1_small)))
    self.prev_slot1_small = small

    if mean_diff >= self.scroll_diff_threshold:
      # Scroll motion detected: reset row-indexed state and wait 6 ticks to settle cleanly
      self.scroll_settling_frames = 6
      self.kill_engine.reset()
      self.color_engine.reset_cache()
      self.squad_locks.clear()
      self.cached_player_names.clear()
      self.has_initial_roster = False
      self.ocr_attempts = 0
      return True

    return False

  def _ai_worker_loop(self):
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

        # Scroll Guard: detect scoreboard scroll and allow rows to settle cleanly
        is_moving = self._detect_scoreboard_scroll(slot1)
        if is_moving:
          time.sleep(0.05)
          continue

        s1_h, s1_w = slot1.shape[:2]
        squad_size = 4
        num_squads = 3
        num_rows = num_squads * squad_size  # 12 rows
        row_height = s1_h / float(num_rows)

        ocr_results = []
        if (not self.has_initial_roster or len(self.cached_player_names) < 4) and self.ocr is not None and self.ocr_attempts < 2 and s1_w >= 80:
          self.ocr_attempts += 1
          try:
            ocr_results, _ = self.ocr(slot1)
            if ocr_results:
              self.has_initial_roster = True
          except Exception:
            pass

        kill_outputs = self.kill_engine.process_frame(frame, s2_coords)

        # Pass 1: Extract row-level features
        raw_players = []
        bg_lab = self.color_engine.estimate_hud_background_lab(slot1)
        for i in range(num_rows):
          y_start = int(i * row_height)
          y_end = int((i + 1) * row_height)
          if y_end > s1_h:
            break
          y_center = (y_start + y_end) / 2.0

          name_zone = frame[
            s1_coords[1] + y_start : s1_coords[1] + y_end,
            s1_coords[2] + 4 : min(frame.shape[1], s1_coords[2] + int(0.18 * frame.shape[1]))
          ]
          if name_zone.size > 0:
            name_gray = cv2.cvtColor(name_zone, cv2.COLOR_BGR2GRAY)
            is_alive = bool(name_gray.max() >= 150 and np.percentile(name_gray, 95) >= 95)
          else:
            is_alive = True

          badge_crop = slot1[y_start + 2: max(y_start + 3, y_end - 2), :]

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

          k_info = kill_outputs[i] if i < len(kill_outputs) else {'kills': 0, 'locked': False, 'conf': 0.0}
          kills = int(k_info['kills'])

          raw_players.append({
            'slot': i + 1,
            'squad_idx': i // squad_size,
            'slot_in_squad': (i % squad_size) + 1,
            'badge_crop': badge_crop,
            'name': player_name,
            'alive': is_alive,
            'kills': kills,
            'kill_locked': bool(k_info.get('locked', False)),
            'y_center': y_center,
            'y_range': (y_start, y_end)
          })

        # Pass 2: Squad-Level Color Consensus
        squad_drafts = []
        for sq_idx in range(num_squads):
          squad_rows = [p for p in raw_players if p['squad_idx'] == sq_idx]
          if not squad_rows:
            continue

          alive_rows = [p for p in squad_rows if p['alive']]
          sq_color = "UNKNOWN"
          sq_hex = "#888888"
          sq_chroma = 0.0

          if alive_rows:
            votes = []
            chroma_vals = []
            for r in alive_rows:
              c_name, c_hex = self.color_engine.extract_row_color(
                r['badge_crop'], bg_lab, slot_idx=(sq_idx * 4) + r['slot_in_squad'], is_alive=True
              )
              v_ratio, m_sat, m_spread = self.color_engine.measure_badge_chroma(r['badge_crop'])
              chroma_vals.append(v_ratio * m_sat)
              if c_name not in ("UNKNOWN", "DIMMED"):
                votes.append((c_name, c_hex))
            if chroma_vals:
              sq_chroma = float(np.median(chroma_vals))
            if votes:
              winner_name, _ = Counter([v[0] for v in votes]).most_common(1)[0]
              sq_color = winner_name
              sq_hex = self.color_engine.hex_map.get(winner_name, "#9EA7B0")
              self.squad_locks[sq_idx] = (sq_color, sq_hex)

          if sq_color in ("UNKNOWN", "DIMMED"):
            if sq_idx in self.squad_locks:
              sq_color, sq_hex = self.squad_locks[sq_idx]
            else:
              sq_color = "GRAY"
              sq_hex = self.color_engine.hex_map["GRAY"]

          squad_drafts.append({
            'sq_idx': sq_idx,
            'rows': squad_rows,
            'color': sq_color,
            'hex': sq_hex,
            'chroma': sq_chroma,
          })

        # Pass 2B: Anti-Merge Duplicate Color Resolution across visible squads
        color_groups: Dict[str, List[Dict[str, Any]]] = {}
        for d in squad_drafts:
          color_groups.setdefault(d['color'], []).append(d)

        used_colors = set(d['color'] for d in squad_drafts)
        for col_name, group in color_groups.items():
          if len(group) <= 1:
            continue
          group.sort(key=lambda g: g['chroma'], reverse=True)
          for loser in group[1:]:
            if "GRAY" not in used_colors and loser['chroma'] < 45.0:
              loser['color'] = "GRAY"
              loser['hex'] = self.color_engine.hex_map["GRAY"]
              used_colors.add("GRAY")
              self.squad_locks[loser['sq_idx']] = ("GRAY", loser['hex'])
            else:
              # Do NOT create "TEAM COLOR #2" duplicates in persistent memory
              loser['skip_persist'] = True

        # Pass 3: Build currently visible player & team structures
        parsed_players = []
        visible_teams: Dict[str, Dict[str, Any]] = {}
        for d in squad_drafts:
          squad_rows = d['rows']
          sq_color = d['color']
          sq_hex = d['hex']
          team_display = f"TEAM {sq_color}"

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

          # Skip transient duplicate-color collisions so they never pollute persistent_teams
          if d.get('skip_persist') or sq_color in ("UNKNOWN", "DIMMED"):
            continue

          sq_kills = sum(p['kills'] for p in squad_rows)
          sq_alive = sum(1 for p in squad_rows if p['alive'])

          # Canonical key = sq_color (guarantees 1 entry per team, updates in place on return)
          color_slug = sq_color.lower().replace(' ', '-')
          team_id = f"{self.stream_id}-team-{color_slug}" if self.stream_id != "default" else f"team-{color_slug}"
          visible_teams[sq_color] = {
            'id': team_id,
            'streamId': self.stream_id,
            'name': team_display,
            'color': sq_hex,
            'colorName': sq_color,
            'kills': sq_kills,
            'alive': sq_alive,
            'isVisible': True,
            'lastSeen': now,
            'players': [{
              'slot': p['slot'],
              'name': p['name'],
              'kills': p['kills'],
              'alive': p['alive'],
              'color': p['color'],
              'hex': p['hex'],
              'hp': p.get('hp', 100.0 if p['alive'] else 0.0)
            } for p in squad_rows]
          }

        # Pass 3B: Lobby Registration & Match-Locked In-Place Updates
        if self.scroll_settling_frames > 0:
          self.scroll_settling_frames -= 1
        else:
          for t_key, t_obj in self.persistent_teams.items():
            if t_key not in visible_teams:
              t_obj['isVisible'] = False

          for t_key, t_obj in visible_teams.items():
            # If roster is locked or stream team cap reached, ignore unregistered/phantom colors
            if t_key not in self.persistent_teams:
              if self.roster_locked or len(self.persistent_teams) >= self.max_display_teams:
                continue

            # If team is completely dead (0 alive), NEVER remove it: force all players to 0 HP & DEAD
            if t_obj['alive'] == 0:
              t_obj['eliminated'] = True
              for pl in t_obj['players']:
                pl['alive'] = False
                pl['hp'] = 0.0
                pl['color'] = 'DEAD'
                pl['hex'] = '#555555'
            else:
              t_obj['eliminated'] = False

            # Preserve previous kills if a dead/dimmed team briefly reads lower
            if t_key in self.persistent_teams:
              prev = self.persistent_teams[t_key]
              if t_obj['alive'] == 0 and t_obj['kills'] < prev['kills']:
                t_obj['kills'] = prev['kills']

            # Update existing team in-place (or register new team in Lobby Mode)
            self.persistent_teams[t_key] = t_obj

        # Build unified ranked leaderboard from all persistent teams (live + scrolled-off + dead)
        ranked_teams = [dict(t) for t in self.persistent_teams.values()]
        ranked_teams.sort(key=lambda t: (t['kills'], t['alive']), reverse=True)
        for rank_idx, t in enumerate(ranked_teams):
          t['rank'] = rank_idx + 1

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

        total_k = sum(t['kills'] for t in ranked_teams)
        kill_event_changed = (self.last_synced_total_kills != -1 and total_k != self.last_synced_total_kills)

        if (now - self.last_sync_time >= self.sync_interval) or (self.total_synced_events == 0 and len(ranked_teams) > 0) or kill_event_changed:
          self.last_sync_time = now
          self.last_synced_total_kills = total_k
          self.total_synced_events += 1

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

          if self.write_local_json:
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

          try:
            payload = json.dumps({
              'matchId': 'ffws-live-match',
              'streamId': self.stream_id,
              'teams': ranked_teams
            }).encode('utf-8')
            req = urllib.request.Request(
              f"{self.server_url}/api/scoreboard/sync",
              data=payload,
              headers={'Content-Type': 'application/json'},
              method='POST'
            )
            with self.http_opener.open(req, timeout=1.5) as resp:
              if self.total_synced_events % 5 == 1 or self.total_synced_events <= 3 or kill_event_changed:
                print(f"[VisionEngine:{self.stream_id}] Synced #{self.total_synced_events}: {len(ranked_teams)} teams to backend (Kills: {total_k}, Alive: {total_a})", flush=True)
          except Exception as e:
            if self.total_synced_events % 10 == 1:
              print(f"[VisionEngine:{self.stream_id} Sync Warning] {e}. Ensure Node server is running on port 3001.", flush=True)

        time.sleep(0.05)
      except Exception as e:
        print(f"[_ai_worker_loop Error] {e}", flush=True)
        time.sleep(0.1)

  def feed_frame(self, frame: np.ndarray):
    with self.lock:
      self.current_frame = frame

  def draw_visual_overlay(self, frame: np.ndarray) -> np.ndarray:
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

    s1 = res.get('s1_coords', (0, 0, 0, 0))
    s2 = res.get('s2_coords', (0, 0, 0, 0))
    s2_row_h = max(1.0, (s2[3] - s2[1]) / 12.0)

    cv2.rectangle(preview, (s1[0], s1[1]), (s1[2], s1[3]), (0, 255, 0), 2)
    cv2.putText(preview, "SLOT 1: TEAMS & PLAYERS", (s1[0], max(20, s1[1] - 8)),
                cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 255, 0), 1, cv2.LINE_AA)

    cv2.rectangle(preview, (s2[0], s2[1]), (s2[2], s2[3]), (0, 230, 255), 2)
    cv2.putText(preview, "SLOT 2: KILLS", (s2[0] - 15, max(20, s2[1] - 8)),
                cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 230, 255), 1, cv2.LINE_AA)

    for idx_p, p in enumerate(res.get('parsed_players', [])):
      y0, y1 = p.get('y_range', (0, 0))
      y_center = p.get('y_center', (y0 + y1) / 2.0)
      y_abs = s1[1] + int(y_center)

      dot_x = s1[0] + 12
      if p['alive']:
        color_bgr = self.color_engine.hex_to_bgr(p.get('hex', '#00E5FF'))
        cv2.circle(preview, (dot_x, y_abs), 5, color_bgr, -1)
        cv2.circle(preview, (dot_x, y_abs), 5, (255, 255, 255), 1)
        cv2.rectangle(preview, (s1[0], s1[1] + y0), (s1[2], s1[1] + y1), (0, 200, 0), 1)
        text_color = (255, 255, 255)
        status_txt = f"{p['name']} ({p['kills']}k)"
      else:
        cv2.circle(preview, (dot_x, y_abs), 5, (55, 55, 55), -1)
        cv2.circle(preview, (dot_x, y_abs), 5, (95, 95, 95), 1)
        cv2.rectangle(preview, (s1[0], s1[1] + y0), (s1[2], s1[1] + y1), (45, 45, 45), 1)
        text_color = (110, 110, 110)
        status_txt = f"{p['name']} ({p['kills']}k) [DEAD]"

      cv2.putText(preview, status_txt, (s1[0] + 25, y_abs + 4),
                  cv2.FONT_HERSHEY_SIMPLEX, 0.42, text_color, 1, cv2.LINE_AA)

      k_y = s2[1] + int((idx_p + 0.5) * s2_row_h) + 4
      k_x = max(0, s2[0] - 26)
      k_col = (0, 255, 120) if p.get('kill_locked', False) else (0, 220, 255)
      cv2.putText(preview, f"{p['kills']}", (k_x, k_y),
                  cv2.FONT_HERSHEY_SIMPLEX, 0.44, k_col, 1, cv2.LINE_AA)

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

    # 12-Team Persistent Leaderboard Sidebar (Lobby Registration & Match-Locked Mode)
    display_teams = teams[:self.max_display_teams]
    row_step = 22
    panel_w = 365
    panel_h = 38 + (max(1, len(display_teams)) * row_step)
    cv2.rectangle(preview, (15, 44), (15 + panel_w, 44 + panel_h), (20, 14, 32), -1)
    cv2.rectangle(preview, (15, 44), (15 + panel_w, 44 + panel_h), (120, 80, 180), 1)

    mode_tag = "LOCKED" if self.roster_locked else "LOBBY ['l' LOCK]"
    cv2.putText(
      preview,
      f"LEADERBOARD ({len(teams)} TEAMS) | {mode_tag}",
      (25, 64),
      cv2.FONT_HERSHEY_SIMPLEX, 0.42, (0, 255, 140) if self.roster_locked else (0, 230, 255), 1, cv2.LINE_AA
    )

    for idx, t in enumerate(display_teams):
      y_pos = 86 + (idx * row_step)
      t_bgr = self.color_engine.hex_to_bgr(t['color'])
      is_vis = t.get('isVisible', True)
      is_dead = (t.get('alive', 0) == 0)

      cv2.rectangle(preview, (25, y_pos - 10), (32, y_pos + 3), (65, 65, 65) if is_dead else t_bgr, -1)
      if is_dead:
        txt_col = (110, 110, 115)
        tag = " [DEAD]"
      else:
        txt_col = (255, 255, 255) if is_vis else (175, 180, 195)
        tag = "" if is_vis else " [SAVED]"

      row_str = f"#{t['rank']:<2} {t['name']:15s} {t['kills']}K ({t['alive']} alive){tag}"
      cv2.putText(preview, row_str, (38, y_pos),
                  cv2.FONT_HERSHEY_SIMPLEX, 0.40, txt_col, 1, cv2.LINE_AA)

    hp_res = res.get('hp_result')
    if hp_res and self.hp_pipeline is not None:
      preview = self.hp_pipeline.draw_debug_overlay(preview, hp_res, show_canvas_preview=True)

    return preview


def wait_for_stream_barrier(
  server_url: str,
  http_opener: urllib.request.OpenerDirector,
  stream_id: str,
  expected_peers: int,
  timeout: float = 15.0
):
  """Block briefly until all expected peer streams finish warm-up so frame 0 aligns."""
  if expected_peers <= 1:
    return
  deadline = time.time() + max(1.0, timeout)
  payload = json.dumps({'streamId': stream_id, 'expected': expected_peers}).encode('utf-8')
  print(f"[Barrier:{stream_id}] Warm-up ready, waiting for {expected_peers} peer stream(s)...", flush=True)
  while time.time() < deadline:
    try:
      req = urllib.request.Request(
        f"{server_url}/api/streams/barrier",
        data=payload,
        headers={'Content-Type': 'application/json'},
        method='POST'
      )
      with http_opener.open(req, timeout=1.0) as resp:
        data = json.loads(resp.read().decode('utf-8'))
        if data.get('ready'):
          print(f"[Barrier:{stream_id}] All {expected_peers} stream(s) ready. Starting frame loop!", flush=True)
          return
    except Exception:
      pass
    time.sleep(0.025)
  print(f"[Barrier:{stream_id}] Barrier timeout ({timeout:.1f}s) reached; starting stream immediately.", flush=True)


def run_live_scoreboard(
  source: str = "image",
  server_url: str = "http://localhost:3001",
  sync_gap: float = 1.2,
  display: bool = True,
  calibrate: bool = False,
  stream_id: str = "default",
  max_teams: int = 12,
  write_local_json: bool = True,
  calibration_file: Optional[str] = None,
  sync_peers: int = 1,
  barrier_timeout: float = 15.0
):
  print("=" * 72, flush=True)
  print(f" FREE FIRE LIVE SCOREBOARD VISION TRACKER [{stream_id}] (ASYNC 60 FPS ENGINE)", flush=True)
  print(f" Source: {source} | Max Teams: {max_teams} | Sync Cadence: {sync_gap}s | Backend: {server_url}", flush=True)
  print("=" * 72, flush=True)

  detector = ThreadedScoreboardDetector(
    server_url=server_url,
    sync_interval=sync_gap,
    max_display_teams=max_teams,
    stream_id=stream_id,
    write_local_json=write_local_json,
    calibration_file=calibration_file
  )

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
        print("[Error] Failed to load any input image or fallback video.")
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

  if not is_image and (cap is None or not cap.isOpened()):
    print(f"[Error:{stream_id}] Failed to open video/camera source: {source}", flush=True)
    detector.running = False
    return

  if calibrate:
    sample_f = frame_cache if is_image else cap.read()[1]
    if sample_f is not None:
      detector.interactive_calibrate_slots(sample_f)

  wait_for_stream_barrier(
    detector.server_url,
    detector.http_opener,
    detector.stream_id,
    sync_peers,
    timeout=barrier_timeout
  )

  stream_tag = f" [{stream_id}]" if stream_id != "default" else ""
  window_name = f"Free Fire Live Scoreboard Tracker{stream_tag} ['q' Quit | 's' Slots | 'l' Lock Roster | 'c' Clear]"
  if display:
    cv2.namedWindow(window_name, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(window_name, 1280, 720)
    if stream_id == "stream_1":
      cv2.moveWindow(window_name, 30, 30)
    elif stream_id == "stream_2":
      cv2.moveWindow(window_name, 160, 100)

  print("\n[Tracker Active] Controls: 'l' = Lock/Unlock Roster | 's' = Select Slots | 'c' = Clear Teams | 'q' = Quit\n")

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
          detector.reset_kill_tracker()
          time.sleep(0.1)
          continue

      detector.feed_frame(frame)

      elapsed = loop_start - last_frame_time
      last_frame_time = loop_start
      if elapsed > 0:
        fps_history.append(1.0 / elapsed)
        if len(fps_history) > 15:
          fps_history.pop(0)
        detector.fps_display = sum(fps_history) / float(len(fps_history))

      if display:
        overlay = detector.draw_visual_overlay(frame)
        cv2.imshow(window_name, overlay)

        key = cv2.waitKey(1) & 0xFF
        if key == ord('q'):
          break
        elif key == ord('s'):
          detector.interactive_calibrate_slots(frame)
        elif key == ord('l'):
          detector.toggle_roster_lock()
        elif key == ord('c'):
          detector.clear_persistent_teams()

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
  parser.add_argument("--stream-id", type=str, default="default", help="Unique stream identifier (e.g. stream_1, stream_2)")
  parser.add_argument("--max-teams", type=int, default=12, help="Maximum persistent teams tracked by this stream (e.g. 6 for 6+6 split)")
  parser.add_argument("--no-local-json", dest="write_local_json", action="store_false", default=True, help="Disable direct live_state.json writes from Python (use in multi-stream)")
  parser.add_argument("--calibration", type=str, default=None, help="Optional per-stream slot calibration JSON path")
  parser.add_argument("--sync-peers", type=int, default=1, help="Wait for N total streams at startup barrier before reading frames")
  parser.add_argument("--barrier-timeout", type=float, default=15.0, help="Max seconds to wait at startup barrier")

  args = parser.parse_args()
  run_live_scoreboard(
    source=args.source,
    server_url=args.server,
    sync_gap=args.gap,
    display=args.display,
    calibrate=args.calibrate,
    stream_id=args.stream_id,
    max_teams=args.max_teams,
    write_local_json=args.write_local_json,
    calibration_file=args.calibration,
    sync_peers=args.sync_peers,
    barrier_timeout=args.barrier_timeout
  )