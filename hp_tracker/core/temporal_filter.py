import json
import os
from collections import deque
from typing import Dict, Any, Optional, List
import numpy as np


class SlotFilter:
    """
    Temporal Filter & Debouncer for an individual player slot:
    - 5-frame rolling median filter (smooths H.264 compression noise).
    - Hysteresis band (prevents +/- 1% flicker on stationary HP).
    - State Transition Debouncer (prevents 1-frame flashbang/UI drop false DEADs).
    """

    def __init__(
        self,
        median_window: int = 2,
        hysteresis_pct: float = 0.5,
        dead_frames_required: int = 2,
        knocked_frames_required: int = 1,
        alive_frames_required: int = 1
    ):
        self.median_window = median_window
        self.hysteresis_pct = hysteresis_pct
        self.dead_frames_required = dead_frames_required
        self.knocked_frames_required = knocked_frames_required
        self.alive_frames_required = alive_frames_required

        self.history: deque = deque(maxlen=median_window)
        self.current_smoothed_hp: float = 100.0
        self.current_state: str = "ALIVE"

        # State debounce counters
        self.candidate_state: str = "ALIVE"
        self.candidate_frames: int = 0

    def reset(self, initial_hp: float = 100.0, initial_state: str = "ALIVE"):
        """Instantly clears all history and state counters."""
        self.history.clear()
        self.current_smoothed_hp = initial_hp
        self.current_state = initial_state
        self.candidate_state = initial_state
        self.candidate_frames = 0

    def update(self, raw_hp: float, tentative_state: str) -> Dict[str, Any]:
        """
        Updates the slot with a new observation and returns filtered results.
        """
        self.history.append(raw_hp)

        # 1. Rolling Median Filter
        med_hp = float(np.median(self.history))

        # 2. Hysteresis: only update if delta exceeds threshold or if 0%/100%
        delta = abs(med_hp - self.current_smoothed_hp)
        if delta >= self.hysteresis_pct or med_hp >= 99.0 or med_hp <= 1.0:
            self.current_smoothed_hp = med_hp

        # 3. State Transition Debouncer
        if tentative_state != self.current_state:
            if tentative_state == self.candidate_state:
                self.candidate_frames += 1
            else:
                self.candidate_state = tentative_state
                self.candidate_frames = 1

            # Determine required frames for candidate state
            if tentative_state == "DEAD":
                req_frames = self.dead_frames_required
            elif tentative_state == "KNOCKED":
                req_frames = self.knocked_frames_required
            else:
                req_frames = self.alive_frames_required

            if self.candidate_frames >= req_frames:
                self.current_state = tentative_state
                self.candidate_frames = 0
        else:
            self.candidate_state = self.current_state
            self.candidate_frames = 0

        # Enforce strict HP constraints based on confirmed state
        if self.current_state == "DEAD":
            smoothed_hp = 0.0
            self.current_smoothed_hp = 0.0
        else:
            smoothed_hp = self.current_smoothed_hp

        return {
            'hp': round(float(smoothed_hp), 1),
            'state': self.current_state,
            'raw_hp': raw_hp,
            'is_debouncing': bool(self.candidate_frames > 0)
        }


class TemporalFilter:
    """
    Multi-Slot Temporal Filter Manager:
    - Maintains 4 SlotFilter instances (for the 4 spectator slots).
    - Instant Buffer Flush on team switch (zero HP smear).
    """

    def __init__(self, config_or_path: Optional[Any] = None, num_slots: int = 4):
        self.num_slots = num_slots
        self.median_window = 2
        self.hysteresis_pct = 0.5
        self.dead_frames_required = 2
        self.knocked_frames_required = 1
        self.alive_frames_required = 1

        self.last_team_id: Optional[Any] = None

        if config_or_path is not None:
            if isinstance(config_or_path, str) and os.path.exists(config_or_path):
                with open(config_or_path, 'r', encoding='utf-8') as f:
                    cfg = json.load(f)
                self._load_config_dict(cfg)
            elif isinstance(config_or_path, dict):
                self._load_config_dict(config_or_path)

        self.slots = [
            SlotFilter(
                median_window=self.median_window,
                hysteresis_pct=self.hysteresis_pct,
                dead_frames_required=self.dead_frames_required,
                knocked_frames_required=self.knocked_frames_required,
                alive_frames_required=self.alive_frames_required
            ) for _ in range(self.num_slots)
        ]

    def _load_config_dict(self, cfg: Dict[str, Any]):
        if "smoothing" in cfg:
            s = cfg["smoothing"]
            if "median_window" in s:
                self.median_window = int(s["median_window"])
            if "hysteresis_pct" in s:
                self.hysteresis_pct = float(s["hysteresis_pct"])

        if "debounce" in cfg:
            d = cfg["debounce"]
            if "dead_frames_required" in d:
                self.dead_frames_required = int(d["dead_frames_required"])
            if "knocked_frames_required" in d:
                self.knocked_frames_required = int(d["knocked_frames_required"])
            if "alive_frames_required" in d:
                self.alive_frames_required = int(d["alive_frames_required"])

    def flush_buffers(self, team_id: Optional[Any] = None):
        """
        Instant Buffer Flush: Clears all temporal filters immediately.
        Triggered when switching spectators to avoid smearing Team A's HP onto Team B.
        """
        for slot in self.slots:
            slot.reset(initial_hp=100.0, initial_state="ALIVE")
        self.last_team_id = team_id

    def filter_observations(
        self,
        raw_observations: List[Dict[str, Any]],
        team_id: Optional[Any] = None
    ) -> List[Dict[str, Any]]:
        """
        Processes a list of 4 raw bar observations through temporal filtering.
        """
        # Instant flush on team switch
        if team_id is not None and self.last_team_id is not None and team_id != self.last_team_id:
            self.flush_buffers(team_id)
        elif self.last_team_id is None and team_id is not None:
            self.last_team_id = team_id

        filtered_results = []
        for i, obs in enumerate(raw_observations):
            if i >= len(self.slots):
                break
            res = self.slots[i].update(obs['raw_hp'], obs['state'])
            res['slot'] = i + 1
            filtered_results.append(res)

        return filtered_results
