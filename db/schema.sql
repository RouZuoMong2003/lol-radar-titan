-- LoL Radar Engine · 唯一 DDL 真源
-- 命名规则：DB 列 = CSV 列小写化（空格→下划线）
-- 详见 docs/SPEC.md §1

PRAGMA foreign_keys = ON;
PRAGMA journal_mode = WAL;

------------------------------------------------------------
-- 字典表
------------------------------------------------------------
CREATE TABLE IF NOT EXISTS leagues (
  id          TEXT PRIMARY KEY,        -- 'LPL'
  name        TEXT,
  region      TEXT,                    -- CN/KR/EU/NA/...
  tier        INTEGER DEFAULT 2        -- 1=主赛区
);

CREATE TABLE IF NOT EXISTS seasons (
  id          TEXT PRIMARY KEY,        -- 'LPL-2026-Spring'
  league_id   TEXT NOT NULL,
  year        INTEGER NOT NULL,
  split       TEXT NOT NULL,
  FOREIGN KEY (league_id) REFERENCES leagues(id)
);

CREATE TABLE IF NOT EXISTS teams (
  id          TEXT PRIMARY KEY,        -- oe:team:xxx
  name        TEXT,
  short_name  TEXT,
  current_league TEXT
);

CREATE TABLE IF NOT EXISTS players (
  id              TEXT PRIMARY KEY,    -- oe:player:xxx
  current_handle  TEXT,
  current_team    TEXT,
  current_position TEXT
);

------------------------------------------------------------
-- match_rows: CSV 落库（核心宽表，仅保留 SPEC §1.2 涉及的字段 + 必要标识）
------------------------------------------------------------
CREATE TABLE IF NOT EXISTS match_rows (
  game_id        TEXT NOT NULL,
  side           TEXT NOT NULL,        -- Blue/Red
  position       TEXT NOT NULL,        -- top/jng/mid/bot/sup/team
  -- 关联标识
  league_id      TEXT,
  season_id      TEXT,
  date           TEXT,
  patch          TEXT,
  playoffs       INTEGER,
  datacompleteness TEXT,
  player_id      TEXT,                 -- team 行 NULL
  player_name    TEXT,
  team_id        TEXT,
  team_name      TEXT,
  champion       TEXT,
  game_length    INTEGER,
  result         INTEGER,
  -- 一级数据
  kills          INTEGER,
  deaths         INTEGER,
  assists        INTEGER,
  teamkills      INTEGER,
  doublekills    INTEGER,
  triplekills    INTEGER,
  quadrakills    INTEGER,
  pentakills     INTEGER,
  firstblood     INTEGER,
  firstdragon    INTEGER,
  firstherald    INTEGER,
  firstbaron     INTEGER,
  firsttower     INTEGER,
  dragons        INTEGER,
  barons         INTEGER,
  -- 二级数据（速率/比率）
  dpm            REAL,
  damageshare    REAL,
  damagemitigatedperminute REAL,
  vspm           REAL,
  wpm            REAL,
  wcpm           REAL,
  cspm           REAL,
  ckpm           REAL,
  team_kpm       REAL,
  earnedgoldshare REAL,
  gspd           REAL,                 -- team 行专属（EGR 类）
  gpr            REAL,                 -- team 行专属
  -- 时间分段差值
  goldat10       INTEGER,
  goldat15       INTEGER,
  opp_goldat10   INTEGER,
  opp_goldat15   INTEGER,
  golddiffat10   INTEGER,
  golddiffat15   INTEGER,
  csdiffat10     INTEGER,
  csdiffat15     INTEGER,
  xpdiffat15     INTEGER,
  PRIMARY KEY (game_id, side, position)
);
CREATE INDEX IF NOT EXISTS idx_mr_player ON match_rows(player_id, season_id);
CREATE INDEX IF NOT EXISTS idx_mr_team   ON match_rows(team_id, season_id);
CREATE INDEX IF NOT EXISTS idx_mr_season ON match_rows(season_id, position);

------------------------------------------------------------
-- player_season: 雷达图选手快照
------------------------------------------------------------
CREATE TABLE IF NOT EXISTS player_season (
  player_id      TEXT NOT NULL,
  season_id      TEXT NOT NULL,
  team_id        TEXT,
  position       TEXT,
  -- 6 维度（标准化后 0-100）
  d_teamfight    INTEGER,
  d_laning       INTEGER,
  d_macro        INTEGER,
  d_mechanics    INTEGER,
  d_consistency  INTEGER,
  d_meta_adapt   INTEGER,
  -- 聚合原值（详情卡 raw 区）
  games          INTEGER,
  wins           INTEGER,
  losses         INTEGER,
  win_rate       REAL,
  kda            REAL,
  avg_kills      REAL,
  avg_deaths     REAL,
  avg_assists    REAL,
  avg_dpm        REAL,
  avg_damageshare REAL,
  avg_vspm       REAL,
  avg_wcpm       REAL,
  avg_cspm       REAL,
  avg_egshare    REAL,
  avg_gd15       REAL,
  avg_csd15      REAL,
  avg_xpd15      REAL,
  champion_pool  INTEGER,
  -- 排名 + 综合
  r_position     INTEGER,
  total_in_pos   INTEGER,
  text_score     INTEGER,
  season_rating  INTEGER,
  updated_at     TEXT DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (player_id, season_id)
);
CREATE INDEX IF NOT EXISTS idx_ps_season_pos ON player_season(season_id, position);

------------------------------------------------------------
-- team_season: 雷达图队伍快照
------------------------------------------------------------
CREATE TABLE IF NOT EXISTS team_season (
  team_id        TEXT NOT NULL,
  season_id      TEXT NOT NULL,
  league_id      TEXT,
  -- 6 维度
  d_teamfight    INTEGER,
  d_laning       INTEGER,
  d_macro        INTEGER,
  d_mechanics    INTEGER,
  d_consistency  INTEGER,
  d_meta_adapt   INTEGER,
  -- 队伍级聚合（来自 position='team' 行）
  games          INTEGER,
  wins           INTEGER,
  losses         INTEGER,
  win_rate       REAL,
  avg_game_length REAL,
  avg_gspd       REAL,                 -- ★ EGR 类直读
  avg_gpr        REAL,                 -- ★ 直读
  avg_ckpm       REAL,
  avg_team_kpm   REAL,
  avg_dragons    REAL,
  avg_barons     REAL,
  first_blood_rate REAL,
  first_tower_rate REAL,
  -- 排名 + 综合
  r_league       INTEGER,
  total_in_league INTEGER,
  text_score     INTEGER,
  season_rating  INTEGER,
  updated_at     TEXT DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (team_id, season_id)
);
CREATE INDEX IF NOT EXISTS idx_ts_season ON team_season(season_id);

------------------------------------------------------------
-- league_average: 橙色基线
------------------------------------------------------------
CREATE TABLE IF NOT EXISTS league_average (
  league_id     TEXT NOT NULL,
  season_id     TEXT NOT NULL,
  position      TEXT NOT NULL,         -- top/jng/mid/bot/sup/team
  d_teamfight   REAL,
  d_laning      REAL,
  d_macro       REAL,
  d_mechanics   REAL,
  d_consistency REAL,
  d_meta_adapt  REAL,
  PRIMARY KEY (league_id, season_id, position)
);

------------------------------------------------------------
-- champion_pool: 选手英雄池
------------------------------------------------------------
CREATE TABLE IF NOT EXISTS champion_pool (
  player_id   TEXT,
  season_id   TEXT,
  champion    TEXT,
  games       INTEGER,
  wins        INTEGER,
  avg_kda     REAL,
  avg_dpm     REAL,
  PRIMARY KEY (player_id, season_id, champion)
);

------------------------------------------------------------
-- import_logs: ETL 日志
------------------------------------------------------------
CREATE TABLE IF NOT EXISTS import_logs (
  id           INTEGER PRIMARY KEY AUTOINCREMENT,
  step         TEXT,
  started_at   TEXT,
  finished_at  TEXT,
  rows_in      INTEGER,
  rows_out     INTEGER,
  status       TEXT,
  message      TEXT
);
