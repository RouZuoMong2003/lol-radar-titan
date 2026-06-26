# LoL Radar Engine

> 把 Oracle's Elixir 的 LoL 职业赛事数据，编译成 SQLite，
> 经过多步聚合产出**选手 / 队伍**的赛季六维能力雷达 + 26 张多维数据图集。

[![CI](https://github.com/RouZuoMong2003/lol-radar-engine/actions/workflows/ci.yml/badge.svg)](https://github.com/RouZuoMong2003/lol-radar-engine/actions/workflows/ci.yml)
[![Deploy](https://github.com/RouZuoMong2003/lol-radar-engine/actions/workflows/deploy-pages.yml/badge.svg)](https://github.com/RouZuoMong2003/lol-radar-engine/actions/workflows/deploy-pages.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Version](https://img.shields.io/badge/version-v1.0.0--plantagenet-9c27b0)](CHANGELOG.md)

🔗 **在线 Demo**：
- GitHub Pages：<https://rouzuomong2003.github.io/lol-radar-engine/>
- Wasmer Edge：<https://lol-radar-engine.wasmer.app/>（部署指南见 [`docs/DEPLOY_WASMER.md`](docs/DEPLOY_WASMER.md)）

📦 当前版本：**v1.0.0「金雀花 / Plantagenet」**（[CHANGELOG](CHANGELOG.md)）

---

## ⚡ 30 秒上手（零配置）

> Release 包内已经包含 **首发 8 个赛季的全部静态数据**（`web/data/`），下载即跑。

### 方式 A：一键启动（推荐）

```bash
# Linux / macOS / WSL
./start.sh

# Windows（双击或在 cmd 里）
start.bat
```

脚本会自动检测 Python、建 `.venv`、装 Flask，然后打开：

- 雷达页 → http://127.0.0.1:8080/
- 图集页 → http://127.0.0.1:8080/charts.html

### 方式 B：零依赖（不想装 Flask 也行）

```bash
./start.sh static          # 或 start.bat static
# 等价于：cd web && python3 -m http.server 8080
```

前端会自动检测到不是 Flask 环境，回退到读取 `web/data/` 静态 JSON，所有功能正常。

### 方式 C：纯浏览器（不装任何东西）

直接打开 `web/index.html`——大部分功能可用（除了少数浏览器对本地 `fetch()` 的 CORS 限制，建议还是用上面的方式）。

---

## 技术栈

```
CSV ──Python ETL(01..09)──▶ SQLite(radar.db) ──┬─▶ Flask API ─▶ web/index.html (Chart.js)
                                                └─▶ 静态 JSON (web/data/) ─▶ GitHub Pages
```

- 纯本地、零外部服务依赖。
- ETL 管线只用 Python 标准库；Web 只需 Flask；PDF 报告（可选）才需 WeasyPrint。
- 同一套前端两个页面：`index.html`（雷达） + `charts.html`（L2 多维图集）。

## 六维模型

| 维度 | 中文 | 说明 |
|------|------|------|
| Teamfight | 团战决策 | **新版重构**：参与 / 输出 / 生存 / 转化 / 节奏 |
| Laning | 线上压制 | GD@15 / CSD@15 / XPD@15 |
| Macro | 长线运营 | **新版重构**：视野 / 目标 / 经济 / 线转图 / 节奏 |
| Mechanics | 操作上限 | KDA / DPM / 输出占比 / 多杀 |
| Consistency | 心态稳定 | **新版重构**：高下限 / 中位影响 / 波动控制 / 死亡可靠 / 逆风韧性 |
| Adaptation | 版本适应 | 英雄池 / 近期版本胜率 / 新英雄 |

**重构思路**：`一级字段 → 二级指标 → 同赛季同位置经验分位归一化 → 按分路职责加权`。

顶部两个评分：

- **Player Score** = 六维均值 + 最强两项上限 + 最低项下限 + 小幅胜率校正
- **Season Rating** = Player Score × 胜率结果系数 + Consistency 稳定性修正

完整公式见 [`server/metrics.py`](server/metrics.py) 与 [`docs/SPEC.md`](docs/SPEC.md)。

## 首发数据集

| 赛区 | 赛季 |
|------|------|
| LCK | 2026 Cup / 2026 Rounds_1-2 |
| LEC | 2026 Spring / 2026 Versus |
| LCS | 2026 Spring / 2026 Lock-In |
| LPL | 2026 Split_1 / 2026 Split_2 |

> ⚠️ LPL 在源 CSV 中为 partial（缺 GD/CSD/XPD@15），线上压制维度会降级处理。

## 目录结构

```
lol-radar-engine/
├── start.sh / start.bat       # 零配置启动脚本
├── VERSION / CHANGELOG.md
├── README.md / LICENSE / requirements.txt
├── .github/workflows/         # CI + GitHub Pages 自动部署
├── docs/                      # SPEC / STRUCTURE / DATAFLOW
├── db/
│   ├── schema.sql             # DDL
│   └── radar.db               # 运行时数据库（仅本地，gitignore）
├── scripts/                   # ETL 管线 01..09 + run_all + _common
├── server/                    # app.py / api.py / metrics.py
├── web/                       # index.html + charts.html + assets/ + data/
└── data/                      # 源 CSV（gitignore，见 data/README.md）
```

## 进阶：重新生成数据

如果你想用自己的 OE CSV 重建数据：

```bash
# 1) 准备源 CSV
export OE_CSV=/absolute/path/to/2026_LoL_esports_match_data_from_OraclesElixir.csv

# 2) 安装 ETL 依赖（其实标准库就够，这步只是稳一点）
pip install -r requirements.txt

# 3) 一键全量：落库 + 聚合 + 导出静态 JSON
python3 scripts/run_all.py

# 4) 启动服务
./start.sh
```

### ETL 管线（scripts/）

| 步骤 | 作用 |
|------|------|
| `00_seed_from_lol_db.py` ⭐ | （可选）`lol_db.sqlite` → `match_rows`，替代 02 跳过 CSV |
| `01_init_db.py` | 建表（schema.sql） |
| `02_import_csv.py` | CSV → match_rows（流式导入） |
| `03_build_dims.py` | 生成 leagues / seasons / teams / players |
| `04_aggregate_player.py` | 选手赛季聚合 + 维度原料 |
| `05_normalize.py` | 同位置归一化 + **新版三维重构** + 评分 + 排名 |
| `06_aggregate_team.py` | 队伍赛季聚合（含 GSPD/GPR 直读） |
| `07_league_avg.py` | 同赛区同位置均值（雷达橙色基线） |
| `08_export_static.py` | 导出 RadarSubject 静态 JSON 到 `web/data/` |
| `09_export_l2_charts.py` ⭐ | 导出 26 张 L2 多维图数据到 `web/data/charts/` |
| `10_export_l1_radar.py` | L1 直透模型导出（默认数据源） |
| `run_all.py` | 依次执行流水线（`USE_LOL_DB=1` 切换 00 替代 02） |

## 核心规则（节选自 SPEC）

1. **CSV 是唯一真源**，所有衍生数据都能一键重算。
2. **二级数据优先**：尽量复用 OE 现成衍生指标（gspd/gpr/dpm/vspm/cspm…）。
3. **EGR/队伍专属直读**：`gspd`、`gpr` 只在 `position='team'` 行直接进队伍维度。
4. **维度端点统一 0–100**，同赛区同位置内部可比。
5. **接口字段沿用 CSV 列名**（小写、保留语义），导入导出可逆。

## 数据来源与免责声明

比赛数据来自 [Oracle's Elixir](https://oracleselixir.com/)。本项目为**非商业**的数据分析与可视化练习，
与 Oracle's Elixir、Riot Games 无隶属或背书关系。数据版权归原始来源所有。

## License

[MIT](LICENSE)