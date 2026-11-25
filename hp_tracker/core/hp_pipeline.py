import os
import json
import time
from typing import Dict, Any, Optional, List, Tuple
import cv2
import numpy as np

from .dark_masker import DarkMasker
from .bar_analyzer import BarAnalyzer
from .temporal_filter import TemporalFilter


class HPTrackerPipeline:
    """
    Unified Dark-Masked Health Bar Tracker:
    - Zero-training, CPU-only, ultra-fast (< 1.0 ms per frame).
    - Pipeline:
        Frame -> DarkMasker (Permanent-Lock White Bar Inner-Core Slicing)
              -> BarAnalyzer (Contiguous L-to-R Scan, Zero BG Bleed)
              -> TemporalFilter (Median Smoothing, Hysteresis, Debounce, Team Flush)
              -> Structured HP Output (0.0-100.0%, ALIVE/KNOCKED/DEAD)
    """

    def __init__(self, config_path: Optional[str] = None):
        if config_path is None:
            config_path = os.path.abspath(
                os.path.join(os.path.dirname(__file__), "..", "config", "hp_config.json")
            )

        self.config_path = config_path
        self.config = {}
        if os.path.exists(config_path):
            with open(config_path, "r", encoding="utf-8") as f:
                self.config = json.load(f)

        self.dark_masker = DarkMasker(self.config)
        self.bar_analyzer = BarAnalyzer(self.config)
        self.temporal_filter = TemporalFilter(self.config, num_slots=4)

        self.total_frames_processed = 0
        self.avg_latency_ms = 0.0

    def reload_config(self):
        """Reloads configuration from disk and resets lock."""
        if os.path.exists(self.config_path):
            with open(self.config_path, "r", encoding="utf-8") as f:
                self.config = json.load(f)
            self.dark_masker._load_config_dict(self.config)
            self.bar_analyzer._load_config_dict(self.config)
            self.temporal_filter._load_config_dict(self.config)

    def reset_lock(self):
        """Manually unlocks the bar positions to allow re-acquisition."""
        self.dark_masker.reset_lock()

    def process_frame(
        self,
        frame: np.ndarray,
        team_id: Optional[Any] = None
    ) -> Dict[str, Any]:
        """
        Executes end-to-end health bar extraction on a single frame.
        """
        t0 = time.perf_counter()

        # Step 1: Programmatic Dark Masking & Permanent-Lock Inner-Core Slicing
        dark_canvas, bar_cores, core_coords, canvas_box = self.dark_masker.mask_and_slice(frame)

        # Step 2: Contiguous Left-to-Right Scan per Bar
        raw_observations = []
        for core in bar_cores:
            analysis = self.bar_analyzer.analyze_bar(core)
            raw_observations.append(analysis)

        # Step 3: Temporal Filtering, Hysteresis & Debouncing
        filtered_players = self.temporal_filter.filter_observations(raw_observations, team_id=team_id)

        for i, p in enumerate(filtered_players):
            if i < len(core_coords):
                p['coords'] = core_coords[i]
            if i < len(raw_observations):
                p['binary_core'] = raw_observations[i]['binary_core']
                p['is_red'] = raw_observations[i]['is_red']

        t1 = time.perf_counter()
        latency_ms = (t1 - t0) * 1000.0

        self.total_frames_processed += 1
        self.avg_latency_ms = (
            self.avg_latency_ms * 0.9 + latency_ms * 0.1
            if self.total_frames_processed > 1 else latency_ms
        )

        is_locked, lock_cur, lock_req = self.dark_masker.get_lock_progress()

        return {
            'players': filtered_players,
            'latency_ms': round(latency_ms, 3),
            'avg_latency_ms': round(self.avg_latency_ms, 3),
            'dark_canvas': dark_canvas,
            'canvas_box': canvas_box,
            'bar_cores': bar_cores,
            'core_coords': core_coords,
            'team_id': team_id,
            'is_locked': is_locked,
            'lock_progress': (lock_cur, lock_req),
        }

    def draw_debug_overlay(
        self,
        frame: np.ndarray,
        hp_result: Dict[str, Any],
        show_canvas_preview: bool = True
    ) -> np.ndarray:
        """
        Renders rich visual debug overlay on top of the frame.
        """
        preview = frame.copy()
        h, w = preview.shape[:2]

        players = hp_result.get('players', [])
        canvas_box = hp_result.get('canvas_box', (0, 0, 0, 0))
        is_locked = hp_result.get('is_locked', False)
        lock_cur, lock_req = hp_result.get('lock_progress', (0, 5))

        # 1. Draw outer HUD canvas box + Lock badge
        cx1, cy1, cx2, cy2 = canvas_box
        cv2.rectangle(preview, (cx1, cy1), (cx2, cy2), (60, 40, 20), 1)
        lock_label = "LOCKED" if is_locked else f"ACQUIRING ({lock_cur}/{lock_req})"
        lock_color = (0, 255, 120) if is_locked else (0, 200, 255)
        cv2.putText(
            preview, f"HP TRACKER: {lock_label}",
            (cx1, max(20, cy1 - 6)),
            cv2.FONT_HERSHEY_SIMPLEX, 0.42, lock_color, 1, cv2.LINE_AA
        )

        # 2. Draw each player bar meter and state badge
        for p in players:
            coords = p.get('coords')
            if not coords:
                continue
            x1, y1, x2, y2 = coords
            bw = x2 - x1
            bh = y2 - y1

            hp = p['hp']
            state = p['state']

            # Background dark bar
            cv2.rectangle(preview, (x1, y1), (x2, y2), (25, 25, 25), -1)

            # Health bar color logic
            if state == "DEAD":
                bar_bgr = (60, 60, 60)
                txt_bgr = (110, 110, 110)
                fill_w = 0
            elif state == "KNOCKED":
                bar_bgr = (0, 0, 220)
                txt_bgr = (255, 255, 255)
                fill_w = max(4, int(bw * (hp / 100.0)))
            else:
                if hp > 50.0:
                    bar_bgr = (0, 230, 80)     # Neon Green
                elif hp > 25.0:
                    bar_bgr = (0, 200, 255)    # Orange/Yellow
                else:
                    bar_bgr = (0, 50, 240)     # Red
                txt_bgr = (255, 255, 255)
                fill_w = max(0, int(bw * (hp / 100.0)))

            if fill_w > 0:
                cv2.rectangle(preview, (x1, y1), (x1 + fill_w, y2), bar_bgr, -1)

            border_bgr = (0, 255, 255) if p.get('is_debouncing') else (120, 120, 120)
            cv2.rectangle(preview, (x1, y1), (x2, y2), border_bgr, 1)

            status_text = f"P{p['slot']}: {hp:.1f}% [{state}]"
            cv2.putText(
                preview, status_text,
                (x2 + 8, y1 + bh + 2),
                cv2.FONT_HERSHEY_SIMPLEX, 0.40, txt_bgr, 1, cv2.LINE_AA
            )

        # 3. Telemetry HUD (Bottom-Left)
        lat = hp_result.get('latency_ms', 0.0)
        avg_lat = hp_result.get('avg_latency_ms', 0.0)
        hud_str = f"HP Engine: {lat:.2f}ms (avg: {avg_lat:.2f}ms) | {lock_label}"
        cv2.rectangle(preview, (10, h - 28), (430, h - 6), (15, 12, 22), -1)
        cv2.rectangle(preview, (10, h - 28), (430, h - 6), (80, 60, 100), 1)
        cv2.putText(
            preview, hud_str, (18, h - 12),
            cv2.FONT_HERSHEY_SIMPLEX, 0.38, (0, 255, 200), 1, cv2.LINE_AA
        )

        # 4. Optional Picture-in-Picture Dark Canvas Preview
        if show_canvas_preview:
            dark_canvas = hp_result.get('dark_canvas')
            if dark_canvas is not None and dark_canvas.size > 0:
                pip_w = 180
                scale = pip_w / float(dark_canvas.shape[1])
                pip_h = max(20, int(dark_canvas.shape[0] * scale))
                pip_canvas = cv2.resize(dark_canvas, (pip_w, pip_h), interpolation=cv2.INTER_NEAREST)

                py1 = h - pip_h - 40
                py2 = py1 + pip_h
                px1 = 10
                px2 = px1 + pip_w

                if py1 > 0 and px2 < w:
                    cv2.rectangle(preview, (px1 - 2, py1 - 16), (px2 + 2, py2 + 2), (30, 20, 40), -1)
                    cv2.putText(
                        preview, "DARK MASK CORE PREVIEW",
                        (px1, py1 - 4),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.34, (200, 200, 255), 1, cv2.LINE_AA
                    )
                    preview[py1:py2, px1:px2] = pip_canvas
                    cv2.rectangle(preview, (px1, py1), (px2, py2), (0, 230, 255), 1)

        return preview