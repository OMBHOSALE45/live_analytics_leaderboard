import json
import os
from typing import List, Tuple, Dict, Any, Optional
import cv2
import numpy as np


class DarkMasker:
    """
    Precision Dark Masker & Permanent-Lock Inner-Core Slicer:
    - Isolates the 4 player spectator white health bars on a pure black (0, 0, 0) canvas.
    - Uses HSV white-pixel filtering + longest horizontal contiguous run to lock
      strictly onto the solid white HP bar (ignoring player names & bright backgrounds).
    - Enforces a rigid 4-bar geometric grid (shared x1/x2, uniform vertical pitch).
    - Multi-frame consensus lock: once locked, coordinates are frozen FOREVER
      throughout the entire stream.
    """

    def __init__(self, config_or_path: Optional[Any] = None):
        self.canvas_roi = [0.035, 0.065, 0.360, 0.550]
        self.bars_roi = [
            [0.0840, 0.1532, 0.3418, 0.1729],
            [0.0840, 0.2670, 0.3418, 0.2867],
            [0.0830, 0.3786, 0.3418, 0.3982],
            [0.0820, 0.4923, 0.3408, 0.5098]
        ]
        self.core_height_fraction = 0.50
        self.config_locked = False

        # Permanent lock state
        self.locked_bars: Dict[int, Tuple[int, int, int, int]] = {}
        self.is_locked = False
        self.frame_dims: Optional[Tuple[int, int]] = None

        # Multi-frame consensus buffer for auto-locking
        self.lock_frames_required = 5
        self._candidate_samples: List[List[Tuple[int, int, int, int]]] = []

        if config_or_path is not None:
            if isinstance(config_or_path, str) and os.path.exists(config_or_path):
                with open(config_or_path, 'r', encoding='utf-8') as f:
                    cfg = json.load(f)
                self._load_config_dict(cfg)
            elif isinstance(config_or_path, dict):
                self._load_config_dict(config_or_path)

    def _load_config_dict(self, cfg: Dict[str, Any]):
        if "canvas_roi" in cfg:
            self.canvas_roi = cfg["canvas_roi"]
        if "bars_roi" in cfg:
            self.bars_roi = cfg["bars_roi"]
        if "core_height_fraction" in cfg:
            self.core_height_fraction = float(cfg["core_height_fraction"])
        if "locked" in cfg:
            self.config_locked = bool(cfg["locked"])
        if "lock_frames_required" in cfg:
            self.lock_frames_required = max(1, int(cfg["lock_frames_required"]))
        self.reset_lock()

    def update_rois(
        self,
        bars_roi: List[List[float]],
        canvas_roi: Optional[List[float]] = None,
        lock_immediately: bool = True
    ):
        """Updates normalized ROIs on calibration."""
        self.bars_roi = bars_roi
        if canvas_roi is not None:
            self.canvas_roi = canvas_roi
        self.config_locked = lock_immediately
        self.reset_lock()

    def reset_lock(self):
        """Resets locked coordinates, allowing re-locking on next valid frames."""
        self.locked_bars.clear()
        self._candidate_samples.clear()
        self.is_locked = False

    def get_lock_progress(self) -> Tuple[bool, int, int]:
        """Returns (is_locked, collected_frames, required_frames)."""
        return (
            self.is_locked,
            self.lock_frames_required if self.is_locked else len(self._candidate_samples),
            self.lock_frames_required,
        )

    @staticmethod
    def _white_bar_mask(bgr_crop: np.ndarray) -> np.ndarray:
        """
        Extracts a strict binary mask of pure white HP bar pixels.
        White HP bars have low saturation (S <= 60) and high brightness (V >= 175).
        """
        if bgr_crop is None or bgr_crop.size == 0:
            return np.zeros((1, 1), dtype=np.uint8)
        hsv = cv2.cvtColor(bgr_crop, cv2.COLOR_BGR2HSV)
        lower_white = np.array([0, 0, 175], dtype=np.uint8)
        upper_white = np.array([180, 60, 255], dtype=np.uint8)
        return cv2.inRange(hsv, lower_white, upper_white)

    @staticmethod
    def _longest_contiguous_run(row_bool: np.ndarray) -> Tuple[int, int, int]:
        """
        Finds the longest contiguous horizontal run of True values in a 1D bool array.
        Returns: (max_len, start_x, end_x_inclusive)
        """
        if row_bool.size == 0 or not np.any(row_bool):
            return 0, 0, 0
        padded = np.concatenate(([False], row_bool, [False]))
        diffs = np.diff(padded.astype(np.int8))
        starts = np.where(diffs == 1)[0]
        ends = np.where(diffs == -1)[0]
        lengths = ends - starts
        best_i = int(np.argmax(lengths))
        return int(lengths[best_i]), int(starts[best_i]), int(ends[best_i] - 1)

    @classmethod
    def _detect_white_bar_in_strip(
        cls,
        strip_bgr: np.ndarray,
        min_width_ratio: float = 0.25
    ) -> Optional[Tuple[int, int, int, int]]:
        """
        Detects a solid white horizontal HP bar inside a search strip.
        Returns (rel_x1, rel_y1, rel_x2, rel_y2) or None if no valid white bar exists.
        """
        if strip_bgr is None or strip_bgr.size == 0:
            return None
        sh, sw = strip_bgr.shape[:2]
        if sw < 10 or sh < 3:
            return None

        mask = cls._white_bar_mask(strip_bgr) > 0
        min_run = max(8, int(sw * min_width_ratio))

        row_runs = np.zeros(sh, dtype=np.int32)
        row_starts = np.zeros(sh, dtype=np.int32)
        row_ends = np.zeros(sh, dtype=np.int32)

        for r in range(sh):
            run_len, sx, ex = cls._longest_contiguous_run(mask[r])
            row_runs[r] = run_len
            row_starts[r] = sx
            row_ends[r] = ex

        valid_rows = row_runs >= min_run
        if not np.any(valid_rows):
            return None

        # Find the thickest contiguous vertical band of valid white rows
        padded = np.concatenate(([False], valid_rows, [False]))
        diffs = np.diff(padded.astype(np.int8))
        b_starts = np.where(diffs == 1)[0]
        b_ends = np.where(diffs == -1)[0]

        best_score = -1.0
        best_band = None
        for bs, be in zip(b_starts, b_ends):
            band_h = int(be - bs)
            if band_h < 2:
                continue
            # Score by vertical thickness * median horizontal run length
            med_run = float(np.median(row_runs[bs:be]))
            score = band_h * med_run
            if score > best_score:
                best_score = score
                best_band = (int(bs), int(be))

        if best_band is None:
            return None

        y1, y2 = best_band
        x1 = int(np.median(row_starts[y1:y2]))
        x2 = int(np.median(row_ends[y1:y2])) + 1

        if (x2 - x1) < min_run:
            return None

        return (x1, y1, x2, y2)

    @staticmethod
    def _enforce_uniform_grid(
        detections: List[Optional[Tuple[int, int, int, int]]],
        num_bars: int,
        frame_w: int,
        frame_h: int
    ) -> Optional[List[Tuple[int, int, int, int]]]:
        """
        Enforces a strict geometric grid across all 4 bars:
        - Shared x1, x2 (exact left/right edges of the white bars).
        - Identical bar height.
        - Strictly uniform vertical pitch between bar centers.
        Works even if only 2 or 3 bars are visible/alive!
        """
        valid = [(i, det) for i, det in enumerate(detections) if det is not None]
        if len(valid) < 2:
            return None

        # Shared horizontal bounds (use 10th percentile x1, 90th percentile x2 for full-width bar)
        x1_vals = [d[0] for _, d in valid]
        x2_vals = [d[2] for _, d in valid]
        shared_x1 = int(np.median(x1_vals))
        shared_x2 = int(np.max(x2_vals))  # Full-HP bar defines true 100% right edge

        # Inset 1px from left/right anti-aliased edges
        if (shared_x2 - shared_x1) > 20:
            shared_x1 += 1
            shared_x2 -= 1

        # Shared bar height
        heights = [d[3] - d[1] for _, d in valid]
        shared_h = max(4, int(round(float(np.median(heights)))))

        # Fit linear model: center_y(i) = y0 + i * pitch_y
        indices = np.array([i for i, _ in valid], dtype=np.float64)
        centers = np.array([(d[1] + d[3]) / 2.0 for _, d in valid], dtype=np.float64)

        pitch_y, y0 = np.polyfit(indices, centers, 1)
        if pitch_y < shared_h * 1.5:
            return None

        grid_bars: List[Tuple[int, int, int, int]] = []
        half_h = shared_h / 2.0
        for i in range(num_bars):
            cy = y0 + i * pitch_y
            by1 = max(0, int(round(cy - half_h)))
            by2 = min(frame_h, int(round(cy + half_h)))
            if by2 <= by1:
                by2 = min(frame_h, by1 + 2)
            grid_bars.append((
                max(0, shared_x1),
                by1,
                min(frame_w, shared_x2),
                by2
            ))

        return grid_bars

    @classmethod
    def extract_bars_from_border(
        cls,
        frame: np.ndarray,
        bx: int,
        by: int,
        bw: int,
        bh: int,
        num_bars: int = 4
    ) -> Tuple[List[List[float]], List[float]]:
        """
        Derives normalized canvas ROI and exact white health bar ROIs from a single
        user-plotted bounding box around the Spectator HP HUD.
        Uses HSV white-bar contiguity + uniform 4-bar grid fitting.
        """
        h, w = frame.shape[:2]

        canvas_norm = [
            round(max(0, bx - 10) / float(w), 4),
            round(max(0, by - 8) / float(h), 4),
            round(min(w, bx + bw + 10) / float(w), 4),
            round(min(h, by + bh + 8) / float(h), 4)
        ]

        sec_h = bh / float(num_bars)
        detections: List[Optional[Tuple[int, int, int, int]]] = []

        for i in range(num_bars):
            s_y1 = max(0, int(by + i * sec_h))
            s_y2 = min(h, int(by + (i + 1) * sec_h))
            strip = frame[s_y1:s_y2, bx:bx + bw]
            det = cls._detect_white_bar_in_strip(strip, min_width_ratio=0.25)
            if det is not None:
                rx1, ry1, rx2, ry2 = det
                detections.append((bx + rx1, s_y1 + ry1, bx + rx2, s_y1 + ry2))
            else:
                detections.append(None)

        grid = cls._enforce_uniform_grid(detections, num_bars, w, h)

        bars_norm: List[List[float]] = []
        if grid is not None:
            for (gx1, gy1, gx2, gy2) in grid:
                bars_norm.append([
                    round(gx1 / float(w), 4),
                    round(gy1 / float(h), 4),
                    round(gx2 / float(w), 4),
                    round(gy2 / float(h), 4)
                ])
        else:
            # Fallback if fewer than 2 white bars were visible during calibration
            for i in range(num_bars):
                s_y1 = int(by + i * sec_h)
                s_y2 = int(by + (i + 1) * sec_h)
                mid_y = (s_y1 + s_y2) // 2
                bar_y1 = max(0, mid_y - 4)
                bar_y2 = min(h, mid_y + 4)
                bars_norm.append([
                    round(bx / float(w), 4),
                    round(bar_y1 / float(h), 4),
                    round((bx + bw) / float(w), 4),
                    round(bar_y2 / float(h), 4)
                ])

        return bars_norm, canvas_norm

    def _compute_inner_core_box(
        self,
        bx1: int,
        by1: int,
        bx2: int,
        by2: int,
        frame_h: int
    ) -> Tuple[int, int, int, int]:
        """Slices strictly the middle core_height_fraction of a bar's vertical height."""
        bh = max(2, by2 - by1)
        core_h = max(2, int(round(bh * self.core_height_fraction)))
        y_mid = (by1 + by2) // 2
        y_core_start = max(0, y_mid - core_h // 2)
        y_core_end = min(frame_h, y_core_start + core_h)
        return (bx1, y_core_start, bx2, y_core_end)

    def _lock_from_config_immediately(self, w: int, h: int):
        """Locks all 4 bars immediately using exact calibrated ROIs from config."""
        self.locked_bars.clear()
        for idx, bar_norm in enumerate(self.bars_roi):
            bx1 = max(0, int(round(bar_norm[0] * w)))
            by1 = max(0, int(round(bar_norm[1] * h)))
            bx2 = min(w, int(round(bar_norm[2] * w)))
            by2 = min(h, int(round(bar_norm[3] * h)))
            self.locked_bars[idx] = self._compute_inner_core_box(bx1, by1, bx2, by2, h)
        self.is_locked = True

    def mask_and_slice(
        self,
        frame: np.ndarray
    ) -> Tuple[np.ndarray, List[np.ndarray], List[Tuple[int, int, int, int]], Tuple[int, int, int, int]]:
        """
        Executes dark masking and inner core extraction.
        Once locked, strictly uses locked pixel coordinates FOREVER.
        """
        if frame is None or frame.size == 0:
            return np.zeros((10, 10, 3), dtype=np.uint8), [], [], (0, 0, 0, 0)

        h, w = frame.shape[:2]

        # Reset lock only if stream resolution changes
        if self.frame_dims != (w, h):
            self.frame_dims = (w, h)
            self.reset_lock()

        # If config was calibrated and marked locked, lock immediately on frame 1
        if not self.is_locked and self.config_locked:
            self._lock_from_config_immediately(w, h)

        # Calculate canvas pixel coordinates
        cx1 = max(0, int(self.canvas_roi[0] * w))
        cy1 = max(0, int(self.canvas_roi[1] * h))
        cx2 = min(w, int(self.canvas_roi[2] * w))
        cy2 = min(h, int(self.canvas_roi[3] * h))
        canvas_box = (cx1, cy1, cx2, cy2)

        cw = max(1, cx2 - cx1)
        ch = max(1, cy2 - cy1)
        dark_canvas = np.zeros((ch, cw, 3), dtype=np.uint8)

        # Auto-acquisition phase (only runs if not yet locked)
        if not self.is_locked:
            detections: List[Optional[Tuple[int, int, int, int]]] = []
            for bar_norm in self.bars_roi:
                bx1 = max(0, int(round(bar_norm[0] * w)))
                by1 = max(0, int(round(bar_norm[1] * h)))
                bx2 = min(w, int(round(bar_norm[2] * w)))
                by2 = min(h, int(round(bar_norm[3] * h)))

                # Tight search window (+/- 12px vertically) to snap onto true white bar
                sy1 = max(0, by1 - 12)
                sy2 = min(h, by2 + 12)
                strip = frame[sy1:sy2, bx1:bx2]
                det = self._detect_white_bar_in_strip(strip, min_width_ratio=0.30)
                if det is not None:
                    rx1, ry1, rx2, ry2 = det
                    detections.append((bx1 + rx1, sy1 + ry1, bx1 + rx2, sy1 + ry2))
                else:
                    detections.append(None)

            grid = self._enforce_uniform_grid(detections, len(self.bars_roi), w, h)
            if grid is not None:
                self._candidate_samples.append(grid)

                # Once we have enough consistent frames, compute median and LOCK FOREVER
                if len(self._candidate_samples) >= self.lock_frames_required:
                    arr = np.array(self._candidate_samples, dtype=np.float64)  # (N, 4, 4)
                    med_grid = np.median(arr, axis=0)
                    for idx in range(len(self.bars_roi)):
                        gx1, gy1, gx2, gy2 = [int(round(v)) for v in med_grid[idx]]
                        self.locked_bars[idx] = self._compute_inner_core_box(gx1, gy1, gx2, gy2, h)
                    self.is_locked = True
                    self._candidate_samples.clear()

        # Extract inner cores (from locked_bars if locked, else fallback to config ROI)
        bar_cores: List[np.ndarray] = []
        core_coords: List[Tuple[int, int, int, int]] = []

        for idx, bar_norm in enumerate(self.bars_roi):
            if self.is_locked and idx in self.locked_bars:
                bx1, y_core_start, bx2, y_core_end = self.locked_bars[idx]
            else:
                bx1 = max(0, int(round(bar_norm[0] * w)))
                by1 = max(0, int(round(bar_norm[1] * h)))
                bx2 = min(w, int(round(bar_norm[2] * w)))
                by2 = min(h, int(round(bar_norm[3] * h)))
                bx1, y_core_start, bx2, y_core_end = self._compute_inner_core_box(bx1, by1, bx2, by2, h)

            bw = max(1, bx2 - bx1)
            core_slice = frame[y_core_start:y_core_end, bx1:bx2]
            bar_cores.append(core_slice)
            core_coords.append((bx1, y_core_start, bx2, y_core_end))

            # Stamp inner core onto pure black dark canvas
            rel_x1 = max(0, bx1 - cx1)
            rel_y1 = max(0, y_core_start - cy1)
            rel_x2 = min(cw, rel_x1 + bw)
            rel_y2 = min(ch, rel_y1 + (y_core_end - y_core_start))

            actual_slice = frame[
                y_core_start:y_core_start + (rel_y2 - rel_y1),
                bx1:bx1 + (rel_x2 - rel_x1)
            ]
            if actual_slice.size > 0:
                dark_canvas[rel_y1:rel_y2, rel_x1:rel_x2] = actual_slice

        return dark_canvas, bar_cores, core_coords, canvas_box