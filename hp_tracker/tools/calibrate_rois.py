import os
import sys
import json
import argparse
import cv2
import numpy as np

# Ensure hp_tracker can be imported
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))


def interactive_calibrate(source: str, config_path: str):
    print("=" * 70)
    print(" HP TRACKER: INTERACTIVE ROI CALIBRATION TOOL")
    print(f" Source: {source} | Config: {config_path}")
    print(" Instructions:")
    print("   1. Select the Spectator HUD Canvas box (overall area). Press ENTER/SPACE.")
    print("   2. Sequentially select Bar 1, Bar 2, Bar 3, Bar 4. Press ENTER/SPACE after each.")
    print("=" * 70)

    # Load sample frame
    cap = None
    if source.isdigit():
        cap = cv2.VideoCapture(int(source))
        ret, frame = cap.read()
    elif source.endswith(('.mp4', '.avi', '.mov', '.mkv')):
        cap = cv2.VideoCapture(source)
        cap.set(cv2.CAP_PROP_POS_FRAMES, 50)
        ret, frame = cap.read()
    else:
        frame = cv2.imread(source)
        ret = frame is not None

    if not ret or frame is None:
        print(f"[Error] Failed to load frame from {source}")
        return

    h, w = frame.shape[:2]
    print(f"[Loaded Frame] Dimensions: {w} x {h}")

    # 1. Select Canvas ROI
    win_canvas = "Select 1: Spectator HUD Area (Press ENTER/SPACE)"
    r_canvas = cv2.selectROI(win_canvas, frame, fromCenter=False, showCrosshair=True)
    cv2.destroyWindow(win_canvas)

    if r_canvas[2] < 20 or r_canvas[3] < 20:
        print("[Warning] Selection canceled or too small. Keeping existing canvas ROI.")
        canvas_norm = [0.035, 0.065, 0.360, 0.550]
    else:
        canvas_norm = [
            round(r_canvas[0] / float(w), 4),
            round(r_canvas[1] / float(h), 4),
            round((r_canvas[0] + r_canvas[2]) / float(w), 4),
            round((r_canvas[1] + r_canvas[3]) / float(h), 4)
        ]
        print(f"[Selected Canvas ROI] Normalized: {canvas_norm}")

    # 2. Select 4 Health Bars
    bars_norm = []
    for slot_idx in range(1, 5):
        win_bar = f"Select Slot {slot_idx} Health Bar Core (Press ENTER/SPACE)"
        r_bar = cv2.selectROI(win_bar, frame, fromCenter=False, showCrosshair=True)
        cv2.destroyWindow(win_bar)

        if r_bar[2] < 10 or r_bar[3] < 2:
            print(f"[Warning] Invalid selection for Bar {slot_idx}. Skipping.")
            continue

        b_norm = [
            round(r_bar[0] / float(w), 4),
            round(r_bar[1] / float(h), 4),
            round((r_bar[0] + r_bar[2]) / float(w), 4),
            round((r_bar[1] + r_bar[3]) / float(h), 4)
        ]
        print(f"[Selected Bar {slot_idx}] Normalized: {b_norm}")
        bars_norm.append(b_norm)

    if len(bars_norm) == 4:
        # Save to config file
        if os.path.exists(config_path):
            with open(config_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        else:
            data = {}

        data["canvas_roi"] = canvas_norm
        data["bars_roi"] = bars_norm

        os.makedirs(os.path.dirname(config_path), exist_ok=True)
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

        print(f"\n[Success] Saved all 4 calibrated bar ROIs to {config_path}!")
    else:
        print(f"\n[Incomplete] Expected 4 bars, got {len(bars_norm)}. Config not saved.")

    if cap is not None:
        cap.release()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Calibrate Spectator Health Bar ROIs")
    parser.add_argument(
        "--source",
        type=str,
        default=os.path.join(os.path.dirname(__file__), "..", "..", "live_analytics_leaderboard", "vision-engine", "Assets", "video_4.mp4"),
        help="Video file or screenshot path"
    )
    parser.add_argument(
        "--config",
        type=str,
        default=os.path.join(os.path.dirname(__file__), "..", "config", "hp_config.json"),
        help="Path to hp_config.json"
    )
    args = parser.parse_args()
    interactive_calibrate(args.source, args.config)
