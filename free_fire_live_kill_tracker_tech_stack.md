# Free Fire Live Kill-Tracking & Leaderboard System — Tech Stack

A production-ready, low-latency technology blueprint for extracting live eliminations from Free Fire spectator streams, verifying them against a pre-match roster, and driving an animated real-time OBS leaderboard with zero double-counting.

---

## 1. Architectural Design Principles

* **CPU-First Inference:** Uses ONNX Runtime for both icon detection and OCR so the entire pipeline can run smoothly on a single broadcast machine (even an 8 GB RAM laptop without a dedicated NVIDIA GPU).
* **Zero State Drift:** All kills are stored as immutable event records; team totals and rankings are dynamically aggregated rather than mutated in place.
* **Closed-Set Verification:** Matches noisy OCR strings against a known 48-player lobby manifest instead of trusting raw text output.
* **Human-in-the-Loop Safety Net:** Pairs automated detection with a 1-click Referee Dashboard during the natural 10–30 second broadcast delay.

---

## 2. Core Technology Matrix

| Layer | Primary Stack | Optional Upgrade (Scale) | Role in Pipeline |
| :--- | :--- | :--- | :--- |
| **Stream Capture** | OBS Studio + Virtual Cam / Local RTMP (`MediaMTX`) | NDI (`ndi-python`) | Uncompressed 1080p frame ingestion from spectator feed |
| **Frame Processing** | Python 3.11 + OpenCV (`opencv-python-headless`) + NumPy | GStreamer / FFmpeg C++ | ROI cropping, 4–5 FPS sampling, CLAHE contrast pre-processing |
| **Change Gating** | `scikit-image` (SSIM) or OpenCV `absdiff` | — | Skips static frames to cut CPU load by 70–85% |
| **Icon & Split Detection** | **YOLOv11-nano** exported to **ONNX Runtime** | TensorRT (if GPU available) | Filters out Knockdowns; locates weapon/skull icon to split Killer vs. Victim |
| **Text Recognition (OCR)** | **RapidOCR** (`rapidocr-onnxruntime`) | PaddleOCR (PP-OCRv5) | Fast, high-accuracy text extraction on stylized gaming fonts |
| **Roster Fuzzy Matching** | **RapidFuzz** + Python `unicodedata` | — | Strips Unicode clutter and matches names against the 48-player manifest in under 1 ms |
| **Backend & Event Ledger** | **Node.js + Express + Socket.IO** | FastAPI (if single-language Python) | Immutable kill ledger, tie-breaker ranking engine, WebSocket broadcast |
| **Database** | **SQLite** (`better-sqlite3` in WAL mode) | PostgreSQL + Redis | Local, zero-config transactional event store with instant undo/audit |
| **Live OBS Overlay** | **React + Vite + Tailwind CSS + Framer Motion** | — | Transparent 1080p Browser Source with animated rank-swap transitions |
| **Referee Dashboard** | **React + Socket.IO Client** | — | Live queue for low-confidence crops (under 85%) with Confirm / Reassign / Undo |
| **Model Training** | **Google Colab** (T4 GPU) + **Roboflow** | Local PyTorch CUDA | Dataset labeling and training the custom YOLOv11n icon classifier |
| **Process Management** | **PM2** or **Docker Compose** | Kubernetes (cloud) | Keeps Python CV worker, Node API, and UI running cleanly with auto-restart |

---

## 3. Layer-by-Layer Breakdown

### A. Video Ingestion & Pre-Processing (Python)
* **Source Capture:** Capture directly from the observer PC via **OBS Virtual Camera** or a local **MediaMTX** RTMP server rather than scraping YouTube/Twitch streams. Avoiding re-compression preserves sharp HUD text edges.
* **OpenCV + NumPy:** Samples frames every 200–250 ms (4–5 FPS) and slices them into three resolution-normalized Regions of Interest (ROIs):
  1. `ROI_KILLFEED`: Active kill-feed rows.
  2. `ROI_ALIVE`: Global alive player counter (sanity check).
  3. `ROI_GUARD`: Detects replays, lobby screens, or transition stingers to auto-pause parsing.
* **Image Conditioning:** Upscaling (`2x–3x` bicubic), grayscale conversion, CLAHE contrast enhancement, and adaptive thresholding to isolate bright text from explosions or sky backgrounds.

### B. Computer Vision & Icon Classification (ONNX Runtime)
* **Why ONNX Runtime:** Avoids installing heavy multi-gigabyte PyTorch runtimes on the broadcast PC while delivering sub-15 ms CPU inference per kill-feed strip.
* **Custom YOLOv11-nano Model:** Trained on 300–500 labeled Free Fire kill-feed banners to classify center icons into:
  * `ELIMINATION` (skull, headshot, standard weapons, grenade, vehicle, zone)
  * `KNOCKDOWN` (discarded immediately before OCR)
* **Dynamic Cropping:** Uses the detected icon bounding box (`x_min`, `x_max`) to cleanly slice `[Left = Killer]` and `[Right = Victim]` so names never bleed together.

### C. OCR, Normalization & Deduplication Engine (Python)
* **RapidOCR (`rapidocr-onnxruntime`):** Lightweight ONNX port of PaddleOCR models; handles sharp outlines and gaming fonts significantly better than Tesseract on CPU.
* **ASCII Skeleton Normalization:** Strips decorative Free Fire Unicode characters (`꧁`, `༺`, `ツ`, `么`, invisible spaces) into a clean alphanumeric skeleton before matching.
* **RapidFuzz:** Scores stripped OCR text against all 48 pre-loaded player skeletons using `WRatio` and `partial_ratio`:
  * **85%+ confidence:** Auto-pass to consensus buffer.
  * **65%–84% confidence:** Hold for multi-frame voting; flag if unresolved.
  * **Under 65% confidence:** Send cropped banner image directly to the Referee Dashboard.
* **Temporal Consensus & Revival Cooldown:**
  * Requires a matching `(killer_id, victim_id)` pair in **at least 2 of 3 consecutive sampled frames** before emitting a kill event.
  * Applies a **15-second sliding hash cooldown** per `(killer_id, victim_id)` pair—long enough to prevent double-counting a banner on screen (4–5 seconds), short enough to accurately count Free Fire revivals.

### D. Event-Sourced Ranking Backend (Node.js)
* **Express + Socket.IO:** Receives verified JSON events from the Python CV worker over a local WebSocket/HTTP bridge and broadcasts state diffs instantaneously to both the OBS Overlay and Referee Dashboard.
* **SQLite (`better-sqlite3`):** Runs in Write-Ahead Logging (WAL) mode for fast concurrent reads/writes with zero external database server overhead.
* **Event-Sourced Schema:**
  * `matches` (match ID, map, start time, scoring rules)
  * `teams` & `players` (pre-match lobby manifest + normalized skeletons)
  * `kill_events` (immutable log: `event_id`, `timestamp`, `killer_id`, `killer_team_id`, `victim_id`, `victim_team_id`, `confidence`, `crop_path`, `status` [`ACTIVE` | `VOIDED` | `PENDING_REVIEW`])
* **Deterministic Tie-Breaking:**
  1. `total_kills` (descending) — or total tournament points (`kills + placement_points`)
  2. `alive_players` (descending)
  3. `first_to_reach_timestamp` (ascending)

### E. Broadcast Overlay & Referee UI (React)
* **OBS Browser Source (`/overlay`):** Built with **React, Vite, Tailwind CSS, and Framer Motion** (`layout` animations). Loaded directly in OBS at `1920x1080` with a transparent background (`background: transparent`) for smooth animated team rank swaps, kill-pop badges, and eliminated-squad dimming.
* **Referee Console (`/referee`):** Accessible from a second monitor, tablet, or phone on the local network. Displays the live kill ticker, global `Alive` mismatch alerts, and a verification queue with cropped kill-feed thumbnails and instant **Confirm / Reassign / Undo** buttons.

---

## 4. Recommended Monorepo Structure

```text
ff-live-leaderboard/
├── config/
│   ├── roi_presets.json          # Normalized 1080p/720p ROI bounding boxes
│   └── sample_roster.json        # 12-team / 48-player pre-match manifest
├── training/
│   ├── train_yolo_icons.ipynb    # Google Colab notebook (PyTorch -> ONNX export)
│   └── dataset.yaml              # Class labels (kill_icon, headshot_icon, knock_icon)
├── vision-engine/                # Python CV & OCR Worker
│   ├── models/
│   │   └── ff_icons_v11n.onnx    # Exported lightweight icon detector
│   ├── capture.py                # OBS Virtual Cam / RTMP frame reader
│   ├── detector.py               # SSIM gate + ONNX icon split
│   ├── matcher.py                # RapidOCR + ASCII skeleton + RapidFuzz
│   ├── consensus.py              # 2-of-3 frame voting + 15s revival cooldown
│   ├── main.py                   # Pipeline loop & Socket.IO emitter
│   └── requirements.txt
├── server/                       # Node.js Event-Sourced Backend
│   ├── db/
│   │   ├── schema.sql            # SQLite immutable event ledger tables
│   │   └── ledger.js             # Aggregation & tie-breaker ranking engine
│   ├── routes/                   # Roster upload & referee correction endpoints
│   ├── sockets.js                # Real-time Socket.IO state fan-out
│   ├── server.js
│   └── package.json
├── frontend/                     # React + Vite (Overlay + Referee UI)
│   ├── src/
│   │   ├── pages/
│   │   │   ├── ObsOverlay.jsx    # Transparent animated leaderboard (Framer Motion)
│   │   │   └── RefereePanel.jsx  # Verification queue & manual override console
│   │   ├── hooks/useLeaderboard.js
│   │   └── App.jsx
│   └── package.json
└── docker-compose.yml            # Optional containerized local orchestration
```

---

## 5. Exact Dependency Blueprint

### Python CV Worker (`vision-engine/requirements.txt`)
```text
opencv-python-headless==4.10.0.84
numpy==1.26.4
onnxruntime==1.19.2
rapidocr-onnxruntime==1.3.24
rapidfuzz==3.10.0
scikit-image==0.24.0
python-socketio[client]==5.11.4
pydantic==2.9.2
```

### Node.js Backend (`server/package.json` core dependencies)
```json
{
  "dependencies": {
    "better-sqlite3": "^11.5.0",
    "cors": "^2.8.5",
    "express": "^4.21.1",
    "socket.io": "^4.8.1",
    "uuid": "^11.0.2"
  }
}
```

### React Frontend (`frontend/package.json` core dependencies)
```json
{
  "dependencies": {
    "framer-motion": "^11.11.17",
    "lucide-react": "^0.454.0",
    "react": "^18.3.1",
    "react-dom": "^18.3.1",
    "socket.io-client": "^4.8.1"
  },
  "devDependencies": {
    "autoprefixer": "^10.4.20",
    "postcss": "^8.4.47",
    "tailwindcss": "^3.4.14",
    "vite": "^5.4.10"
  }
}
```

---

## 6. End-to-End Latency Budget (Per Active Kill Banner)

| Stage | Target Latency | Notes |
| :--- | :--- | :--- |
| Frame Grab + ROI Crop + SSIM Gate | 5–10 ms | Static frames exit here at under 3 ms |
| YOLOv11-nano ONNX (Icon Split) | 12–18 ms | Single CPU thread; drops knockdowns immediately |
| RapidOCR (2 Small Name Crops) | 25–45 ms | Only runs when new kill icon is confirmed |
| RapidFuzz Roster Match (48 IGNs) | under 1 ms | C++ compiled Levenshtein/ratio scoring |
| Temporal Consensus Wait (2 of 3 frames) | 200–400 ms | Intentional 1–2 sample hold to guarantee accuracy |
| SQLite Write + Socket.IO + OBS Render | 10–20 ms | Instant animated update on Browser Source |
| **Total Time (Banner → Leaderboard)** | **~260–495 ms** | Under half a second end-to-end |

---

## 7. Hardware & Resource Sizing

| Tier | Machine Profile | Expected Performance |
| :--- | :--- | :--- |
| **Minimum (Single-PC Local)** | Dual/Quad-Core CPU (e.g., Intel Core i3/i5), 8 GB RAM, SSD | Runs smoothly at 4 FPS with SSIM gating + ONNX CPU inference (~15–25% CPU overhead alongside OBS). |
| **Recommended (Dedicated Broadcast)** | 6+ Core CPU (i5/Ryzen 5+), 16 GB RAM, optional entry GPU | Runs effortlessly at 5–10 FPS with zero frame drops even during chaotic 12-team final-zone fights. |
| **Cloud / Multi-Stream Scale** | Linux VPS / Container + PostgreSQL + Redis | Supports simultaneous tournament lobbies and remote web-based referees. |

---

## 8. Training & Validation Tooling

* **Frame Extraction:** `ffmpeg` CLI (`ffmpeg -i vod.mp4 -vf fps=2 frames/frame_%04d.png`) to pull kill-feed samples from recorded 1080p Free Fire spectator VODs.
* **Annotation:** **Roboflow** (free tier) or **LabelImg** to draw tight bounding boxes around Free Fire weapon, headshot, skull, and knockdown icons.
* **Model Training & Export:** **Google Colab (Free T4 GPU)** using Ultralytics (`yolo train` → `yolo export format=onnx imgsz=320 simplify=True`).
* **Offline Accuracy Benchmark:** Python evaluation script comparing pipeline output against a manually logged ground-truth CSV (`timestamp, killer, victim`) to verify **Precision, Recall, and F1 over 98.5%** before live deployment.