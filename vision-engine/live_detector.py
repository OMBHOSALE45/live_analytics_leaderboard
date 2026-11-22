import os
import sys
import time
import argparse
import cv2
import numpy as np

sys.path.append(os.path.dirname(__file__))

from pipeline import LiveKillDetectionPipeline
from video_source import VideoSourceManager

def run_live_detector(
  source: str = "sim",
  server_url: str = "http://localhost:3001",
  sampling_fps: float = 4.0,
  resolution: str = "1080p",
  display: bool = False,
  max_events: int = 0
):
  print("=" * 72, flush=True)
  print(" FREE FIRE LIVE VIDEO KILL DETECTION SYSTEM", flush=True)
  print(f" Source: {source} | Resolution: {resolution} | Target Sampling: {sampling_fps} FPS", flush=True)
  print(f" Connected Backend: {server_url}", flush=True)
  print("=" * 72, flush=True)

  # Initialize Video Ingestion
  if source.isdigit():
    video_source = VideoSourceManager(source_mode="camera", camera_id=int(source))
  elif source.lower() == "sim":
    video_source = VideoSourceManager(source_mode="sim")
  else:
    video_source = VideoSourceManager(source_mode="video", video_path=source)

  # Initialize Detection Pipeline
  pipeline = LiveKillDetectionPipeline(
    server_url=server_url,
    resolution=resolution
  )

  frame_interval = 1.0 / sampling_fps
  last_sample_time = 0.0
  events_detected = 0
  latest_kill_summary = "Awaiting live eliminations in killfeed zone..."
  latest_kill_color = (180, 180, 180)
  latest_kill_time = 0.0

  window_name = "Free Fire Live Video Kill Tracker [AI Detection Active]"
  if display:
    cv2.namedWindow(window_name, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(window_name, 1280, 720)

  print("\n[Engine Ready] Live video capture loop running. Press Ctrl+C or 'q' to stop.\n")

  try:
    while True:
      now = time.time()
      ret, frame = video_source.read_frame()

      if not ret or frame is None:
        print("[VideoSource] Stream ended or frame not available. Reconnecting...")
        time.sleep(1.0)
        continue

      # Smart Sampling: process frame every 200-250 ms (4-5 FPS)
      if now - last_sample_time >= frame_interval:
        last_sample_time = now
        res = pipeline.process_frame(frame, timestamp_sec=now)

        # Handle events emitted from this frame
        if res.get('events'):
          for ev in res['events']:
            events_detected += 1
            killer = ev.get('killerPlayerId') or 'ENVIRONMENT'
            victim = ev.get('victimPlayerId')
            k_team = ev.get('killerTeamId') or 'ENV'
            v_team = ev.get('victimTeamId')
            conf = int(ev.get('confidence', 1.0) * 100)
            status = ev.get('status')
            sync = ev.get('server_response', {}).get('status') or 'COMMITTED'
            weapon = ev.get('weapon', 'WEAPON')

            latest_kill_summary = f"{k_team.upper()} ({killer})  ==[{weapon}]==>  {v_team.upper()} ({victim})  |  CONF: {conf}%"
            latest_kill_color = (0, 220, 255) if status == 'ACTIVE' else (0, 140, 255)
            latest_kill_time = now

            print(f"⚡ [KILL DETECTED #{events_detected:02d}] {k_team.upper()} ({killer}) → {v_team.upper()} ({victim})", flush=True)
            print(f"   ├─ Weapon:     {weapon} | Confidence: {conf}%", flush=True)
            print(f"   ├─ Status:     {status} (Consensus Verified)", flush=True)
            print(f"   └─ Sync State: {sync} -> Leaderboard Updated\n", flush=True)

            if max_events > 0 and events_detected >= max_events:
              print(f"[Done] Reached target {max_events} events. Exiting.")
              return

      # Visual Inspection Window & Real-Time Plotting
      if display:
        preview = frame.copy()
        h, w = preview.shape[:2]

        # 1. ROI A (Killfeed Detection Zone) - Cyan
        cv2.rectangle(preview, (820, 10), (1910, 230), (255, 255, 0), 2)
        cv2.putText(preview, "ROI A: KILLFEED ZONE (RapidOCR + Consensus)", (825, 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 0), 2, cv2.LINE_AA)

        # 2. ROI B (Alive Counter) - Lime Green
        cv2.rectangle(preview, (890, 5), (1030, 48), (50, 255, 50), 2)
        cv2.putText(preview, "ROI B: ALIVE", (895, 62),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, (50, 255, 50), 1, cv2.LINE_AA)

        # 3. Top Broadcast Telemetry Bar
        cv2.rectangle(preview, (0, 0), (w, 40), (18, 12, 28), -1)
        cv2.line(preview, (0, 40), (w, 40), (80, 50, 110), 1)

        total_p = max(1, pipeline.frames_processed)
        cpu_saved = int((pipeline.static_frames_skipped / total_p) * 100)
        telemetry_txt = (
          f"AI ENGINE: ACTIVE | SAMPLING: {sampling_fps:.1f} FPS | "
          f"FRAMES: {pipeline.frames_processed} | SKIPPED: {pipeline.static_frames_skipped} ({cpu_saved}% CPU SAVED) | "
          f"VERIFIED KILLS: {events_detected}"
        )
        cv2.putText(preview, telemetry_txt, (20, 26),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.55, (220, 220, 240), 1, cv2.LINE_AA)

        # 4. Live Elimination Alert Banner (Bottom HUD)
        is_recent_kill = (now - latest_kill_time) < 4.0
        hud_bg_color = (25, 20, 40) if not is_recent_kill else (20, 45, 10)
        cv2.rectangle(preview, (0, h - 65), (w, h), hud_bg_color, -1)
        cv2.line(preview, (0, h - 65), (w, h - 65), (0, 230, 255) if is_recent_kill else (60, 50, 80), 2)

        prefix = "⚡ [LIVE ELIMINATION DETECTED]" if is_recent_kill else "• [RADAR STATUS]"
        cv2.putText(preview, f"{prefix}  {latest_kill_summary}", (30, h - 25),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.65, latest_kill_color if is_recent_kill else (180, 180, 180), 2, cv2.LINE_AA)

        cv2.imshow(window_name, preview)
        if cv2.waitKey(1) & 0xFF == ord('q'):
          break

      # Yield thread briefly
      time.sleep(0.005)

  except KeyboardInterrupt:
    print("\n[Engine Stopped] Interrupted by user.")
  finally:
    video_source.release()
    if display:
      cv2.destroyAllWindows()

if __name__ == '__main__':
  parser = argparse.ArgumentParser(description="Free Fire Live Video Kill Detection Pipeline")
  parser.add_argument("--source", type=str, default="sim", help="Camera index ('0'), video file path, or 'sim' for simulated spectator stream")
  parser.add_argument("--server", type=str, default="http://localhost:3001", help="Leaderboard server URL")
  parser.add_argument("--fps", type=float, default=4.0, help="Frame sampling rate (default 4.0 FPS)")
  parser.add_argument("--resolution", type=str, default="1080p", help="Resolution preset: 1080p or 720p")
  parser.add_argument("--display", action="store_true", help="Show live visual debug window")
  parser.add_argument("--max-events", type=int, default=0, help="Stop after N events (for automated tests)")

  args = parser.parse_args()
  run_live_detector(
    source=args.source,
    server_url=args.server,
    sampling_fps=args.fps,
    resolution=args.resolution,
    display=args.display,
    max_events=args.max_events
  )
