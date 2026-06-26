# Project Info

| 项 | 值 |
|----|----|
| 名称 | LoL Radar Engine |
| 仓库 | https://github.com/RouZuoMong2003/lol-radar-engine |
| 在线 Demo | https://rouzuomong2003.github.io/lol-radar-engine/ |
| License | MIT |
| 语言 | Python（ETL/后端）、HTML/CSS/JS（前端，Chart.js） |
| 运行环境 | Python ≥ 3.10（开发用 3.12）|
| 数据来源 | Oracle's Elixir（非商业、无隶属） |
| 状态 | 可运行；LCK / LCK-Cup 为已验证数据集 |

## 关键设计决策

- **CSV 唯一真源**：所有 DB / JSON 都能由 `scripts/run_all.py` 一键重算。
- **DB/API 字段名 = CSV 列名小写**，导入导出可逆。
- **二级数据优先**：尽量复用 OE 现成衍生指标（gspd/gpr/dpm/vspm/cspm/
  damageshare/earnedgoldshare/wcpm…），少做二次推导。
- **GSPD/GPR 直读**：只在 `position='team'` 行存在，直接喂入队伍 Macro 维度。
- **维度端点 0–100**：同赛区同位置内归一化，60/基线为同位置均值（橙色对照）。

## 六维与评分模型（新版）

- 重构维度：**Teamfight / Macro / Consistency**
  - 路径：一级字段 → 二级指标 → 同赛季同位置经验分位 → 分路职责加权。
- 沿用维度：Laning / Mechanics / Adaptation（同位置分位拉伸）。
- 顶部评分：
  - Player Score = 六维均值 + 最强两项上限 + 最低项下限 + 小幅胜率校正。
  - Season Rating = Player Score × 胜率结果系数 + Consistency 稳定性修正。
- 权重与公式集中在 `server/metrics.py`（`TF_WEIGHTS / MACRO_WEIGHTS /
  CONS_WEIGHTS / scores() / DIM_META`），是唯一真源，ETL 与导出都从这里取。

## 数据集说明

- 已验证：LCK-2026-Cup、LCK-2026-Rounds_1-2。
- LPL 在源 CSV 中为 partial（缺 GD/CSD/XPD@15），线上压制维度会降级处理。

## 目录速查

- ETL：`scripts/01..08` + `run_all.py` + `_common.py`
- 后端：`server/app.py`（Flask 8080）/ `api.py` / `metrics.py`
- 前端：`web/index.html` + `web/assets/` + `web/data/`（静态导出）
- 报告：`reports/`（HTML + PDF；生成脚本在 `scripts/make_*_report.py`）
- 文档：`docs/SPEC.md`（契约）/ `STRUCTURE.md` / `DATAFLOW.md`

## CI / CD

- `.github/workflows/ci.yml`：Python 字节编译 + 校验 web/data 全部 JSON 合法。
- `.github/workflows/deploy-pages.yml`：push 到 main 且改动 web/ 时自动部署 Pages。
