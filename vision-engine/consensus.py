import time
import hashlib
from typing import Dict, List, Optional, Tuple

class TemporalConsensusEngine:
  """
  Stage 5: Temporal Consensus & Revival-Aware Deduplication
  - Multi-frame voting (requires candidate in >= 2 of 3 consecutive samples)
  - 15-second sliding hash cooldown for H(killer_id, victim_id)
  """
  def __init__(self, cooldown_seconds: float = 15.0, vote_window_seconds: float = 3.0):
    self.cooldown_seconds = cooldown_seconds
    self.vote_window_seconds = vote_window_seconds
    # sliding cooldown store: hash -> last_committed_timestamp
    self.cooldown_tracker: Dict[str, float] = {}
    # candidate buffer: hash -> list of timestamps
    self.observation_buffer: Dict[str, List[float]] = {}

  def has_pending_votes(self) -> bool:
    """Returns True if any kill candidates are currently awaiting multi-frame consensus."""
    return len(self.observation_buffer) > 0

  @staticmethod
  def compute_event_hash(killer_id: Optional[str], victim_id: str) -> str:
    key = f"{killer_id or 'ENV'}->{victim_id}"
    return hashlib.md5(key.encode('utf-8')).hexdigest()

  def record_observation(
    self, 
    killer_id: Optional[str], 
    victim_id: str, 
    confidence: float,
    timestamp: Optional[float] = None
  ) -> Tuple[bool, str]:
    """
    Records a detected kill candidate from a frame.
    Returns: (is_confirmed_to_commit, reason_or_status)
    """
    now = timestamp if (timestamp is not None and timestamp > 0) else time.time()
    event_hash = self.compute_event_hash(killer_id, victim_id)

    # Clean old cooldown records
    self._purge_stale_records(now)

    # Check 15-second revival cooldown
    if event_hash in self.cooldown_tracker:
      elapsed = now - self.cooldown_tracker[event_hash]
      if elapsed < self.cooldown_seconds:
        return False, f"COOLDOWN_ACTIVE ({elapsed:.1f}s / {self.cooldown_seconds}s)"

    # Add to rolling observation buffer
    if event_hash not in self.observation_buffer:
      self.observation_buffer[event_hash] = []
    
    # Filter observations older than vote window
    self.observation_buffer[event_hash] = [
      t for t in self.observation_buffer[event_hash]
      if now - t <= self.vote_window_seconds
    ]
    self.observation_buffer[event_hash].append(now)

    # 2 of 3 consensus check: at least 2 observations within window
    if len(self.observation_buffer[event_hash]) >= 2:
      # Commit event and activate 15s cooldown
      self.cooldown_tracker[event_hash] = now
      del self.observation_buffer[event_hash]
      return True, "CONSENSUS_REACHED"

    return False, "AWAITING_MULTI_FRAME_VOTE"

  def _purge_stale_records(self, now: float):
    stale_cooldowns = [
      h for h, t in self.cooldown_tracker.items() 
      if now - t > self.cooldown_seconds * 2
    ]
    for h in stale_cooldowns:
      del self.cooldown_tracker[h]

    stale_buffer = [
      h for h, times in self.observation_buffer.items()
      if not times or (now - times[-1] > self.vote_window_seconds)
    ]
    for h in stale_buffer:
      del self.observation_buffer[h]

