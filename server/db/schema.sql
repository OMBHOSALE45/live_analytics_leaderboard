-- Free Fire Live Kill Tracker: Event-Sourced Schema
PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

-- Matches
CREATE TABLE IF NOT EXISTS matches (
  id TEXT PRIMARY KEY,
  map TEXT NOT NULL DEFAULT 'BERMUDA',
  started_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  scoring_rules TEXT NOT NULL DEFAULT 'KILLS_ONLY',
  status TEXT NOT NULL DEFAULT 'LIVE' CHECK(status IN ('LIVE', 'COMPLETED', 'PAUSED'))
);

-- Teams (12 teams per lobby)
CREATE TABLE IF NOT EXISTS teams (
  id TEXT NOT NULL,
  match_id TEXT NOT NULL,
  name TEXT NOT NULL,
  tag TEXT NOT NULL,
  country TEXT NOT NULL,
  logo TEXT NOT NULL,
  flag TEXT NOT NULL,
  default_rank INTEGER NOT NULL,
  alive_players INTEGER NOT NULL DEFAULT 4,
  damage_dealt INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY (id, match_id),
  FOREIGN KEY (match_id) REFERENCES matches(id) ON DELETE CASCADE
);

-- Players (4 players per squad = 48 players lobby manifest)
CREATE TABLE IF NOT EXISTS players (
  id TEXT NOT NULL,
  team_id TEXT NOT NULL,
  match_id TEXT NOT NULL,
  ign TEXT NOT NULL,
  normalized_skeleton TEXT NOT NULL,
  role TEXT NOT NULL DEFAULT 'Rusher',
  is_alive INTEGER NOT NULL DEFAULT 1,
  PRIMARY KEY (id, match_id),
  FOREIGN KEY (team_id, match_id) REFERENCES teams(id, match_id) ON DELETE CASCADE,
  FOREIGN KEY (match_id) REFERENCES matches(id) ON DELETE CASCADE
);

-- Immutable Kill Ledger Events
CREATE TABLE IF NOT EXISTS kill_events (
  event_id TEXT PRIMARY KEY,
  match_id TEXT NOT NULL,
  timestamp TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  match_time_sec INTEGER NOT NULL DEFAULT 0,
  killer_player_id TEXT,
  killer_team_id TEXT,
  victim_player_id TEXT,
  victim_team_id TEXT,
  weapon TEXT DEFAULT 'UNKNOWN',
  confidence REAL NOT NULL DEFAULT 1.0,
  source TEXT NOT NULL DEFAULT 'VISION_AI' CHECK(source IN ('VISION_AI', 'MANUAL_REFEREE', 'SIMULATOR')),
  crop_path TEXT,
  status TEXT NOT NULL DEFAULT 'ACTIVE' CHECK(status IN ('ACTIVE', 'VOIDED', 'PENDING_REVIEW')),
  notes TEXT,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (match_id) REFERENCES matches(id) ON DELETE CASCADE
);

-- Indices for instant query & aggregation
CREATE INDEX IF NOT EXISTS idx_kills_match_status ON kill_events(match_id, status);
CREATE INDEX IF NOT EXISTS idx_kills_killer_team ON kill_events(killer_team_id, status);
CREATE INDEX IF NOT EXISTS idx_kills_timestamp ON kill_events(timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_players_skeleton ON players(normalized_skeleton);

