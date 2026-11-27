# Graph Report - live_analytics_leaderboard  (2026-11-27)

## Corpus Check
- 61 files · ~41,178 words
- Verdict: corpus is large enough that graph structure adds value.
- Unclassified: 11 file(s) not represented in the graph (top: .css 4, .bat 4, (none) 3)

## Summary
- 550 nodes · 1069 edges · 30 communities (16 shown, 14 thin omitted)
- Extraction: 92% EXTRACTED · 8% INFERRED · 0% AMBIGUOUS · INFERRED: 87 edges (avg confidence: 0.85)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `f5e07dea`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- cv2
- frontend_team_table/package.json
- Kill-Feed Detection & Consensus Pipeline
- Scoreboard Kill & Badge Detector
- Frontend Package & Build Config
- TemporalFilter
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
- scoreboard_detector.py
- Free Fire World Series Live Standings HTML Entrypoint
- HP Tracker Python Dependencies (opencv-python, numpy)
- React + Vite

## God Nodes (most connected - your core abstractions)
1. `ThreadedScoreboardDetector` - 28 edges
2. `DarkMasker` - 22 edges
3. `KillLedger` - 17 edges
4. `main()` - 15 edges
5. `run_live_scoreboard()` - 15 edges
6. `HPTrackerPipeline` - 15 edges
7. `KillCountEngine` - 14 edges
8. `BarAnalyzer` - 13 edges
9. `ChangeGatedDetector` - 13 edges
10. `LiveKillDetectionPipeline` - 13 edges

## Surprising Connections (you probably didn't know these)
- `HP Tracker Python Dependencies (opencv-python, numpy)` --conceptually_related_to--> `Vision Engine Python Dependencies`  [INFERRED]
  hp_tracker/requirements.txt → vision-engine/requirements.txt
- `run_live_scoreboard()` --calls--> `default_team_names_path()`  [EXTRACTED]
  vision-engine/scoreboard_detector.py → vision-engine/team_names.py
- `run_live_scoreboard()` --calls--> `prompt_lobby_team_names()`  [EXTRACTED]
  vision-engine/scoreboard_detector.py → vision-engine/team_names.py
- `LiveKillDetectionPipeline` --uses--> `ROICaptureManager`  [INFERRED]
  vision-engine/pipeline.py → vision-engine/capture.py
- `LiveKillDetectionPipeline` --uses--> `TemporalConsensusEngine`  [INFERRED]
  vision-engine/pipeline.py → vision-engine/consensus.py

## Import Cycles
- None detected.

## Hyperedges (group relationships)
- **Active Spectator Target Synchronization (Turn6e4U5W9 / Squad 4)** — assets_squad_8_left_squad_status_hud, assets_squad_8_right_spectator_roster_panel, assets_squad_8_gameplay_viewport_spectated_player, assets_squad_8_squad_4_roster_group [EXTRACTED 1.00]
- **Multi-Squad Live Kill Leaderboard Display** — assets_squad_8_right_spectator_roster_panel, assets_squad_8_squad_3_roster_group, assets_squad_8_squad_4_roster_group, assets_squad_8_squad_5_roster_group [EXTRACTED 1.00]
- **Synchronized Multi-View Squad Telemetry** — assets_ss_squad_hud_panel, assets_ss_live_leaderboard_drawer, assets_ss_storm_arena_viewport [EXTRACTED 1.00]
- **Six-Stage Live Esports Kill-Tracking Architecture** — plan_stage1_roster_manifest_normalization, plan_stage2_video_ingestion_roi_blueprint, plan_stage3_change_gated_row_parsing_icon_classification, plan_stage4_ocr_roster_fuzzy_matching, plan_stage5_temporal_consensus_revival_dedup, plan_stage6_event_sourced_ranking_overlay_referee [EXTRACTED 1.00]
- **Live Scoreboard AI Tracker Composite HUD Overlay** — vision_engine_assets_health_bug_live_scoreboard_ai_tracker_header, vision_engine_assets_health_bug_hp_tracker_spectator_hud, vision_engine_assets_health_bug_live_leaderboard_panel [EXTRACTED 1.00]

## Communities (30 total, 14 thin omitted)

### Community 0 - "cv2"
Cohesion: 0.11
Nodes (10): BarAnalyzer, HPTrackerPipeline, TemporalFilter, run_full_harness(), interactive_calibrate(), run_visualizer(), nothing(), run_hsv_tuner() (+2 more)

### Community 1 - "frontend_team_table/package.json"
Cohesion: 0.08
Nodes (33): dependencies, react@^19.1.1, react-dom@^19.1.1, devDependencies, eslint@^9.36.0, @eslint/js@^9.36.0, eslint-plugin-react-hooks@^5.2.0, eslint-plugin-react-refresh@^0.4.20 (+25 more)

### Community 2 - "Kill-Feed Detection & Consensus Pipeline"
Cohesion: 0.06
Nodes (7): ROICaptureManager, TemporalConsensusEngine, ChangeGatedDetector, emit_kill_to_server(), run_simulation_pipeline(), RosterMatcher, LiveKillDetectionPipeline

### Community 3 - "Scoreboard Kill & Badge Detector"
Cohesion: 0.07
Nodes (4): BadgeColorEngine, KillCountEngine, run_live_scoreboard(), ThreadedScoreboardDetector

### Community 4 - "Frontend Package & Build Config"
Cohesion: 0.07
Nodes (36): dependencies, cloudflared@^0.7.3, react@^19.1.1, react-dom@^19.1.1, devDependencies, eslint@^9.36.0, @eslint/js@^9.36.0, eslint-plugin-react-hooks@^5.2.0 (+28 more)

### Community 6 - "Stage 4: OCR & Roster-Constrained Fuzzy Matching"
Cohesion: 0.32
Nodes (7): PandaScore Esports CV Pipeline, End-to-End 6-Stage System Architecture, Stage 1: Pre-Match Roster Manifest & Normalization, Stage 2: High-Signal Video Ingestion & ROI Blueprint, Stage 3: Change-Gated Row Parsing & Icon Classification, Stage 4: OCR & Roster-Constrained Fuzzy Matching, Stage 6: Event-Sourced Ranking Engine, OBS Overlay & Referee Fail-Safe

### Community 7 - "Node Broadcast Server & Store"
Cohesion: 0.08
Nodes (20): RFC-6455, __dirname, __filename, ScoreboardStore, broadcastState(), __dirname, DIST_PATH, __filename (+12 more)

### Community 8 - "React Broadcast UI & Pages"
Cohesion: 0.10
Nodes (14): App(), LeaderboardCard(), SvgDefs(), getRankSuffix(), initialTeams, useLeaderboard(), ObsOverlay(), RefereePanel() (+6 more)

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

### Community 21 - "scoreboard_detector.py"
Cohesion: 0.08
Nodes (18): _build_worker_cmd(), _is_server_healthy(), main(), _no_proxy_opener(), _reset_barrier(), _build_worker_cmd(), _is_server_healthy(), main() (+10 more)

### Community 22 - "Free Fire World Series Live Standings HTML Entrypoint"
Cohesion: 0.67
Nodes (3): Free Fire World Series Live Standings HTML Entrypoint, Tailwind CDN Esports Broadcast Theme Config, Frontend React + Vite Template Guide

## Knowledge Gaps
- **13 isolated node(s):** `RFC-6455`, `RFC-6455`, `Squad 3 Roster Group (Red: ?MAxx 2 kills, THE GOD07 1 kill, TP TOTAL 0 kills, YASH LIVE 0 kills)`, `Squad 5 Roster Group (Purple: MOOD6H7C9L 1 kill, ZIX!EGO_¥¥ 0 kills, Slot 3 ornate name 0 kills, CORN3V6_1N 0 kills)`, `Iconify Logos Icon Set` (+8 more)
  These have ≤1 connection - possible missing edges or undocumented components. (Counts symbols only; 174 node(s) total have ≤1 connection when file, concept and rationale nodes are included.)
- **14 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `ThreadedScoreboardDetector` connect `Scoreboard Kill & Badge Detector` to `scoreboard_detector.py`?**
  _High betweenness centrality (0.033) - this node is a cross-community bridge._
- **What connects `RFC-6455`, `RFC-6455`, `Squad 3 Roster Group (Red: ?MAxx 2 kills, THE GOD07 1 kill, TP TOTAL 0 kills, YASH LIVE 0 kills)` to the rest of the system?**
  _13 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `cv2` be split into smaller, more focused modules?**
  _Cohesion score 0.10768300060496068 - nodes in this community are weakly interconnected._
- **Why does `DarkMasker` connect `DarkMasker` to `cv2`?**
  _High betweenness centrality (0.030) - this node is a cross-community bridge._
- **Should `frontend_team_table/package.json` be split into smaller, more focused modules?**
  _Cohesion score 0.0784313725490196 - nodes in this community are weakly interconnected._
- **Why does `ChangeGatedDetector` connect `Kill-Feed Detection & Consensus Pipeline` to `cv2`?**
  _High betweenness centrality (0.026) - this node is a cross-community bridge._
- **Should `Kill-Feed Detection & Consensus Pipeline` be split into smaller, more focused modules?**
  _Cohesion score 0.05656565656565657 - nodes in this community are weakly interconnected._