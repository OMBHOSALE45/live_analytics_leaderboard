import os
import sys
import argparse
import time
import cv2
import numpy as np

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
from hp_tracker.core.hp_pipeline import HPTrackerPipeline


def run_visualizer(source: str, config_path: str):
    print("=" * 70)
    print(" HP TRACKER: REAL-TIME DEBUG VISUALIZER")
    print(f" Source: {source} | Config: {config_path}")
    print(" Press 'q' to Quit, 'r' to Reload Config.")
    print("=" * 70)

    pipeline = HPTrackerPipeline(config_path)

    cap = None
    is_image = False
    target_fps = 30.0

    if source.isdigit():
        cap = cv2.VideoCapture(int(source))
    elif source.endswith(('.jpg', '.jpeg', '.png')):
        is_image = True
        frame_cache = cv2.imread(source)
    else:
        cap = cv2.VideoCapture(source)
        if cap.isOpened():
            v_fps = cap.get(cv2.CAP_PROP_FPS)
            if v_fps > 0:
                target_fps = v_fps

    win_name = "Free Fire Spectator HP Tracker [Dark Masking & Contiguous Scan Active]"
    cv2.namedWindow(win_name, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(win_name, 1280, 720)

    frame_interval = 1.0 / target_fps
    fps_history = []
    last_time = time.time()

    while True:
        loop_start = time.time()

        if is_image:
            frame = frame_cache.copy()
            ret = True
        else:
            ret, frame = cap.read()
            if not ret or frame is None:
                print("[Video] Looping back to start...")
                cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                continue

        # Process frame through full HP pipeline
        result = pipeline.process_frame(frame)

        # Draw rich visual debug overlay
        overlay = pipeline.draw_debug_overlay(frame, result, show_canvas_preview=True)

        # FPS calculation
        elapsed = loop_start - last_time
        last_time = loop_start
        if elapsed > 0:
            fps_history.append(1.0 / elapsed)
            if len(fps_history) > 15:
                fps_history.pop(0)
        cur_fps = sum(fps_history) / float(len(fps_history)) if fps_history else 30.0

        # Draw top banner
        cv2.putText(
            overlay, f"FPS: {cur_fps:.1f} | HP Engine Latency: {result['latency_ms']:.2f}ms",
            (18, 30),
            cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 230, 255), 1, cv2.LINE_AA
        )

        cv2.imshow(win_name, overlay)

        key = cv2.waitKey(1) & 0xFF
        if key == ord('q'):
            break
        elif key == ord('r'):
            pipeline.reload_config()
            print("[Pipeline] Reloaded config from disk!")

        # Maintain smooth playback timing
        proc_time = time.time() - loop_start
        sleep_dur = frame_interval - proc_time
        if sleep_dur > 0.001:
            time.sleep(sleep_dur)

    if cap is not None:
        cap.release()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Real-Time HP Tracker Debug Visualizer")
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
    run_visualizer(args.source, args.config)
