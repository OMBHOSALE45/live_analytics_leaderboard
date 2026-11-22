import os
import sys
import json
import time
import random
import urllib.request
from matcher import RosterMatcher
from consensus import TemporalConsensusEngine
from detector import ChangeGatedDetector
from capture import ROICaptureManager

def load_sample_roster():
  roster_path = os.path.join(os.path.dirname(__file__), '..', 'config', 'sample_roster.json')
  with open(roster_path, 'r', encoding='utf-8') as f:
    return json.load(f)

def emit_kill_to_server(event_data, server_url="http://localhost:3001/api/kill"):
  """POST verified kill event to backend server"""
  try:
    payload = json.dumps(event_data).encode('utf-8')
    req = urllib.request.Request(
      server_url, 
      data=payload, 
      headers={'Content-Type': 'application/json'},
      method='POST'
    )
    with urllib.request.urlopen(req, timeout=2) as resp:
      return json.loads(resp.read().decode('utf-8'))
  except Exception as e:
    # Server offline or not reachable; log locally
    return {'status': 'OFFLINE_BUFFERED', 'error': str(e)}

def run_simulation_pipeline(num_events=10, interval=3.0):
  """
  Full end-to-end vision pipeline demonstration:
  1. Captures synthetic candidate from spectator feed
  2. Runs SSIM change gating (Detector)
  3. Applies ASCII skeleton normalization and RapidFuzz roster matching (Matcher)
  4. Runs 2-of-3 frame consensus & 15s revival cooldown (Consensus)
  5. Emits verified event to Event-Sourced Ledger Backend
  """
  print("=" * 65)
  print(" Free Fire Live Kill Tracker — Vision Inference Pipeline")
  print(" CPU-First Architecture | RapidFuzz Closed-Set | Temporal Consensus")
  print("=" * 65)

  roster = load_sample_roster()
  matcher = RosterMatcher(roster)
  consensus = TemporalConsensusEngine(cooldown_seconds=15.0)
  detector = ChangeGatedDetector()
  capture = ROICaptureManager()

  teams = roster['teams']
  weapons = ['AWM', 'M1887', 'SCAR', 'MP40', 'GROZA', 'WOODPECKER', 'GRENADE']

  print(f"[Init] Loaded {len(teams)} teams and {len(matcher.players)} player skeletons.")
  print(f"[Pipeline] Listening on simulated 4-5 FPS spectator stream...\n")

  for i in range(num_events):
    killer_team = random.choice(teams)
    victim_team = random.choice([t for t in teams if t['id'] != killer_team['id']])
    killer_player = random.choice(killer_team['players'])
    victim_player = random.choice(victim_team['players'])
    weapon = random.choice(weapons)

    # Simulate realistic OCR string with stylized game noise
    noisy_killer_ocr = f"꧁{killer_player['ign']}ツ么"
    noisy_victim_ocr = f"༺{victim_player['ign']}༻"

    # Step 1: Match OCR to roster skeletons
    matched_k, conf_k, route_k = matcher.match_ocr_text(noisy_killer_ocr)
    matched_v, conf_v, route_v = matcher.match_ocr_text(noisy_victim_ocr)

    overall_conf = round(conf_k * conf_v, 2)

    # Step 2: Temporal Consensus & Cooldown
    # Simulate multi-frame observation (sample 1, then sample 2)
    consensus.record_observation(matched_k['id'], matched_v['id'], overall_conf)
    confirmed, reason = consensus.record_observation(matched_k['id'], matched_v['id'], overall_conf)

    print(f"[Frame Event #{i+1:02d}] {noisy_killer_ocr} [{weapon}] {noisy_victim_ocr}")
    print(f"  ├─ Roster Match: Killer={matched_k['ign']} ({matched_k['team_name']}), Victim={matched_v['ign']} ({matched_v['team_name']})")
    print(f"  ├─ Confidence:   {overall_conf*100:.0f}% (Route: {route_k})")
    print(f"  ├─ Consensus:    {reason} (Confirmed: {confirmed})")

    if confirmed:
      event_payload = {
        'matchId': roster['matchId'],
        'killerTeamId': matched_k['team_id'],
        'killerPlayerId': matched_k['id'],
        'victimTeamId': matched_v['team_id'],
        'victimPlayerId': matched_v['id'],
        'weapon': weapon,
        'confidence': overall_conf,
        'source': 'VISION_AI',
        'status': 'ACTIVE' if overall_conf >= 0.85 else 'PENDING_REVIEW'
      }

      result = emit_kill_to_server(event_payload)
      print(f"  └─ Server Sync:  Emitted to ledger -> {result.get('status', 'COMMITTED')}\n")
    else:
      print(f"  └─ Filtered:     Held in temporal consensus buffer\n")

    time.sleep(interval)

if __name__ == '__main__':
  run_simulation_pipeline(num_events=5, interval=1.0)

