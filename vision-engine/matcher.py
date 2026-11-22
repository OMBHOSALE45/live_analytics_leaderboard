import re
import unicodedata
from typing import Dict, List, Optional, Tuple

class RosterMatcher:
  """
  Stage 1 & 4: Closed-Set Roster Normalization & RapidFuzz Matcher
  Matches noisy OCR text strings against known 48-player lobby manifest in < 1 ms.
  """
  def __init__(self, roster_data: dict):
    self.roster = roster_data
    self.players: List[dict] = []
    self.teams: Dict[str, dict] = {}
    self.skeleton_index: Dict[str, dict] = {}
    self._build_indexes()

  @staticmethod
  def normalize_skeleton(text: str) -> str:
    """
    Strips decorative Free Fire Unicode characters (꧁, ༺, ツ, 么, invisible spaces)
    into a clean alphanumeric skeleton.
    """
    if not text:
      return ""
    # Normalize unicode (NFKD decomposes ligatures & accents)
    normalized = unicodedata.normalize('NFKD', text)
    # Remove non-ASCII characters and special styling symbols
    ascii_only = normalized.encode('ASCII', 'ignore').decode('ASCII')
    # Lowercase and retain only alphanumeric characters
    cleaned = re.sub(r'[^a-zA-Z0-9]', '', ascii_only).lower()
    return cleaned

  def _build_indexes(self):
    for team in self.roster.get('teams', []):
      self.teams[team['id']] = team
      for p in team.get('players', []):
        player_entry = {
          'id': p.get('id', f"{team['id']}-{p['ign']}"),
          'ign': p['ign'],
          'team_id': team['id'],
          'team_name': team['name'],
          'role': p.get('role', 'Rusher'),
          'skeleton': p.get('normalizedSkeleton') or self.normalize_skeleton(p['ign'])
        }
        self.players.append(player_entry)
        self.skeleton_index[player_entry['skeleton']] = player_entry

  def match_ocr_text(self, ocr_text: str) -> Tuple[Optional[dict], float, str]:
    """
    Matches raw OCR text to nearest player skeleton.
    Returns: (matched_player_dict, confidence_0_to_1, route_decision)
    Route Decision:
      - 'AUTO_ACCEPT': confidence >= 0.85
      - 'HOLD_CONSENSUS': 0.65 <= confidence < 0.85
      - 'REFEREE_REVIEW': confidence < 0.65
    """
    candidate_skeleton = self.normalize_skeleton(ocr_text)
    if not candidate_skeleton:
      return None, 0.0, 'REFEREE_REVIEW'

    # Direct exact skeleton match
    if candidate_skeleton in self.skeleton_index:
      return self.skeleton_index[candidate_skeleton], 1.0, 'AUTO_ACCEPT'

    # Fuzzy match using Levenshtein / ratio heuristic
    best_player = None
    best_score = 0.0

    try:
      from rapidfuzz import fuzz
      for player in self.players:
        # Combine partial_ratio and WRatio for high accuracy on truncated names
        ratio = fuzz.ratio(candidate_skeleton, player['skeleton'])
        partial = fuzz.partial_ratio(candidate_skeleton, player['skeleton'])
        score = max(ratio, partial) / 100.0

        if score > best_score:
          best_score = score
          best_player = player
    except ImportError:
      # Lightweight fallback if rapidfuzz is not yet installed
      for player in self.players:
        target = player['skeleton']
        common = sum(1 for c in candidate_skeleton if c in target)
        score = (2.0 * common) / (len(candidate_skeleton) + len(target))
        if score > best_score:
          best_score = score
          best_player = player

    if best_score >= 0.85:
      route = 'AUTO_ACCEPT'
    elif best_score >= 0.65:
      route = 'HOLD_CONSENSUS'
    else:
      route = 'REFEREE_REVIEW'

    return best_player, round(best_score, 2), route

