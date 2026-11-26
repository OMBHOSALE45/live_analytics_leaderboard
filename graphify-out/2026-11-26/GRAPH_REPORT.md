# Graph Report - live_analytics_leaderboard  (2026-11-26)

## Corpus Check
- 52 files · ~34,282 words
- Verdict: corpus is large enough that graph structure adds value.
- Unclassified: 7 file(s) not represented in the graph (top: .bat 3, (none) 2, .css 2)

## Summary
- 447 nodes · 870 edges · 26 communities (16 shown, 10 thin omitted)
- Extraction: 91% EXTRACTED · 9% INFERRED · 0% AMBIGUOUS · INFERRED: 80 edges (avg confidence: 0.86)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `539d0b13`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- cv2
- launch_dual.py
- Kill-Feed Detection & Consensus Pipeline
- Scoreboard Kill & Badge Detector
- Frontend Package & Build Config
- HPTrackerPipeline
- Stage 4: OCR & Roster-Constrained Fuzzy Matching
- Node Broadcast Server & Store
- React Broadcast UI & Pages
- DarkMasker
- SQLite Kill Event Ledger
- Video Source & Spectator Simulator
- Spectator Squad UI Layout
- WebSocket & SSE Broadcast Hub
- Server Package & Dependencies
- Storm Arena Leaderboard Reference
- HP HUD Overlap Bug Screenshot
- Vision Engine HUD Bug Screenshot
- React SVG Brand Asset
- Vite SVG Brand Asset
- Free Fire World Series Live Standings HTML Entrypoint
- HP Tracker Python Dependencies (opencv-python, numpy)

## God Nodes (most connected - your core abstractions)
1. `DarkMasker` - 23 edges
2. `ThreadedScoreboardDetector` - 19 edges
3. `KillLedger` - 17 edges
4. `HPTrackerPipeline` - 17 edges
5. `BarAnalyzer` - 14 edges
6. `KillCountEngine` - 14 edges
7. `react` - 14 edges
8. `ChangeGatedDetector` - 13 edges
9. `LiveKillDetectionPipeline` - 13 edges
10. `TemporalConsensusEngine` - 12 edges

## Surprising Connections (you probably didn't know these)
- `HP Tracker Python Dependencies (opencv-python, numpy)` --conceptually_related_to--> `Vision Engine Python Dependencies`  [INFERRED]
  hp_tracker/requirements.txt → vision-engine/requirements.txt
- `HPTrackerPipeline` --uses--> `BarAnalyzer`  [INFERRED]
  hp_tracker/core/hp_pipeline.py → hp_tracker/core/bar_analyzer.py
- `HPTrackerPipeline` --uses--> `DarkMasker`  [INFERRED]
  hp_tracker/core/hp_pipeline.py → hp_tracker/core/dark_masker.py
- `LiveKillDetectionPipeline` --uses--> `ROICaptureManager`  [INFERRED]
  vision-engine/pipeline.py → vision-engine/capture.py
- `HPTrackerPipeline` --uses--> `TemporalFilter`  [INFERRED]
  hp_tracker/core/hp_pipeline.py → hp_tracker/core/temporal_filter.py

## Import Cycles
- None detected.

## Hyperedges (group relationships)
- **Active Spectator Target Synchronization (Turn6e4U5W9 / Squad 4)** — assets_squad_8_left_squad_status_hud, assets_squad_8_right_spectator_roster_panel, assets_squad_8_gameplay_viewport_spectated_player, assets_squad_8_squad_4_roster_group [EXTRACTED 1.00]
- **Multi-Squad Live Kill Leaderboard Display** — assets_squad_8_right_spectator_roster_panel, assets_squad_8_squad_3_roster_group, assets_squad_8_squad_4_roster_group, assets_squad_8_squad_5_roster_group [EXTRACTED 1.00]
- **Synchronized Multi-View Squad Telemetry** — assets_ss_squad_hud_panel, assets_ss_live_leaderboard_drawer, assets_ss_storm_arena_viewport [EXTRACTED 1.00]
- **Six-Stage Live Esports Kill-Tracking Architecture** — plan_stage1_roster_manifest_normalization, plan_stage2_video_ingestion_roi_blueprint, plan_stage3_change_gated_row_parsing_icon_classification, plan_stage4_ocr_roster_fuzzy_matching, plan_stage5_temporal_consensus_revival_dedup, plan_stage6_event_sourced_ranking_overlay_referee [EXTRACTED 1.00]
- **Live Scoreboard AI Tracker Composite HUD Overlay** — vision_engine_assets_health_bug_live_scoreboard_ai_tracker_header, vision_engine_assets_health_bug_hp_tracker_spectator_hud, vision_engine_assets_health_bug_live_leaderboard_panel [EXTRACTED 1.00]

## Communities (26 total, 10 thin omitted)

### Community 0 - "cv2"
Cohesion: 0.13
Nodes (10): BarAnalyzer, run_full_harness(), interactive_calibrate(), interactive_plot_border(), nothing(), run_hsv_tuner(), ROICaptureManager, emit_kill_to_server() (+2 more)

### Community 1 - "launch_dual.py"
Cohesion: 0.29
Nodes (5): _build_worker_cmd(), _is_server_healthy(), main(), _no_proxy_opener(), _reset_barrier()

### Community 2 - "Kill-Feed Detection & Consensus Pipeline"
Cohesion: 0.06
Nodes (4): TemporalConsensusEngine, ChangeGatedDetector, RosterMatcher, LiveKillDetectionPipeline

### Community 3 - "Scoreboard Kill & Badge Detector"
Cohesion: 0.06
Nodes (6): BadgeColorEngine, KillCountEngine, PlayerKillState, run_live_scoreboard(), ThreadedScoreboardDetector, wait_for_stream_barrier()

### Community 4 - "Frontend Package & Build Config"
Cohesion: 0.08
Nodes (35): dependencies, cloudflared@^0.7.3, react@^19.1.1, react-dom@^19.1.1, devDependencies, eslint@^9.36.0, @eslint/js@^9.36.0, eslint-plugin-react-hooks@^5.2.0 (+27 more)

### Community 5 - "HPTrackerPipeline"
Cohesion: 0.07
Nodes (4): HPTrackerPipeline, SlotFilter, TemporalFilter, run_visualizer()

### Community 6 - "Stage 4: OCR & Roster-Constrained Fuzzy Matching"
Cohesion: 0.32
Nodes (7): PandaScore Esports CV Pipeline, End-to-End 6-Stage System Architecture, Stage 1: Pre-Match Roster Manifest & Normalization, Stage 2: High-Signal Video Ingestion & ROI Blueprint, Stage 3: Change-Gated Row Parsing & Icon Classification, Stage 4: OCR & Roster-Constrained Fuzzy Matching, Stage 6: Event-Sourced Ranking Engine, OBS Overlay & Referee Fail-Safe

### Community 7 - "Node Broadcast Server & Store"
Cohesion: 0.09
Nodes (19): __dirname, __filename, ScoreboardStore, broadcastState(), __dirname, DIST_PATH, __filename, handleClientFrame() (+11 more)

### Community 8 - "React Broadcast UI & Pages"
Cohesion: 0.13
Nodes (9): App(), LeaderboardCard(), SvgDefs(), getRankSuffix(), initialTeams, useLeaderboard(), ObsOverlay(), RefereePanel() (+1 more)

### Community 11 - "Video Source & Spectator Simulator"
Cohesion: 0.16
Nodes (4): run_live_detector(), generate_benchmark_video(), SimulatedSpectatorFeed, VideoSourceManager

### Community 12 - "Spectator Squad UI Layout"
Cohesion: 0.27
Nodes (9): 3D Gameplay Viewport and Spectated Player (Turn6e4U5W9 Driving ATV, Pink Slot 4), Left Squad Status HUD (Slots 1-4: nBsndb, karanrajj124, SOHILbhai, Turn6e4U5W9), Right Spectator Roster Panel (ALL and NEARBY Tabs with Multi-Squad Kill Leaderboard), Safe Zone Shrinking Banner and Revival Point Heart Indicators (7 m), Squad 8 Spectator Mode UI Screenshot, Squad 3 Roster Group (Red: ?MAxx 2 kills, THE GOD07 1 kill, TP TOTAL 0 kills, YASH LIVE 0 kills), Squad 4 Active Spectated Roster Group (Pink: NBSNDB 2 kills, KARANRAJJ124 0 kills, SOHILBHAI 0 kills, TURN6E4U5W9 0 kills), Squad 5 Roster Group (Purple: MOOD6H7C9L 1 kill, ZIX!EGO_¥¥ 0 kills, Slot 3 ornate name 0 kills, CORN3V6_1N 0 kills) (+1 more)

### Community 14 - "Server Package & Dependencies"
Cohesion: 0.25
Nodes (8): ws, dependencies, ws@^8.18.0, name, scripts, start, type, version

### Community 15 - "Storm Arena Leaderboard Reference"
Cohesion: 0.39
Nodes (7): ALL / NEARBY Tabbed Leaderboard Filter, Free Fire Storm Arena Live Leaderboard UI Screenshot, Diamond Skull Kill Score Metric Column, Right-Side Live Leaderboard Drawer, Squad-Grouped Color-Coded Leaderboard Rows, Top-Left Persistent Squad Status HUD, Storm Arena 3D Lobby Viewport

### Community 16 - "HP HUD Overlap Bug Screenshot"
Cohesion: 0.60
Nodes (6): Health Bug UI Screenshot (health_bug.png), HP TRACKER: SPECTATOR HUD Bounding Box Overlay, HP Readout Horizontal Overflow Overlapping Live Leaderboard Bug, LIVE LEADERBOARD (KILLS) Overlay Panel (Team Red 4, Team Blue 1, Team Pink 1), LIVE SCOREBOARD AI TRACKER Top Status Bar (FPS 23.7, TEAMS 3, ALIVE 12, KILLS 6), P1: 100.0% [ALIVE] Green HP Bar and Text Readout

### Community 17 - "Vision Engine HUD Bug Screenshot"
Cohesion: 0.60
Nodes (6): HP Tracker Spectator HUD ROI (Player 1 Green Health Bar), HUD Text Overlap Bug (P1 Status Label Collides With #2 Team Blue), Live Leaderboard (Kills) Panel (Red, Blue, Pink Teams), Live Scoreboard AI Tracker Status Bar (FPS, Teams, Alive, Kills), P1 Health Status Label (P1: 100.0% [ALIVE]), Health Bug HUD Screenshot (Spectator HP vs Leaderboard Overlap)

### Community 22 - "Free Fire World Series Live Standings HTML Entrypoint"
Cohesion: 0.67
Nodes (3): Free Fire World Series Live Standings HTML Entrypoint, Tailwind CDN Esports Broadcast Theme Config, Frontend React + Vite Template Guide

## Knowledge Gaps
- **13 isolated node(s):** `RFC-6455`, `RFC-6455`, `Squad 3 Roster Group (Red: ?MAxx 2 kills, THE GOD07 1 kill, TP TOTAL 0 kills, YASH LIVE 0 kills)`, `Squad 5 Roster Group (Purple: MOOD6H7C9L 1 kill, ZIX!EGO_¥¥ 0 kills, Slot 3 ornate name 0 kills, CORN3V6_1N 0 kills)`, `Iconify Logos Icon Set` (+8 more)
  These have ≤1 connection - possible missing edges or undocumented components. (Counts symbols only; 147 node(s) total have ≤1 connection when file, concept and rationale nodes are included.)
- **10 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `DarkMasker` connect `DarkMasker` to `cv2`, `HPTrackerPipeline`?**
  _High betweenness centrality (0.047) - this node is a cross-community bridge._
- **What connects `RFC-6455`, `RFC-6455`, `Squad 3 Roster Group (Red: ?MAxx 2 kills, THE GOD07 1 kill, TP TOTAL 0 kills, YASH LIVE 0 kills)` to the rest of the system?**
  _13 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `cv2` be split into smaller, more focused modules?**
  _Cohesion score 0.12784313725490196 - nodes in this community are weakly interconnected._
- **Why does `HPTrackerPipeline` connect `HPTrackerPipeline` to `cv2`, `DarkMasker`, `Scoreboard Kill & Badge Detector`?**
  _High betweenness centrality (0.038) - this node is a cross-community bridge._
- **Should `Kill-Feed Detection & Consensus Pipeline` be split into smaller, more focused modules?**
  _Cohesion score 0.0647342995169082 - nodes in this community are weakly interconnected._
- **Why does `ChangeGatedDetector` connect `Kill-Feed Detection & Consensus Pipeline` to `cv2`?**
  _High betweenness centrality (0.033) - this node is a cross-community bridge._
- **Should `Scoreboard Kill & Badge Detector` be split into smaller, more focused modules?**
  _Cohesion score 0.06349206349206349 - nodes in this community are weakly interconnected._