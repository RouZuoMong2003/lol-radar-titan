# Changelog

All notable changes to this project will be documented in this file.
The format is based on [Keep a Changelog](https://keepachangelog.com/),
and this project adheres to [Semantic Versioning](https://semver.org/).

## [v1.0.0-plantagenet] - 2026-06-26

🏰 **Codename: Plantagenet（金雀花）** — 首个稳定版本，开箱即用。

### 数据 & 模型
- L1 雷达六维：Teamfight / Laning / Macro / Mechanics / Consistency / Adaptation
- Teamfight / Macro / Consistency 三维基于一级字段二次推导，弱化纯 KP/胜率偏差
- 顶部双评分：**Player Score** + **Season Rating**
- L2 多维数据图集：26 张图 / 7 个谱，独立 `charts.html` 页面
- 同位置经验分位归一化，同位置均值作为橙色基线
- GSPD / GPR 直读自 `position='team'` 行，进入队伍 Macro 维度

### 前端
- Hash 路由：`#/p/{season}/{entity}` / `#/t/{season}/{entity}`
- 原子化路由同步（消除切换赛季/选手时的视觉爆闪）
- Loading 蒙层延迟显示（400ms 阈值，本地 JSON 永不显现）
- 移动端单列布局 + 桌面端三栏 grid
- 主题切换（亮 / 暗）+ 图集入口（📊）

### 数据集（首发）
- LCK 2026 Cup / Rounds_1-2
- LEC 2026 Spring / Versus
- LCS 2026 Spring / Lock-In
- LPL 2026 Split_1 / Split_2

### 工程
- 零配置启动脚本 `start.sh` / `start.bat`（自动建虚拟环境 + 装依赖 + 起服务）
- GitHub Actions：CI（JSON 校验）+ Pages 自动部署
- 静态导出与 Flask API 双模式，前端自动检测切换

[v1.0.0-plantagenet]: https://github.com/RouZuoMong2003/lol-radar-engine/releases/tag/v1.0.0-plantagenet
