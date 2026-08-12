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
  rounds INTEGER DEFAULT 0,
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

-- ============================================================
-- VCT 选手画像（聚合自 player_stats，多维能力模型）
-- ============================================================
CREATE TABLE IF NOT EXISTS player_profiles (
  player_name TEXT PRIMARY KEY,
  team TEXT,
  main_role TEXT,            -- 常用位置：duelist/initiator/controller/sentinel
  role_share TEXT,           -- JSON: {"duelist": 0.42, ...} 各位置回合占比
  total_rounds INTEGER DEFAULT 0,
  rounds_by_agent TEXT,      -- JSON: {"Jett": 120, "Raze": 60, ...}
  top_agents TEXT,           -- JSON: [{"agent","rounds","role"}, ...] 按回合降序
  kills INTEGER DEFAULT 0,
  deaths INTEGER DEFAULT 0,
  assists INTEGER DEFAULT 0,
  kda REAL,
  acs REAL,                  -- 近窗均值
  adr REAL,                  -- 近窗均值
  fk INTEGER DEFAULT 0,      -- 首杀累计
  fd INTEGER DEFAULT 0,      -- 首死累计
  n_maps INTEGER DEFAULT 0,
  updated_at TEXT
);

-- ============================================================
-- 选手-战队映射（当前 roster 归属，由最近比赛推断）
-- ============================================================
CREATE TABLE IF NOT EXISTS player_teams (
  player_name TEXT PRIMARY KEY,
  team TEXT NOT NULL,
  evidence TEXT,             -- 推断依据说明
  updated_at TEXT
);

-- ============================================================
-- 战队地图胜率（按 地图 × 对手 分类）
-- ============================================================
CREATE TABLE IF NOT EXISTS team_map_winrate (
  team TEXT NOT NULL,
  map_name TEXT NOT NULL,
  opponent TEXT NOT NULL,
  wins INTEGER DEFAULT 0,
  losses INTEGER DEFAULT 0,
  rounds_won INTEGER DEFAULT 0,
  rounds_lost INTEGER DEFAULT 0,
  n_maps INTEGER DEFAULT 0,
  win_rate REAL,
  updated_at TEXT,
  PRIMARY KEY(team, map_name, opponent)
);

CREATE INDEX IF NOT EXISTS idx_profiles_role ON player_profiles(main_role);
CREATE INDEX IF NOT EXISTS idx_team_winrate_team ON team_map_winrate(team);
CREATE INDEX IF NOT EXISTS idx_team_winrate_map ON team_map_winrate(map_name);
CREATE INDEX IF NOT EXISTS idx_team_winrate_opponent ON team_map_winrate(opponent);

-- ============================================================
-- Hupu post-match player ratings and match comments.
-- ============================================================
CREATE TABLE IF NOT EXISTS hupu_match_ratings (
  id TEXT PRIMARY KEY,
  match_id TEXT NOT NULL,
  player_name TEXT NOT NULL,
  team TEXT,
  rating_avg REAL,
  rating_count INTEGER,
  rating_dist TEXT,
  fetched_at TEXT
);

CREATE TABLE IF NOT EXISTS hupu_comments (
  id TEXT PRIMARY KEY,
  match_id TEXT,
  thread_id TEXT,
  page INTEGER,
  author TEXT,
  content TEXT,
  floor INTEGER,
  like_count INTEGER,
  post_time TEXT,
  fetched_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_hupu_rating_match ON hupu_match_ratings(match_id);
CREATE INDEX IF NOT EXISTS idx_hupu_rating_player ON hupu_match_ratings(player_name);
CREATE INDEX IF NOT EXISTS idx_hupu_comment_match ON hupu_comments(match_id);
