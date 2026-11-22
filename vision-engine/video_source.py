import cv2
import numpy as np
import time
import json
import random
import os
from typing import Optional, Tuple

class SimulatedSpectatorFeed:
  """
  Generates authentic 1080p Free Fire spectator match frames in real time:
  - Bermuda island background with cyber grid overlay
  - Dynamic killfeed notification banners sliding into ROI A
  - Live Alive counter in ROI B ticking down
  - FFWS tournament HUD branding & match clock
  """
  def __init__(self, roster_path: Optional[str] = None, width: int = 1920, height: int = 1080):
    self.width = width
    self.height = height

    if roster_path is None:
      roster_path = os.path.join(os.path.dirname(__file__), '..', 'config', 'sample_roster.json')

    with open(roster_path, 'r', encoding='utf-8') as f:
      self.roster = json.load(f)

    self.teams = self.roster['teams']
    self.weapons = ['AWM', 'M1887', 'SCAR', 'MP40', 'GROZA', 'WOODPECKER', 'GRENADE']
    self.active_banners = [] # list of active banner objects currently on screen
    self.alive_count = 48
    self.last_kill_spawn = 0.0
    self.frame_index = 0

  def _draw_hud_base(self) -> np.ndarray:
    """Renders 1080p spectator view background and HUD overlay"""
    frame = np.zeros((self.height, self.width, 3), dtype=np.uint8)

    # Gradient Bermuda Terrain / Cyber Spectator Background
    for y in range(self.height):
      r = int(12 + (y / self.height) * 16)
      g = int(8 + (y / self.height) * 12)
      b = int(24 + (y / self.height) * 28)
      frame[y, :] = (b, g, r)

    # Subtle tactical grid
    grid_spacing = 60
    for x in range(0, self.width, grid_spacing):
      cv2.line(frame, (x, 0), (x, self.height), (35, 20, 50), 1)
    for y in range(0, self.height, grid_spacing):
      cv2.line(frame, (0, y), (self.width, y), (35, 20, 50), 1)

    # Top Bar HUD
    cv2.rectangle(frame, (0, 0), (self.width, 60), (18, 10, 36), -1)
    cv2.line(frame, (0, 60), (self.width, 60), (120, 60, 200), 1)

    # Tournament Title
    cv2.putText(frame, "FREE FIRE WORLD SERIES - BERMUDA GRAND FINALS", (40, 40),
                cv2.FONT_HERSHEY_SIMPLEX, 0.85, (255, 255, 255), 2, cv2.LINE_AA)

    # Alive Counter (ROI B: x=890, y=5, w=140, h=35)
    cv2.rectangle(frame, (890, 8), (1030, 48), (30, 16, 55), -1)
    cv2.rectangle(frame, (890, 8), (1030, 48), (91, 226, 255), 1)
    cv2.putText(frame, f"ALIVE: {self.alive_count:02d}", (905, 36),
                cv2.FONT_HERSHEY_SIMPLEX, 0.75, (91, 226, 255), 2, cv2.LINE_AA)

    return frame

  def spawn_kill_banner(self):
    """Spawns an authentic elimination banner using current lobby roster"""
    killer_team = random.choice(self.teams)
    victim_team = random.choice([t for t in self.teams if t['id'] != killer_team['id']])
    killer_player = random.choice(killer_team['players'])
    victim_player = random.choice(victim_team['players'])
    weapon = random.choice(self.weapons)

    # Realistic in-game stylized strings (with clan tags / Unicode embellishments)
    killer_text = f"{killer_player['ign']}"
    victim_text = f"{victim_player['ign']}"

    banner = {
      'killer_text': killer_text,
      'victim_text': victim_text,
      'weapon': weapon,
      'spawn_time': time.time(),
      'duration': 4.5, # Remains visible 4-5 seconds like actual Free Fire killfeed
      'alpha': 1.0
    }

    self.active_banners.insert(0, banner)
    if len(self.active_banners) > 4:
      self.active_banners.pop()

    self.alive_count = max(2, self.alive_count - 1)

  def get_frame(self) -> np.ndarray:
    """Returns next frame in simulated spectator stream"""
    self.frame_index += 1
    now = time.time()

    # Spawn new kill banner every 3.8 to 6 seconds
    if now - self.last_kill_spawn >= 4.0:
      self.spawn_kill_banner()
      self.last_kill_spawn = now

    frame = self._draw_hud_base()

    # Clean expired banners
    self.active_banners = [b for b in self.active_banners if now - b['spawn_time'] < b['duration']]

    # Render Killfeed in ROI A (x=820, y=10, width=1090, height=220)
    # Typically Free Fire notifications appear in upper right stack
    feed_x = 830
    feed_y_start = 65
    row_height = 48

    for idx, b in enumerate(self.active_banners):
      y_pos = feed_y_start + (idx * row_height)

      # Semi-transparent dark banner strip with cyan/purple gradient border
      cv2.rectangle(frame, (feed_x, y_pos), (feed_x + 680, y_pos + 42), (24, 14, 46), -1)
      cv2.rectangle(frame, (feed_x, y_pos), (feed_x + 680, y_pos + 42), (180, 100, 255), 1)

      # Killer Name (Left)
      cv2.putText(frame, b['killer_text'], (feed_x + 20, y_pos + 28),
                  cv2.FONT_HERSHEY_SIMPLEX, 0.75, (255, 230, 80), 2, cv2.LINE_AA)

      # Weapon / Action Icon (Center)
      cv2.rectangle(frame, (feed_x + 290, y_pos + 6), (feed_x + 390, y_pos + 36), (40, 25, 75), -1)
      cv2.putText(frame, b['weapon'], (feed_x + 300, y_pos + 26),
                  cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 90, 90), 2, cv2.LINE_AA)

      # Victim Name (Right)
      cv2.putText(frame, b['victim_text'], (feed_x + 415, y_pos + 28),
                  cv2.FONT_HERSHEY_SIMPLEX, 0.75, (240, 240, 255), 2, cv2.LINE_AA)

    return frame


class VideoSourceManager:
  """
  Unified Video Source Manager:
  - Camera / OBS Virtual Camera
  - Video File (.mp4/.mkv)
  - Simulated Live Spectator Feed
  """
  def __init__(self, source_mode: str = "sim", video_path: Optional[str] = None, camera_id: int = 0):
    self.source_mode = source_mode
    self.cap = None
    self.sim_feed = None

    if source_mode == "camera":
      # Try DirectShow on Windows, fallback to default
      self.cap = cv2.VideoCapture(camera_id, cv2.CAP_DSHOW)
      if not self.cap.isOpened():
        self.cap = cv2.VideoCapture(camera_id)
      print(f"[VideoSource] Connected to Camera index {camera_id}")

    elif source_mode == "video":
      if not video_path or not os.path.exists(video_path):
        raise FileNotFoundError(f"Video file not found: {video_path}")
      self.cap = cv2.VideoCapture(video_path)
      print(f"[VideoSource] Opened video file: {video_path}")

    else:
      self.source_mode = "sim"
      self.sim_feed = SimulatedSpectatorFeed()
      print("[VideoSource] Initialized Real-Time Simulated Spectator Stream (1080p Free Fire)")

  def read_frame(self) -> Tuple[bool, Optional[np.ndarray]]:
    if self.source_mode == "sim":
      frame = self.sim_feed.get_frame()
      return True, frame

    if self.cap is not None:
      ret, frame = self.cap.read()
      if not ret and self.source_mode == "video":
        # Loop video file for continuous testing
        self.cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
        ret, frame = self.cap.read()
      return ret, frame

    return False, None

  def release(self):
    if self.cap is not None:
      self.cap.release()

