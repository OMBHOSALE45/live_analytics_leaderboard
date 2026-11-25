import os
import sys
import json
import argparse
import cv2
import numpy as np

# Ensure root is in path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
from hp_tracker.core.dark_masker import DarkMasker


def interactive_plot_border(source: str = "image", config_path: str = None) -> bool:
    """
    Interactive Border Plotting Tool:
    - User drags a single bounding box around the Spectator Health Bar HUD.
    - System automatically snaps onto the 4 white HP bars using HSV contiguity
      and uniform 4-bar grid fitting.
    - Saves exact locked coordinates to hp_config.json (locked=True) so they
      stay frozen forever across the entire stream.
    """
    if config_path is None:
        config_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "config", "hp_config.json"))

    print("=" * 72)
    print(" FREE FIRE SPECTATOR HP BORDER PLOTTER & PERMANENT LOCK CALIBRATOR")
    print(f" Source: {source} | Config: {config_path}")
    print("=" * 72)

    cap = None
    frame = None
    if str(source).isdigit():
        cap = cv2.VideoCapture(int(source))
        ret, frame = cap.read()
    elif str(source).endswith(('.mp4', '.avi', '.mov', '.mkv')):
        cap = cv2.VideoCapture(source)
        cap.set(cv2.CAP_PROP_POS_FRAMES, 50)
        ret, frame = cap.read()
    elif source.lower() == "image":
        candidates = [
            os.path.join(os.path.dirname(__file__), "..", "..", "vision-engine", "Assets", "video_4.mp4"),
            os.path.join(os.path.dirname(__file__), "..", "..", "Assets", "video_4.mp4"),
            os.path.join(os.path.dirname(__file__), "..", "..", "live_analytics_leaderboard", "vision-engine", "Assets", "video_4.mp4"),
            r"C:\Users\ASUS\.gemini\antigravity\brain\a120a3e1-ce4b-467c-add4-2d6988cc4804\.user_uploaded\media_1795346901821_baac37ad.jpg",
            r"C:\Users\ASUS\.gemini\antigravity\brain\a120a3e1-ce4b-467c-add4-2d6988cc4804\.user_uploaded\media_1795351169972_11ac2576.jpg"
        ]
        for c in candidates:
            if os.path.exists(c):
                if c.endswith(('.mp4', '.avi')):
                    cap = cv2.VideoCapture(c)
                    cap.set(cv2.CAP_PROP_POS_FRAMES, 50)
                    ret, frame = cap.read()
                else:
                    frame = cv2.imread(c)
                if frame is not None:
                    break
    else:
        frame = cv2.imread(source)

    if frame is None:
        print(f"[Error] Could not load sample frame from '{source}'.")
        return False

    h, w = frame.shape[:2]
    print(f"[Loaded Frame] Dimensions: {w}x{h}")

    guide_frame = frame.copy()
    cv2.rectangle(guide_frame, (0, 0), (w, 42), (20, 15, 30), -1)
    cv2.line(guide_frame, (0, 42), (w, 42), (0, 230, 255), 2)
    instructions = "PLOT SPECTATOR HP BORDER: Drag box around the 4 white HP bars -> Press ENTER/SPACE"
    cv2.putText(guide_frame, instructions, (20, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 255, 255), 1, cv2.LINE_AA)

    win_title = "Plot Spectator HP Border [Drag Box -> ENTER/SPACE]"
    cv2.namedWindow(win_title, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(win_title, min(1280, w), min(720, h))

    roi = cv2.selectROI(win_title, guide_frame, fromCenter=False, showCrosshair=True)
    cv2.destroyWindow(win_title)

    bx, by, bw, bh = roi
    if bw < 20 or bh < 20:
        print("[Warning] Border selection canceled or too small. No changes made.")
        if cap is not None:
            cap.release()
        return False

    print(f"[Border Selected] Box: x={bx}, y={by}, w={bw}, h={bh}")

    bars_roi, canvas_roi = DarkMasker.extract_bars_from_border(frame, bx, by, bw, bh, num_bars=4)

    print("\n[Derived Locked Normalized Coordinates]")
    print(f"Canvas ROI: {canvas_roi}")
    for idx, b in enumerate(bars_roi):
        print(f"  Bar {idx + 1} ROI: {b} -> px x=[{int(b[0]*w)}..{int(b[2]*w)}], y=[{int(b[1]*h)}..{int(b[3]*h)}]")

    if os.path.exists(config_path):
        with open(config_path, "r", encoding="utf-8") as f:
            cfg = json.load(f)
    else:
        cfg = {}

    cfg["canvas_roi"] = canvas_roi
    cfg["bars_roi"] = bars_roi
    cfg["locked"] = True  # Permanently lock onto these exact calibrated white-bar coordinates

    os.makedirs(os.path.dirname(config_path), exist_ok=True)
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)

    print(f"\n[Success] Saved permanently locked coordinates to {config_path}!")

    # Verify Dark Masking & Alignment on the spot
    masker = DarkMasker(cfg)
    dark_canvas, cores, coords, cbox = masker.mask_and_slice(frame)

    verify_frame = frame.copy()
    for idx, (x1, y1, x2, y2) in enumerate(coords):
        cv2.rectangle(verify_frame, (x1, y1), (x2, y2), (0, 255, 0), 1)
        cv2.putText(verify_frame, f"P{idx+1} LOCKED", (x2 + 6, y2), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 255, 0), 1)

    cv2.namedWindow("Alignment Verification [Green = Locked Core]", cv2.WINDOW_NORMAL)
    cv2.imshow("Alignment Verification [Green = Locked Core]", verify_frame[cbox[1]:cbox[3], cbox[0]:min(w, cbox[2] + 100)])

    preview_win = "Dark Mask Preview [Pure Black Canvas] - Press any key to close"
    cv2.namedWindow(preview_win, cv2.WINDOW_NORMAL)
    cv2.imshow(preview_win, dark_canvas)
    cv2.waitKey(0)
    cv2.destroyAllWindows()

    if cap is not None:
        cap.release()

    return True


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Plot Spectator HP Border and Calibrate Dark Mask")
    parser.add_argument("--source", type=str, default="image", help="Video file, camera index, or image path")
    parser.add_argument("--config", type=str, default=None, help="Path to hp_config.json")
    args = parser.parse_args()

    interactive_plot_border(source=args.source, config_path=args.config)