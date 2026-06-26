# 数据血缘（DATAFLOW）

```
┌────────────────────────────────────────────────────────────────┐
│ /workspace/data/2026_LoL_esports_match_data_from_OraclesElixir │
│                  CSV  46MB / 165 列 / 70729 行                 │
└──────────────────────────────┬─────────────────────────────────┘
                               │
                               ▼ 02_import_csv.py（流式 + 过滤 datacompleteness=complete）
                       ┌───────────────┐
                       │  match_rows   │ ~65k 行（player 行 + team 行）
                       └───────┬───────┘
                               │
        ┌──────────────────────┼──────────────────────┐
        ▼                                             ▼
03_build_dims.py                          04_aggregate_player.py
（去重生成字典）                          （GROUP BY player_id, season_id）
        │                                             │
        ▼                                             ▼
┌────────────────┐                          ┌─────────────────────┐
│ leagues(30)    │                          │ player_season_raw   │
│ seasons(150)   │                          │ 含 6 维度原始分     │
│ teams(300)     │                          └──────────┬──────────┘
│ players(2000)  │                                     │
└────────────────┘                                     ▼
                                          05_normalize.py
                                          （同 league+season+position 组 z-score）
                                                       │
                                                       ▼
                                          ┌─────────────────────┐
                                          │ player_season(final)│
                                          │ 6 维度 0-100 + rank │
                                          └──────────┬──────────┘
                                                     │
                                                     ▼
                                          06_aggregate_team.py
                                          （选手加权 + team 行直读 gspd/gpr）
                                                     │
                                                     ▼
                                          ┌─────────────────────┐
                                          │ team_season         │
                                          └──────────┬──────────┘
                                                     │
                                                     ▼
                                          07_league_avg.py
                                                     │
                                                     ▼
                                          ┌─────────────────────┐
                                          │ league_average      │← 雷达橙色基线
                                          └─────────────────────┘
```

## 字段血缘（节选关键项）

| 最终字段 | 来源（CSV 列） | 经过的步骤 |
|---|---|---|
| `player_season.d_mechanics` | `kills, deaths, assists, dpm, damageshare, doublekills..pentakills` | 02 → 04 → 05 |
| `player_season.d_macro`     | `vspm, wcpm, earnedgoldshare, firsttower(team行)` | 02 → 04 → 05 |
| `team_season.d_macro`       | **`gspd`(team行) + `gpr`(team行)** + 选手 `wcpm` | 02 → 06 |
| `league_average.d_*`        | 同位置同赛季全选手均值 | → 07 |

## 各步骤产出表 & 删除策略

| 步骤 | 写入表 | 重跑策略 |
|---|---|---|
| 02 | `match_rows` | `DELETE WHERE season_id=?` 后批量插 |
| 03 | `leagues/seasons/teams/players` | `INSERT OR REPLACE` |
| 04 | `player_season`（除 d_* 与 rank） | `DELETE WHERE season_id=?` 后插 |
| 05 | `player_season.d_*, rank_*, text_score, season_rating` | UPDATE |
| 06 | `team_season` | `DELETE WHERE season_id=?` 后插 |
| 07 | `league_average` | `DELETE WHERE season_id=?` 后插 |
