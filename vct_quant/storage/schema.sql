-- vct_quant 数据库表结构

CREATE TABLE IF NOT EXISTS matches (
  id TEXT PRIMARY KEY,
  event TEXT,
  date TEXT,
  team_a TEXT,
  team_b TEXT,
  score_a INTEGER,
  score_b INTEGER,
  url TEXT,
  fetched_at TEXT
);

CREATE TABLE IF NOT EXISTS maps (
  id TEXT PRIMARY KEY,
  match_id TEXT,
  map_name TEXT,
  team_a_score INTEGER,
  team_b_score INTEGER,
  winner TEXT,
  duration_sec INTEGER,
  site TEXT,
  FOREIGN KEY(match_id) REFERENCES matches(id)
);

CREATE TABLE IF NOT EXISTS player_stats (
  id TEXT PRIMARY KEY,
  map_id TEXT,
  match_id TEXT,
  player_name TEXT,
  team TEXT,
  agent TEXT,
  acs REAL,
  kills INTEGER,
  deaths INTEGER,
  assists INTEGER,
  kast REAL,
  fk INTEGER,
  fd INTEGER,
  adr REAL,
  hs_pct REAL,
  FOREIGN KEY(map_id) REFERENCES maps(id)
);

CREATE TABLE IF NOT EXISTS posts (
  id TEXT PRIMARY KEY,
  source TEXT,
  thread_id TEXT,
  author TEXT,
  content TEXT,
  post_time TEXT,
  reply_count INTEGER,
  fetched_at TEXT
);

CREATE TABLE IF NOT EXISTS sentiments (
  id TEXT PRIMARY KEY,
  post_id TEXT,
  player_name TEXT,
  team TEXT,
  sentiment_score REAL,
  bullish_score REAL,
  confidence REAL,
  method TEXT,
  created_at TEXT,
  FOREIGN KEY(post_id) REFERENCES posts(id)
);

CREATE TABLE IF NOT EXISTS player_ratings (
  player_name TEXT PRIMARY KEY,
  rating REAL,
  rd REAL,
  vol REAL,
  updated_at TEXT
);

CREATE TABLE IF NOT EXISTS value_signals (
  date TEXT,
  player_name TEXT,
  v_star REAL,
  p_market REAL,
  delta REAL,
  signal TEXT,
  position REAL,
  rationale TEXT,
  created_at TEXT,
  PRIMARY KEY(date, player_name)
);

CREATE INDEX IF NOT EXISTS idx_player_stats_player ON player_stats(player_name);
CREATE INDEX IF NOT EXISTS idx_player_stats_map ON player_stats(map_id);
CREATE INDEX IF NOT EXISTS idx_player_stats_match ON player_stats(match_id);
CREATE INDEX IF NOT EXISTS idx_sentiments_player ON sentiments(player_name);
CREATE INDEX IF NOT EXISTS idx_posts_source_time ON posts(source, post_time);
