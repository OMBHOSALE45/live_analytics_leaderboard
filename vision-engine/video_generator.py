import cv2
import numpy as np
import os
import sys

# Add vision-engine to path
sys.path.append(os.path.dirname(__file__))
from video_source import SimulatedSpectatorFeed

def generate_benchmark_video(output_path: str = "test_match_1080p.mp4", duration_seconds: int = 30, fps: int = 30):
  """
  Generates an authentic 1080p MP4 spectator feed video containing live Free Fire match HUD,
  alive counters, and animated kill notifications using current roster players.
  """
  print(f"[Generator] Creating 1080p benchmark match video -> {output_path} ({duration_seconds}s @ {fps}fps)...")
  sim = SimulatedSpectatorFeed()

  fourcc = cv2.VideoWriter_fourcc(*'mp4v')
  out = cv2.VideoWriter(output_path, fourcc, fps, (1920, 1080))

  total_frames = duration_seconds * fps
  for i in range(total_frames):
    frame = sim.get_frame()
    out.write(frame)
    if i % (fps * 5) == 0:
      progress = (i / total_frames) * 100
      print(f"  ├─ Rendering progress: {progress:.0f}% ({i}/{total_frames} frames)")

  out.release()
  file_size_mb = os.path.getsize(output_path) / (1024 * 1024)
  print(f"[Generator] Video successfully generated: {output_path} ({file_size_mb:.2f} MB)")
  return output_path

if __name__ == '__main__':
  video_file = os.path.join(os.path.dirname(__file__), '..', 'test_match_1080p.mp4')
  generate_benchmark_video(video_file, duration_seconds=20, fps=20)

