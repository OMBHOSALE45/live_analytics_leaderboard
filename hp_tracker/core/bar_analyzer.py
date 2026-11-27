import json
import os
from typing import Dict, Any, Optional, Tuple, List
import cv2
import numpy as np


class BarAnalyzer:
    """
    High-Performance Bar Core Analyzer with Contiguous Left-to-Right Scan:
    - Multi-color HSV binarization (White, Green, Yellow, Red/Knocked).
    - Contiguous Left-to-Right scan: advances as long as columns are filled,
      and halts at the first real gap (>= 5 empty columns).
    - Zero Background Bleed: bright sky, clouds, muzzle flashes, or gloo walls
      behind the empty right track are completely ignored.
    - Tentative state detection: ALIVE, KNOCKED, DEAD.
    """

    def __init__(self, config_or_path: Optional[Any] = None):
        self.contiguous_gap_threshold = 5
        self.col_fill_threshold = 0.35
        self.brightness_threshold = 130
        self.dead_hp_cutoff = 1.5

        # Default HSV Thresholds for Free Fire Health Bars
        self.hsv_ranges = {
            "white": (np.array([0, 0, 155], dtype=np.uint8), np.array([180, 65, 255], dtype=np.uint8)),
            "green": (np.array([35, 60, 70], dtype=np.uint8), np.array([85, 255, 255], dtype=np.uint8)),
            "yellow": (np.array([18, 80, 80], dtype=np.uint8), np.array([35, 255, 255], dtype=np.uint8)),
            "red1": (np.array([0, 90, 80], dtype=np.uint8), np.array([12, 255, 255], dtype=np.uint8)),
            "red2": (np.array([168, 90, 80], dtype=np.uint8), np.array([180, 255, 255], dtype=np.uint8))
        }

        if config_or_path is not None:
            if isinstance(config_or_path, str) and os.path.exists(config_or_path):
                with open(config_or_path, 'r', encoding='utf-8') as f:
                    cfg = json.load(f)
                self._load_config_dict(cfg)
            elif isinstance(config_or_path, dict):
                self._load_config_dict(config_or_path)

    def _load_config_dict(self, cfg: Dict[str, Any]):
        if "contiguous_gap_threshold" in cfg:
            self.contiguous_gap_threshold = int(cfg["contiguous_gap_threshold"])
        if "col_fill_threshold" in cfg:
            self.col_fill_threshold = float(cfg["col_fill_threshold"])
        if "brightness_threshold" in cfg:
            self.brightness_threshold = int(cfg["brightness_threshold"])
        if "dead_hp_cutoff" in cfg:
            self.dead_hp_cutoff = float(cfg["dead_hp_cutoff"])

        if "hsv_thresholds" in cfg:
            t = cfg["hsv_thresholds"]
            if "white_hp" in t:
                self.hsv_ranges["white"] = (
                    np.array(t["white_hp"]["lower"], dtype=np.uint8),
                    np.array(t["white_hp"]["upper"], dtype=np.uint8)
                )
            if "green_hp" in t:
                self.hsv_ranges["green"] = (
                    np.array(t["green_hp"]["lower"], dtype=np.uint8),
                    np.array(t["green_hp"]["upper"], dtype=np.uint8)
                )
            if "yellow_hp" in t:
                self.hsv_ranges["yellow"] = (
                    np.array(t["yellow_hp"]["lower"], dtype=np.uint8),
                    np.array(t["yellow_hp"]["upper"], dtype=np.uint8)
                )
            if "red_hp_1" in t:
                self.hsv_ranges["red1"] = (
                    np.array(t["red_hp_1"]["lower"], dtype=np.uint8),
                    np.array(t["red_hp_1"]["upper"], dtype=np.uint8)
                )
            if "red_hp_2" in t:
                self.hsv_ranges["red2"] = (
                    np.array(t["red_hp_2"]["lower"], dtype=np.uint8),
                    np.array(t["red_hp_2"]["upper"], dtype=np.uint8)
                )

    def binarize_bar_core(self, core_bgr: np.ndarray) -> Tuple[np.ndarray, bool]:
        """
        Binarizes active health pixels in the inner core.
        Returns: (binary_mask, is_red_dominant)
        """
        if core_bgr is None or core_bgr.size == 0:
            return np.zeros((1, 1), dtype=np.uint8), False

        hsv = cv2.cvtColor(core_bgr, cv2.COLOR_BGR2HSV)

        # 1. White HP mask (Standard healthy bar)
        mask_white = cv2.inRange(hsv, self.hsv_ranges["white"][0], self.hsv_ranges["white"][1])

        # 2. Green HP mask
        mask_green = cv2.inRange(hsv, self.hsv_ranges["green"][0], self.hsv_ranges["green"][1])

        # 3. Yellow HP mask
        mask_yellow = cv2.inRange(hsv, self.hsv_ranges["yellow"][0], self.hsv_ranges["yellow"][1])

        # 4. Red / Knocked HP mask (HSV + BGR red-channel dominance for compressed streams)
        mask_red1 = cv2.inRange(hsv, self.hsv_ranges["red1"][0], self.hsv_ranges["red1"][1])
        mask_red2 = cv2.inRange(hsv, self.hsv_ranges["red2"][0], self.hsv_ranges["red2"][1])
        b_ch, g_ch, r_ch = cv2.split(core_bgr)
        bgr_red = ((r_ch >= 115) & (r_ch.astype(np.int16) - np.maximum(g_ch, b_ch).astype(np.int16) >= 38)).astype(np.uint8) * 255
        mask_red = cv2.bitwise_or(cv2.bitwise_or(mask_red1, mask_red2), bgr_red)

        # Combined multi-color active health mask
        active_mask = cv2.bitwise_or(mask_white, mask_green)
        active_mask = cv2.bitwise_or(active_mask, mask_yellow)
        active_mask = cv2.bitwise_or(active_mask, mask_red)

        # Fallback high-contrast thresholding on bright pixels
        gray = cv2.cvtColor(core_bgr, cv2.COLOR_BGR2GRAY)
        _, bright_mask = cv2.threshold(gray, self.brightness_threshold, 255, cv2.THRESH_BINARY)
        combined_mask = cv2.bitwise_or(active_mask, bright_mask)

        # Check if red is dominant (player knocked down & bleeding in red)
        red_count = np.count_nonzero(mask_red)
        total_active = np.count_nonzero(combined_mask)
        is_red_dominant = bool(total_active > 0 and (red_count / float(total_active)) >= 0.35)

        return combined_mask, is_red_dominant

    def analyze_bar(self, core_bgr: np.ndarray) -> Dict[str, Any]:
        """
        Runs Contiguous Left-to-Right Scan on a single bar core.

        Returns:
            {
                'raw_hp': float (0.0 to 100.0),
                'state': str ('ALIVE', 'KNOCKED', 'DEAD'),
                'last_filled_x': int,
                'bar_width': int,
                'is_red': bool,
                'binary_core': np.ndarray
            }
        """
        if core_bgr is None or core_bgr.size == 0:
            return {
                'raw_hp': 0.0,
                'state': 'DEAD',
                'last_filled_x': -1,
                'bar_width': 0,
                'is_red': False,
                'binary_core': np.zeros((1, 1), dtype=np.uint8)
            }

        h_core, w_bar = core_bgr.shape[:2]
        if w_bar < 5 or h_core < 1:
            return {
                'raw_hp': 0.0,
                'state': 'DEAD',
                'last_filled_x': -1,
                'bar_width': w_bar,
                'is_red': False,
                'binary_core': np.zeros((1, 1), dtype=np.uint8)
            }

        bin_core, is_red = self.binarize_bar_core(core_bgr)

        # -------------------------------------------------------------
        # UPGRADED OPENCV FIX: Contiguous Left-to-Right Scan
        # -------------------------------------------------------------
        # Scans columns starting from x=0. As long as columns contain active
        # health pixels, it advances. If a gap >= gap_threshold (5 cols)
        # is encountered, scanning halts immediately. Any bright pixels to
        # the right of the gap (e.g. gloo walls, sky) are completely discarded.
        # -------------------------------------------------------------
        consecutive_gaps = 0
        last_filled_x = -1

        # Vectorized column density calculation for maximum speed (< 0.03 ms)
        col_densities = np.mean(bin_core > 0, axis=0)  # Shape: (w_bar,)

        for x in range(w_bar):
            if col_densities[x] >= self.col_fill_threshold:
                last_filled_x = x
                consecutive_gaps = 0
            else:
                consecutive_gaps += 1
                if consecutive_gaps >= self.contiguous_gap_threshold:
                    # Halt scan: remaining pixels are background bleed!
                    break

        if last_filled_x < 0:
            raw_hp = 0.0
        else:
            raw_hp = min(100.0, ((last_filled_x + 1) / float(w_bar)) * 100.0)

        # Edge validation: if raw_hp is near 100% (within 4px of right border), clamp to 100%
        if w_bar - (last_filled_x + 1) <= 3 and raw_hp > 96.0:
            raw_hp = 100.0

        # Tentative state classification: any red HP bar above dead cutoff is KNOCKED & bleeding
        if raw_hp <= self.dead_hp_cutoff:
            tentative_state = "DEAD"
            raw_hp = 0.0
        elif is_red:
            tentative_state = "KNOCKED"
        else:
            tentative_state = "ALIVE"

        return {
            'raw_hp': round(float(raw_hp), 2),
            'state': tentative_state,
            'last_filled_x': last_filled_x,
            'bar_width': w_bar,
            'is_red': is_red,
            'binary_core': bin_core
        }
