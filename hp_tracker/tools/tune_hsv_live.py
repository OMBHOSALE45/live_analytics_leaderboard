import os
import sys
import json
import argparse
import cv2
import numpy as np

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
from hp_tracker.core.dark_masker import DarkMasker
from hp_tracker.core.bar_analyzer import BarAnalyzer


def nothing(x):
    pass


def run_hsv_tuner(source: str, config_path: str):
    print("=" * 70)
    print(" HP TRACKER: LIVE HSV & THRESHOLD TUNING TOOL")
    print(f" Source: {source} | Config: {config_path}")
    print(" Press 's' to SAVE tuned parameters to hp_config.json, 'q' to QUIT.")
    print("=" * 70)

    if not os.path.exists(config_path):
        print(f"[Error] Config file not found at {config_path}")
        return

    with open(config_path, "r", encoding="utf-8") as f:
        cfg = json.load(f)

    masker = DarkMasker(cfg)
    analyzer = BarAnalyzer(cfg)

    cap = None
    is_image = False
    if source.isdigit():
        cap = cv2.VideoCapture(int(source))
    elif source.endswith(('.jpg', '.jpeg', '.png')):
        is_image = True
        frame_cache = cv2.imread(source)
    else:
        cap = cv2.VideoCapture(source)

    win_name = "HP Bar Tuning [Press 's' to Save, 'q' to Quit]"
    cv2.namedWindow(win_name, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(win_name, 900, 600)

    # Trackbars
    cv2.createTrackbar("Brightness Thresh", win_name, cfg.get("brightness_threshold", 130), 255, nothing)
    cv2.createTrackbar("Gap Thresh", win_name, cfg.get("contiguous_gap_threshold", 5), 20, nothing)
    cv2.createTrackbar("Col Fill %", win_name, int(cfg.get("col_fill_threshold", 0.35) * 100), 100, nothing)
    cv2.createTrackbar("White Val Min", win_name, cfg["hsv_thresholds"]["white_hp"]["lower"][2], 255, nothing)
    cv2.createTrackbar("White Sat Max", win_name, cfg["hsv_thresholds"]["white_hp"]["upper"][1], 255, nothing)

    while True:
        if is_image:
            frame = frame_cache.copy()
        else:
            ret, frame = cap.read()
            if not ret or frame is None:
                cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                continue

        # Read Trackbars
        b_th = cv2.getTrackbarPos("Brightness Thresh", win_name)
        gap_th = max(1, cv2.getTrackbarPos("Gap Thresh", win_name))
        col_fill = max(0.05, cv2.getTrackbarPos("Col Fill %", win_name) / 100.0)
        val_min = cv2.getTrackbarPos("White Val Min", win_name)
        sat_max = cv2.getTrackbarPos("White Sat Max", win_name)

        analyzer.brightness_threshold = b_th
        analyzer.contiguous_gap_threshold = gap_th
        analyzer.col_fill_threshold = col_fill
        analyzer.hsv_ranges["white"] = (
            np.array([0, 0, val_min], dtype=np.uint8),
            np.array([180, sat_max, 255], dtype=np.uint8)
        )

        _, bar_cores, _, _ = masker.mask_and_slice(frame)

        # Build visualization rows
        vis_rows = []
        for idx, core in enumerate(bar_cores):
            res = analyzer.analyze_bar(core)
            bin_core = res['binary_core']
            last_x = res['last_filled_x']
            raw_hp = res['raw_hp']

            # Scale up for clean inspection
            h_c, w_c = core.shape[:2]
            scale_y = 28
            scaled_core = cv2.resize(core, (w_c, scale_y), interpolation=cv2.INTER_NEAREST)
            scaled_bin = cv2.resize(bin_core, (w_c, scale_y), interpolation=cv2.INTER_NEAREST)
            scaled_bin_bgr = cv2.cvtColor(scaled_bin, cv2.COLOR_GRAY2BGR)

            # Draw detected cutoff edge
            if last_x >= 0:
                cv2.line(scaled_core, (last_x, 0), (last_x, scale_y), (0, 0, 255), 2)
                cv2.line(scaled_bin_bgr, (last_x, 0), (last_x, scale_y), (0, 255, 0), 2)

            # Info text
            text_panel = np.zeros((scale_y, 220, 3), dtype=np.uint8)
            cv2.putText(
                text_panel, f"Slot {idx+1}: {raw_hp:.1f}% ({res['state']})",
                (8, scale_y - 8),
                cv2.FONT_HERSHEY_SIMPLEX, 0.44, (0, 230, 255), 1, cv2.LINE_AA
            )

            # Combined row
            row_vis = np.hstack([scaled_core, np.zeros((scale_y, 4, 3), dtype=np.uint8), scaled_bin_bgr, text_panel])
            vis_rows.append(row_vis)

        if vis_rows:
            combined_display = np.vstack(vis_rows)
            # Add header
            header = np.zeros((32, combined_display.shape[1], 3), dtype=np.uint8)
            cv2.putText(
                header, "RAW CORE SLICE (Left) | BINARY MASK (Center) | HP ESTIMATE (Right)",
                (14, 20),
                cv2.FONT_HERSHEY_SIMPLEX, 0.42, (200, 200, 200), 1, cv2.LINE_AA
            )
            final_ui = np.vstack([header, combined_display])
            cv2.imshow(win_name, final_ui)

        key = cv2.waitKey(25) & 0xFF
        if key == ord('q'):
            break
        elif key == ord('s'):
            cfg["brightness_threshold"] = b_th
            cfg["contiguous_gap_threshold"] = gap_th
            cfg["col_fill_threshold"] = round(col_fill, 2)
            cfg["hsv_thresholds"]["white_hp"]["lower"][2] = val_min
            cfg["hsv_thresholds"]["white_hp"]["upper"][1] = sat_max
            with open(config_path, "w", encoding="utf-8") as f:
                json.dump(cfg, f, indent=2)
            print(f"[Saved] Successfully updated thresholds in {config_path}!")

    if cap is not None:
        cap.release()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Live HSV & Threshold Tuner")
    default_src = "0"
    for cand in [
        os.path.join(os.path.dirname(__file__), "..", "..", "vision-engine", "Assets", "video_4.mp4"),
        os.path.join(os.path.dirname(__file__), "..", "..", "Assets", "video_4.mp4"),
        os.path.join(os.path.dirname(__file__), "..", "..", "live_analytics_leaderboard", "vision-engine", "Assets", "video_4.mp4")
    ]:
        if os.path.exists(cand):
            default_src = os.path.abspath(cand)
            break

    parser.add_argument(
        "--source",
        type=str,
        default=default_src,
        help="Video source or screenshot"
    )
    parser.add_argument(
        "--config",
        type=str,
        default=os.path.join(os.path.dirname(__file__), "..", "config", "hp_config.json"),
        help="Path to hp_config.json"
    )
    args = parser.parse_args()
    run_hsv_tuner(args.source, args.config)
