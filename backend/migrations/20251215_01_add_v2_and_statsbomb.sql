-- Migration: 20251215_01_add_v2_and_statsbomb
-- Target DB: SQLite (data/app.db by default)
-- Notes:
--   * This migration is intentionally idempotent: CREATE TABLE/INDEX IF NOT EXISTS.
--   * schema_migrations is for bookkeeping; DDL is safe to re-run.

PRAGMA foreign_keys = ON;

BEGIN;

-- ------------------------------------------------------------
-- Bookkeeping
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS schema_migrations (
  id TEXT PRIMARY KEY,
  applied_at TEXT NOT NULL DEFAULT (datetime('now'))
);

INSERT OR IGNORE INTO schema_migrations (id) VALUES ('20251215_01_add_v2_and_statsbomb');

-- ------------------------------------------------------------
-- V2 persistence: narration chunks + decomposition runs + projected events
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS narration_chunks (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  match_id TEXT NOT NULL,
  period TEXT NOT NULL,
  video_start_s REAL NOT NULL,
  video_end_s REAL NOT NULL,
  transcript_text TEXT NOT NULL,
  team_context TEXT,
  status TEXT NOT NULL DEFAULT 'draft',  -- draft|final|locked
  chunk_index INTEGER,                  -- optional ordering within a session
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  updated_at TEXT NOT NULL DEFAULT (datetime('now')),
  hash TEXT                             -- optional dedupe/change detection
);

CREATE INDEX IF NOT EXISTS idx_narration_chunks_match_period_time
  ON narration_chunks(match_id, period, video_start_s);

CREATE INDEX IF NOT EXISTS idx_narration_chunks_status
  ON narration_chunks(status);

CREATE TABLE IF NOT EXISTS chunk_decompositions (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  chunk_id INTEGER NOT NULL,
  schema_version TEXT NOT NULL DEFAULT 'v2',
  prompt_version TEXT,
  model TEXT,
  raw_llm_text TEXT NOT NULL,      -- exact model output
  parsed_json TEXT,                -- extracted JSON envelope (text)
  parse_ok INTEGER NOT NULL DEFAULT 0,
  error_json TEXT,
  latency_ms INTEGER,
  cost_usd REAL,
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  FOREIGN KEY (chunk_id) REFERENCES narration_chunks(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_chunk_decompositions_chunk_created
  ON chunk_decompositions(chunk_id, created_at);

-- Projected, query-friendly event rows from a decomposition (V2)
-- Keep this "hybrid": common fields as columns + extra_fields for everything else.
CREATE TABLE IF NOT EXISTS v2_events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  chunk_id INTEGER NOT NULL,
  decomposition_id INTEGER NOT NULL,

  event_type TEXT,
  team TEXT,
  player_name TEXT,
  player_jersey_number TEXT,

  approximate_time_s REAL,
  source_phrase TEXT,

  -- V2 "first touch" fields
  first_touch_quality TEXT,
  first_touch_result TEXT,

  -- V2 "on-ball action" fields
  on_ball_action_type TEXT,
  touch_count_before_action INTEGER,
  pass_intent TEXT,
  action_outcome_team TEXT,
  action_outcome_detail TEXT,

  -- V2 "post-loss reaction" fields
  post_loss_behaviour TEXT,
  post_loss_outcome TEXT,
  post_loss_effort_intensity TEXT,

  extra_fields TEXT,               -- JSON blob for everything else
  created_at TEXT NOT NULL DEFAULT (datetime('now')),

  FOREIGN KEY (chunk_id) REFERENCES narration_chunks(id) ON DELETE CASCADE,
  FOREIGN KEY (decomposition_id) REFERENCES chunk_decompositions(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_v2_events_chunk_time
  ON v2_events(chunk_id, approximate_time_s);

-- ------------------------------------------------------------
-- StatsBomb "Raw JSON + Projections"
-- ------------------------------------------------------------

-- Raw ingest storage (lossless)
CREATE TABLE IF NOT EXISTS sb_raw_files (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  source TEXT NOT NULL,             -- e.g., open-data, api, manual
  file_type TEXT NOT NULL,          -- competitions|matches|events|lineups|three_sixty|other
  external_id TEXT,                 -- e.g., match_id or comp/season key
  schema_version TEXT,
  ingested_at TEXT NOT NULL DEFAULT (datetime('now')),
  sha256 TEXT,                      -- optional content hash
  raw_json TEXT NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_sb_raw_files_type_ext_sha
  ON sb_raw_files(file_type, external_id, sha256);

CREATE INDEX IF NOT EXISTS idx_sb_raw_files_type_ext
  ON sb_raw_files(file_type, external_id);

-- Minimal match projection
CREATE TABLE IF NOT EXISTS sb_matches (
  match_id INTEGER PRIMARY KEY,     -- StatsBomb match_id is typically numeric
  competition_id INTEGER,
  season_id INTEGER,
  match_date TEXT,
  kick_off TEXT,

  home_team_id INTEGER,
  home_team_name TEXT,
  away_team_id INTEGER,
  away_team_name TEXT,

  -- store the full match object too (lossless)
  match_json TEXT,

  ingested_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_sb_matches_date
  ON sb_matches(match_date);

-- Hybrid event table: common fields as columns + event_json for full record
CREATE TABLE IF NOT EXISTS sb_events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,

  match_id INTEGER NOT NULL,
  event_id TEXT NOT NULL,           -- UUID string from StatsBomb
  index_in_match INTEGER,           -- "index" in event list if present
  period INTEGER,
  timestamp TEXT,
  minute INTEGER,
  second INTEGER,

  team_id INTEGER,
  team_name TEXT,
  player_id INTEGER,
  player_name TEXT,
  possession INTEGER,

  type_id INTEGER,
  type_name TEXT,

  play_pattern_id INTEGER,
  play_pattern_name TEXT,

  location_x REAL,
  location_y REAL,

  -- full lossless event object
  event_json TEXT NOT NULL,

  ingested_at TEXT NOT NULL DEFAULT (datetime('now')),

  FOREIGN KEY (match_id) REFERENCES sb_matches(match_id) ON DELETE CASCADE
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_sb_events_match_event
  ON sb_events(match_id, event_id);

CREATE INDEX IF NOT EXISTS idx_sb_events_match_time
  ON sb_events(match_id, period, minute, second);

CREATE INDEX IF NOT EXISTS idx_sb_events_match_index
  ON sb_events(match_id, index_in_match);

CREATE INDEX IF NOT EXISTS idx_sb_events_type
  ON sb_events(type_name);

COMMIT;
