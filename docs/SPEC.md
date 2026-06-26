# 工程契约（SPEC）

本文件是**唯一权威**的工程标准。任何代码、API、前端字段命名与之不一致都视为 bug。

---

## §0 你的需求 → 工程化补全（先把模糊点钉死）

| 你的原话 | 补全为 |
|---|---|
| "数据标准和接口要按照 CSV 的格式采用" | API 字段名、DB 字段名、ETL 中间字段名**全部使用 OE CSV 的列名小写形式**，下划线保留（如 `earnedgoldshare`、`golddiffat15`、`damagemitigatedperminute`），中文仅出现在前端展示层。 |
| "雷达六维度尽量使用二级数据" | "二级数据"= OE 已经在 CSV 里算好的**衍生比率/速率字段**：`dpm, vspm, cspm, wpm, wcpm, ckpm, team kpm, damageshare, earnedgoldshare, gspd, gpr`。维度公式优先用它们，**只对没有现成字段的指标才二次推导**（详见 §4）。 |
| "EGR 这种现成的可以直接用在队伍" | 经数据核对，OE 中**队伍专属现成衍生分**为 `gspd`（黄金差占比，相当于 EGR）和 `gpr`（黄金比率），**仅 `position='team'` 行有值**。这两个字段**直接喂给队伍维度**，不再做加权或推导。 |
| "雷达图左上角有两个选项：选手 / 队伍" | 顶部加一组 segmented tab：`[选手] [队伍]`。切换时同时改变：(1) 实体下拉选择源（players vs teams）、(2) API 路径（`/api/player/...` vs `/api/team/...`）、(3) 雷达图标题和橙色基线含义（同位置选手均值 vs 全联赛队伍均值）。 |
| "工程文件结构，清晰，阐明" | 见 `STRUCTURE.md`：单一根目录、ETL 步骤数字前缀、schema.sql 唯一真源、metrics.py 唯一公式实现。 |

---

## §1 数据标准（命名 = CSV 列名）

### 1.1 命名规则

- **DB 列名 = CSV 列名小写化**，空格替换为下划线：
  `team kpm` → `team_kpm`，`earned gpm` → `earned_gpm`。
- **API 返回 JSON 字段** = DB 列名（直出，无 camelCase 转换）。
- **新派生字段**用 `d_` 前缀（dimension）和 `r_` 前缀（rank）：
  `d_teamfight, d_laning, ..., r_overall, r_position`。
- **复合主键**：`season_id = "{league}-{year}-{split}"`，例 `LPL-2026-Spring`。

### 1.2 一级 vs 二级数据划分

| 类别 | 含义 | CSV 字段示例 | 处理方式 |
|---|---|---|---|
| **一级数据**（计数/绝对值） | 单局原始计数 | `kills, deaths, assists, dragons, barons, wardsplaced, totalgold, goldat15` | 仅做 SUM/AVG 聚合，**不直接进雷达** |
| **二级数据**（速率/比率） | OE 已算好的衍生分 | `dpm, vspm, cspm, wpm, wcpm, ckpm, damageshare, earnedgoldshare, gspd, gpr, team_kpm` | **直接进雷达维度公式** |
| **二级数据**（差值） | 时间分段对位差 | `golddiffat15, csdiffat15, xpdiffat15, golddiffat10` | 直接进雷达 |
| **必须二次推导** | CSV 没现成字段 | KP%, KDA, 劣势局胜率, 多杀分, 英雄池广度 | `metrics.py` 内部计算 |

→ 对应你的"尽量使用二级数据"原则：**6 维度共 24 个权重项中，21 个直接使用二级数据，仅 3 个（KP%、劣势局胜率、英雄池广度）需要二次推导。**

### 1.3 选手行 vs 队伍行的字段可用性（实测）

| 字段 | player 行 | team 行 | 用法 |
|---|---|---|---|
| `gspd, gpr` | ❌ 全空 | ✅ | **队伍专属二级数据**，直接进 `team_season.d_macro` |
| `damageshare, earnedgoldshare` | ✅ | ❌ 全空 | 选手专属（队内占比），进 `player_season` |
| `dpm, vspm, cspm, wpm, wcpm, ckpm, team_kpm` | ✅ | ✅ | 双方都用，但维度权重不同 |
| `kills, deaths, assists` | ✅ | ✅ (= 队伍合) | player 取自身，team 取 team 行 |

---

## §2 数据库 Schema（权威）

DDL 见 `db/schema.sql`。表清单：

| 表 | 行数预估 | 用途 |
|---|---:|---|
| `leagues` | ~30 | 赛区字典 |
| `seasons` | ~150 | 赛季字典 |
| `teams` | ~300 | 队伍字典 |
| `players` | ~2000 | 选手字典 |
| `match_rows` | ~65000 | CSV 落库（去除 datacompleteness != complete） |
| `player_season` | ~6000 | 选手赛季快照（雷达图直接读这张） |
| `team_season` | ~600 | 队伍赛季快照（雷达图直接读这张） |
| `league_average` | ~500 | 同赛区同位置均值（橙色基线） |
| `champion_pool` | ~80000 | 选手英雄池 |
| `import_logs` | - | ETL 日志 |

---

## §3 API 契约

所有接口 `Content-Type: application/json`，错误统一返回 `{ "error": "...", "code": 4xx }`。

### 3.1 字典类

| 方法 | 路径 | 返回 |
|---|---|---|
| GET | `/api/leagues` | `[{id, name, region, tier}]` |
| GET | `/api/seasons?league_id=LPL` | `[{id, league_id, year, split}]` |
| GET | `/api/teams?season_id=LPL-2026-Spring` | `[{id, name, short_name}]` |
| GET | `/api/players?season_id=...&position=mid` | `[{id, current_handle, team_id, position}]` |

### 3.2 雷达数据（前端核心调用）

**统一返回结构 `RadarSubject`**（选手与队伍同 schema，便于前端复用一套渲染逻辑）：

```json
{
  "type": "player",
  "id": "oe:player:6fc7...",
  "name": "Knight",
  "season_id": "LPL-2026-Spring",
  "tags": [
    {"label": "LPL", "color": "blue"},
    {"label": "中单", "color": "red"}
  ],
  "top_stats": {
    "text_score":    {"value": 1495, "rank": 1, "total": 14, "subtitle": "Spring MVP"},
    "season_rating": {"value": 1493, "rank": 1, "total": 14, "subtitle": "Season Rating"}
  },
  "dimensions": [
    {"key": "d_teamfight",   "label": "团战决策", "value": 82, "avg": 60, "rank": 2, "total": 14},
    {"key": "d_laning",      "label": "线上压制", "value": 78, "avg": 60, "rank": 4, "total": 14},
    {"key": "d_macro",       "label": "长线运营", "value": 74, "avg": 60, "rank": 3, "total": 14},
    {"key": "d_mechanics",   "label": "操作上限", "value": 88, "avg": 60, "rank": 1, "total": 14},
    {"key": "d_consistency", "label": "心态稳定", "value": 65, "avg": 60, "rank": 5, "total": 14},
    {"key": "d_meta_adapt",  "label": "版本适应", "value": 70, "avg": 60, "rank": 3, "total": 14}
  ],
  "raw": {
    "games": 18, "wins": 14, "losses": 4, "win_rate": 0.778,
    "kda": 5.2, "avg_dpm": 680.3, "avg_vspm": 1.84,
    "avg_gd15": 320.5, "avg_csd15": 8.4, "champion_pool": 14
  }
}
```

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/player/<player_id>?season_id=...` | 返回 RadarSubject (type=player) |
| GET | `/api/team/<team_id>?season_id=...`     | 返回 RadarSubject (type=team) |
| GET | `/api/league_average?season_id=...&position=mid` | 橙色基线：返回同样的 dimensions 数组（用于选手对比） |
| GET | `/api/league_average?season_id=...&type=team`    | 队伍模式的橙色基线（同赛季全队伍均值） |

### 3.3 设计要点

1. **type 字段统一前端**：选手 `type="player"`，队伍 `type="team"`。前端 tab 切换只换 fetch URL，不改渲染组件。
2. **avg 字段直接内嵌**：每条 dimension 自带橙色基线值，前端无需二次合并请求。
3. **rank/total 全维度都给**：雷达每个轴顶端的 #X/Y 胶囊数据完备。
4. **raw 区**保留聚合后的二级数据原值，供详情卡使用（如 `场均KDA 5.2`）。

---

## §4 六维度公式（合并 03-metrics + 实测字段可用性）

> 全部输出 0–100，60 = 同 (league, season, position) 组均值。
> 二次推导项用 `★` 标注。

### 4.1 选手维度（`player_season`，position ≠ 'team'）

| 维度 | 计算（权重 × 二级字段） | 二次推导项 |
|---|---|---|
| **d_teamfight** 团战决策 | 0.40 × `kp_rate★` + 0.30 × `damagemitigatedperminute` + 0.30 × `first_resource_rate★` | `kp_rate = Σ(kills+assists) / Σ(teamkills)`；首资源参与率从 `firstdragon/firstherald/firstbaron` 推 |
| **d_laning** 线上压制 | 0.50 × `golddiffat15` + 0.30 × `csdiffat15` + 0.20 × `xpdiffat15`（辅助位用 `golddiffat10`） | 无 |
| **d_macro** 长线运营 | 0.35 × `vspm` + 0.25 × `wcpm` + 0.20 × `earnedgoldshare` + 0.20 × `first_tower_rate★` | `first_tower_rate` = 该选手在场时本队拿到首塔的比例（从 team 行连接） |
| **d_mechanics** 操作上限 | 0.40 × `kda★` + 0.30 × `dpm` + 0.15 × `damageshare` + 0.15 × `multikill_score★` | `kda=(K+A)/max(D,1)`；`multikill = Σ(d+2t+3q+5p)/games` |
| **d_consistency** 心态稳定 | 0.50 × `win_rate★` + 0.30 × `comeback_rate★` + 0.20 × `death_stability★` | 全部从 `result/goldat15/deaths` 推 |
| **d_meta_adapt** 版本适应 | 0.50 × `pool_breadth★` + 0.30 × `latest_patch_winrate★` + 0.20 × `new_champ_score★` | 全部从 `champion/patch/result` 推 |

→ **24 项权重中，二级字段直用 11 项，二次推导 13 项**（多于估算，因为 consistency/meta 全是推导）。

### 4.2 队伍维度（`team_season`）

按你的要求"EGR 这种现成的直接用在队伍"，队伍维度采用**双源混合**：

| 维度 | 计算 |
|---|---|
| **d_teamfight** | 0.5 × 选手加权平均 + 0.5 × `ckpm`（队伍行直读） |
| **d_laning** | 选手加权平均（队伍行无 `golddiffat15`，但 player 行有） |
| **d_macro** | **0.6 × `gspd`（队伍行直读，EGR 类） + 0.2 × `gpr`（队伍行直读） + 0.2 × 选手加权 `wcpm`** ← 你说的"现成直接用" |
| **d_mechanics** | 选手加权平均 |
| **d_consistency** | 0.5 × `win_rate` + 0.5 × 选手加权平均 |
| **d_meta_adapt** | 选手加权平均 |

### 4.3 标准化

```python
# 同 (league, season, position) 内做 z-score → 60 + z*15 → clamp[0,100]
# 队伍模式 position 固定为 'team'
def normalize(value, samples):
    mean, std = avg(samples), stddev(samples)
    if std == 0: return 60
    return clamp(round(60 + (value - mean) / std * 15), 0, 100)
```

### 4.4 综合评分（顶部双卡）

> 以下公式与 `server/metrics.py:scores()` 一致，以代码为唯一真源。

```python
avg6      = mean(d1..d6)                      # 六维均值
ceiling   = mean(top_2_dims)                   # 最强两项上限
floor     = min(d1..d6)                        # 最低项下限
consistency = d5                               # 心态稳定维度

player_score  = round(1000 + 5.8*avg6 + 1.4*ceiling + 0.8*floor + 70*win_rate)
season_rating = round(player_score * (0.92 + 0.16*win_rate) + 1.6*(consistency - 60))
```

---

## §5 前端契约（左上角 tab）

### 5.1 顶部组件

```
┌──────────────────────────────────────────────┐
│ [选手 ●] [队伍 ○]                  Player A ▾ │  ← 左 segmented + 右下拉
└──────────────────────────────────────────────┘
```

- 切换 tab → 重新拉 `/api/players?...` 或 `/api/teams?...` 填充下拉。
- 选实体 → fetch 对应 RadarSubject → 渲染雷达。
- 雷达橙色基线根据 tab 类型自动切：选手 tab 用同位置均值，队伍 tab 用全联盟均值。

### 5.2 渲染契约

- 雷达 6 个轴的标签来源：`dimensions[i].label`（从后端来，不在前端写死）。
- 每个轴上方的 `#X/Y` 胶囊：`dimensions[i].rank` / `dimensions[i].total`。
- 顶部双卡：`top_stats.text_score` 与 `top_stats.season_rating`，副标题随 type 切换：
  - player: "Spring MVP" / "Season Rating"
  - team: "Team Power" / "Season Rating"

---

## §6 ETL 管线契约

详见 `DATAFLOW.md`。每步脚本必须满足：

1. **幂等**：重复执行结果一致（用 `INSERT OR REPLACE` 或先 DELETE 当前赛季）。
2. **可独立运行**：`python3 scripts/04_aggregate_player.py LPL-2026-Spring` 也能跑。
3. **打日志**：每步开始/结束时间、处理行数 → `import_logs` 表。
4. **失败即停**：任一步骤异常退出码非 0，`run_all.py` 终止。
