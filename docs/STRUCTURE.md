# 目录结构（权威版）

```
lol-radar-engine/
│
├── README.md                  ← 项目门面：一句话栈 + 一键跑通命令
│
├── docs/                      ← 设计与契约（不可执行）
│   ├── STRUCTURE.md             本文件，目录索引
│   ├── SPEC.md                  工程契约：数据标准 + API 契约 + 6 维度公式
│   └── DATAFLOW.md              数据血缘：8 步管线每步的输入→输出
│
├── db/                        ← 数据库层
│   ├── schema.sql               DDL：leagues / seasons / teams / players /
│   │                             match_rows / player_season / team_season /
│   │                             league_average / champion_pool / import_logs
│   └── radar.db                 运行时 SQLite 文件（脚本生成；可删除重建）
│
├── scripts/                   ← ETL 管线（每个文件 = 一个独立步骤）
│   ├── 01_init_db.py            执行 schema.sql 建库
│   ├── 02_import_csv.py         流式解析 CSV → match_rows（批量 500/事务）
│   ├── 03_build_dims.py         去重生成 leagues / seasons / teams / players
│   ├── 04_aggregate_player.py   match_rows → player_season（含 6 维度原始分）
│   ├── 05_normalize.py          同位置 z-score 标准化 + 排名 + text_score
│   ├── 06_aggregate_team.py     选手加权 + 队伍 team 行直读 → team_season
│   ├── 07_league_avg.py         同赛区同位置均值 → league_average（橙色基线）
│   └── run_all.py               依次跑 01→07，计时打印
│
├── server/                    ← Web 层（Flask）
│   ├── app.py                   入口：注册蓝图、静态文件、CORS
│   ├── api.py                   REST API（见 SPEC §3）
│   └── metrics.py               6 维度公式（scripts/04 与本层共用）
│
├── web/                       ← 前端（无构建工具，原生 HTML+JS）
│   ├── index.html               主页，左上角 [选手|队伍] tab 切换
│   └── assets/
│       ├── radar.css            从 lol-radar/index.html 抽出的样式
│       └── radar.js             Chart.js 初始化 + 数据 fetch + tab 逻辑
│
└── data/                      ← 仅放本工程私有的小数据
    └── (CSV 大文件统一在 /workspace/data/，不复制)
```

## 文件命名约定

| 模式 | 含义 |
|---|---|
| `01_xxx.py`, `02_xxx.py` | ETL 步骤脚本，前缀数字代表执行顺序 |
| `schema.sql` | 唯一的 DDL 真源，禁止在 Python 里重复定义表结构 |
| `metrics.py` | 6 维度公式的唯一实现，ETL 与 API 都从此处导入 |
| `*.md` 全部用小写 + kebab-case 不适用，统一大写避免误删 | 文档命名 |

## 跨项目关系

| 关联项目 | 关系 |
|---|---|
| `/workspace/projects/lol-radar/` | 视觉原型（保留），本工程沿用其 CSS/雷达画法 |
| `/workspace/projects/lol-read/` | 设计文档源头，`docs/SPEC.md` 是它的工程化收敛 |
| `/workspace/data/2026_LoL_esports_match_data_from_OraclesElixir.csv` | 唯一数据真源 |
