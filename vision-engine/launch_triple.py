"""Concurrent launcher for the updated 12-team + Live Spectator pipeline:
- Engine 1 (stream_1): All 12 teams on a single OpenCV scoreboard engine
- Spectator Feed (spectator): Live stream feed (Slot 3 player names + yellow eye + HP)
"""

import argparse
import json
import os
import signal
import subprocess
import sys
import time
from typing import Optional
import urllib.request

from team_names import (
  default_team_names_path,
  load_team_names,
  prompt_lobby_team_names,
  push_team_names_to_server,
)


def _no_proxy_opener() -> urllib.request.OpenerDirector:
  os.environ['NO_PROXY'] = 'localhost,127.0.0.1'
  os.environ['no_proxy'] = 'localhost,127.0.0.1'
  return urllib.request.build_opener(urllib.request.ProxyHandler({}))


def _is_server_healthy(opener: urllib.request.OpenerDirector, server_url: str) -> bool:
  try:
    req = urllib.request.Request(f"{server_url}/health", method='GET')
    with opener.open(req, timeout=0.3) as resp:
      return resp.status == 200
  except Exception:
    return False


def _reset_barrier(opener: urllib.request.OpenerDirector, server_url: str):
  try:
    req = urllib.request.Request(
      f"{server_url}/api/streams/barrier",
      data=json.dumps({'reset': True}).encode('utf-8'),
      headers={'Content-Type': 'application/json'},
      method='POST'
    )
    with opener.open(req, timeout=1.0):
      pass
  except Exception:
    pass


def _build_worker_cmd(
  detector_script: str,
  source: str,
  stream_id: str,
  role: str,
  server_url: str,
  max_teams: int,
  gap: float,
  display: bool,
  calibrate: bool,
  calibrate_hp: bool,
  calibrate_names: bool,
  calib_file: Optional[str],
  hp_config: Optional[str],
  team_names_file: str,
  enable_hp: bool,
  sync_peers: int
) -> list[str]:
  cmd = [
    sys.executable,
    '-u',
    detector_script,
    '--source', source,
    '--server', server_url,
    '--stream-id', stream_id,
    '--role', role,
    '--max-teams', str(max_teams),
    '--gap', str(gap),
    '--sync-peers', str(sync_peers),
    '--team-names', team_names_file,
    '--no-local-json',
  ]
  cmd.append('--display' if display else '--no-display')
  if not enable_hp:
    cmd.append('--no-hp')
  if calibrate:
    cmd.append('--calibrate')
  if calibrate_hp and role == 'spectator':
    cmd.append('--calibrate-hp')
  if calibrate_names and role == 'spectator':
    cmd.append('--calibrate-names')
  if calib_file:
    cmd.extend(['--calibration', calib_file])
  if hp_config and role == 'spectator':
    cmd.extend(['--hp-config', hp_config])
  return cmd


def main():
  parser = argparse.ArgumentParser(description="Launch 12-team Scoreboard Engine + Live Spectator Feed concurrently")
  parser.add_argument("--source1", type=str, default=os.path.join('vision-engine', 'Assets', 'video_6.mp4'), help="Source for Engine 1 (all 12 teams)")
  parser.add_argument("--source3", "--source2", dest="source_spectator", type=str, default=os.path.join('vision-engine', 'Assets', 'video_10.mp4'), help="Source for Live Spectator feed (player names + eye + HP)")
  parser.add_argument("--server", type=str, default="http://localhost:3001", help="Leaderboard server URL")
  parser.add_argument("--gap", type=float, default=0.3, help="Sync cadence in seconds (default 0.3s; HP/eye/names/kills sync immediately)")
  parser.add_argument("--display", action="store_true", default=True, help="Show OpenCV windows for both engines (default: enabled)")
  parser.add_argument("--no-display", dest="display", action="store_false", help="Disable OpenCV windows")
  parser.add_argument("--calibrate", action="store_true", default=False, help="Run interactive Slot 1/2 calibration on startup")
  parser.add_argument("--calibrate-hp", action="store_true", default=False, help="Run HP border dark-mask calibration on Spectator feed startup")
  parser.add_argument("--calibrate-names", action="store_true", default=False, help="Run Slot 3 player-names calibration on Spectator feed startup")
  parser.add_argument("--calib1", type=str, default=None, help="Slot calibration JSON for Engine 1 (12 teams)")
  parser.add_argument("--calib3", type=str, default=None, help="Slot calibration JSON for Spectator feed")
  parser.add_argument("--hp-config", type=str, default=None, help="HP dark-mask config JSON for Spectator feed")
  parser.add_argument("--team-names", type=str, default=None, help="12-team slot-color JSON path (default config/team_names.json)")
  parser.add_argument("--setup-teams", action="store_true", default=False, help="Prompt to enter all 12 lobby team names before starting engines")
  parser.add_argument("--skip-setup", action="store_true", default=False, help="Skip lobby team-name prompt and use saved config/team_names.json")
  args = parser.parse_args()

  project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
  detector_script = os.path.join(os.path.dirname(__file__), 'scoreboard_detector.py')
  server_url = args.server.rstrip('/').replace('localhost', '127.0.0.1')
  opener = _no_proxy_opener()
  team_names_path = args.team_names or default_team_names_path(project_root)

  # Step 1: Lobby 12-team color-name entry BEFORE starting Engine 1
  if args.setup_teams:
    team_map = prompt_lobby_team_names(team_names_path, server_url=server_url)
  elif not args.skip_setup:
    try:
      ans = input("[Lobby] Enter/edit 12 team names by slot color before starting? [y/N]: ").strip().lower()
    except EOFError:
      ans = ""
    if ans in ("y", "yes"):
      team_map = prompt_lobby_team_names(team_names_path, server_url=server_url)
    else:
      team_map = load_team_names(team_names_path)
  else:
    team_map = load_team_names(team_names_path)

  workers: list[subprocess.Popen] = []

  def shutdown(*_):
    for proc in workers:
      if proc.poll() is None:
        proc.terminate()
    for proc in workers:
      try:
        proc.wait(timeout=3.0)
      except Exception:
        proc.kill()

  def _handle_stop(*_):
    raise KeyboardInterrupt()

  signal.signal(signal.SIGINT, _handle_stop)
  if hasattr(signal, 'SIGTERM'):
    signal.signal(signal.SIGTERM, _handle_stop)

  try:
    if _is_server_healthy(opener, server_url):
      _reset_barrier(opener, server_url)
      if team_map:
        push_team_names_to_server(team_map, server_url)
    else:
      print(f"[Launcher Warning] Server not detected at {server_url}. Start your Node server manually for sync.", flush=True)

    cmd1 = _build_worker_cmd(
      detector_script, args.source1, 'stream_1', 'scoreboard', server_url,
      12, args.gap, args.display, args.calibrate, False, False, args.calib1, None,
      team_names_path, enable_hp=False, sync_peers=2
    )
    cmd_spec = _build_worker_cmd(
      detector_script, args.source_spectator, 'spectator', 'spectator', server_url,
      12, args.gap, args.display, args.calibrate, args.calibrate_hp, args.calibrate_names, args.calib3, args.hp_config,
      team_names_path, enable_hp=True, sync_peers=2
    )

    print("[Launcher] Spawning Engine 1 (12 teams) and Spectator Feed (Player Names + Eye + HP) simultaneously...", flush=True)
    workers.append(subprocess.Popen(cmd1, cwd=project_root))
    workers.append(subprocess.Popen(cmd_spec, cwd=project_root))

    while True:
      codes = [p.poll() for p in workers]
      if all(c is not None for c in codes):
        print(f"[Launcher] All workers exited (codes={codes}).", flush=True)
        break
      time.sleep(0.2)
  except KeyboardInterrupt:
    print("\n[Launcher] Stopping vision pipeline...", flush=True)
  finally:
    shutdown()


if __name__ == '__main__':
  main()
