"""Concurrent dual-stream launcher for 6+6 split Free Fire scoreboard tracking."""

import argparse
import json
import os
import signal
import subprocess
import sys
import time
from typing import Optional
import urllib.request


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
  server_url: str,
  max_teams: int,
  gap: float,
  display: bool,
  calibrate: bool,
  calib_file: Optional[str],
  sync_peers: int
) -> list[str]:
  cmd = [
    sys.executable,
    '-u',
    detector_script,
    '--source', source,
    '--server', server_url,
    '--stream-id', stream_id,
    '--max-teams', str(max_teams),
    '--gap', str(gap),
    '--sync-peers', str(sync_peers),
    '--no-local-json',
  ]
  cmd.append('--display' if display else '--no-display')
  if calibrate:
    cmd.append('--calibrate')
  if calib_file:
    cmd.extend(['--calibration', calib_file])
  return cmd


def main():
  parser = argparse.ArgumentParser(description="Launch two 6-team Free Fire vision streams concurrently")
  parser.add_argument("--source1", type=str, default=os.path.join('vision-engine', 'Assets', 'video_6.mp4'), help="Video/camera source for stream_1")
  parser.add_argument("--source2", type=str, default=os.path.join('vision-engine', 'Assets', 'video_7.mp4'), help="Video/camera source for stream_2")
  parser.add_argument("--server", type=str, default="http://localhost:3001", help="Leaderboard server URL")
  parser.add_argument("--gap", type=float, default=0.3, help="Periodic sync cadence in seconds (default 0.3s; kills sync immediately)")
  parser.add_argument("--max-teams", type=int, default=6, help="Max teams per stream (default 6)")
  parser.add_argument("--display", action="store_true", default=True, help="Show OpenCV preview windows for both streams (default: enabled)")
  parser.add_argument("--no-display", dest="display", action="store_false", help="Disable OpenCV preview windows for headless mode")
  parser.add_argument("--calibrate", action="store_true", default=False, help="Run interactive slot calibration on startup")
  parser.add_argument("--calib1", type=str, default=None, help="Optional calibration JSON path for stream_1")
  parser.add_argument("--calib2", type=str, default=None, help="Optional calibration JSON path for stream_2")
  args = parser.parse_args()

  project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
  detector_script = os.path.join(os.path.dirname(__file__), 'scoreboard_detector.py')
  server_url = args.server.rstrip('/').replace('localhost', '127.0.0.1')
  opener = _no_proxy_opener()

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
    else:
      print(f"[Launcher Warning] Server not detected at {server_url}. Start your Node server manually for sync.", flush=True)

    cmd1 = _build_worker_cmd(
      detector_script, args.source1, 'stream_1', server_url,
      args.max_teams, args.gap, args.display, args.calibrate, args.calib1, sync_peers=2
    )
    cmd2 = _build_worker_cmd(
      detector_script, args.source2, 'stream_2', server_url,
      args.max_teams, args.gap, args.display, args.calibrate, args.calib2, sync_peers=2
    )

    print("[Launcher] Spawning stream_1 and stream_2 simultaneously...", flush=True)
    workers.append(subprocess.Popen(cmd1, cwd=project_root))
    workers.append(subprocess.Popen(cmd2, cwd=project_root))

    while True:
      codes = [p.poll() for p in workers]
      if all(c is not None for c in codes):
        print(f"[Launcher] Both workers exited (codes={codes}).", flush=True)
        break
      time.sleep(0.2)
  except KeyboardInterrupt:
    print("\n[Launcher] Stopping dual-stream vision engines...", flush=True)
  finally:
    shutdown()


if __name__ == '__main__':
  main()
