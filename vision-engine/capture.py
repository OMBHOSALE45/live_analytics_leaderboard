import json
import os
from typing import Dict, Any, Optional

class ROICaptureManager:
  """
  Stage 2: Resolution-Normalized Coordinate Masking
  Loads presets from config/roi_presets.json and slices incoming frames into:
  - ROI A: Kill-Feed Zone
  - ROI B: Alive Counter
  - ROI C: Game-State Guard
  """
  def __init__(self, preset_path: Optional[str] = None, resolution: str = "1080p"):
    if preset_path is None:
      preset_path = os.path.join(os.path.dirname(__file__), '..', 'config', 'roi_presets.json')
    
    self.resolution = resolution
    self.presets = self._load_presets(preset_path)

  def _load_presets(self, path: str) -> Dict[str, Any]:
    if os.path.exists(path):
      with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)
    # Default 1080p fallback
    return {
      "1080p": {
        "killfeed": { "x": 820, "y": 10, "width": 1090, "height": 220 },
        "alive_counter": { "x": 890, "y": 5, "width": 140, "height": 35 },
        "game_state_guard": { "x": 400, "y": 480, "width": 1120, "height": 120 }
      }
    }

  def crop_roi(self, frame, roi_key: str):
    config = self.presets.get(self.resolution, {}).get(roi_key)
    if not config or frame is None:
      return None

    x, y, w, h = config['x'], config['y'], config['width'], config['height']
    return frame[y:y+h, x:x+w]

