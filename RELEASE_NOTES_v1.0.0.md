# 🏰 v1.0.0「金雀花 / Plantagenet」

LoL Radar Engine 的首个稳定版本。本 Release 内含 **完整源代码 + 全部静态数据**，下载解压即可运行，无需联网拉数据。

## 📦 包含什么

| 内容 | 路径 | 说明 |
|------|------|------|
| 前端两个页面 | `web/index.html` + `web/charts.html` | 雷达页 + L2 多维图集 |
| 静态数据 | `web/data/` | 8 个赛季全部预生成 JSON |
| ETL 管线 | `scripts/01..10` | 从 OE CSV 重建数据全套 |
| 后端 API | `server/app.py` | Flask，端口 8080 |
| 一键启动 | `start.sh` / `start.bat` | 自动建 venv + 装依赖 |
| 文档 | `docs/SPEC.md` 等 | 数据契约、结构、流向 |

## 📥 下载哪个？

| 附件 | 大小 | 何时下载 |
|------|------|---------|
| **`lol-radar-engine-v1.0.0-plantagenet.zip`** | ~3 MB | **Windows 用户首选**，解压双击 `start.bat` |
| **`lol-radar-engine-v1.0.0-plantagenet.tar.gz`** | ~1.6 MB | **Linux/macOS 用户首选**，解压 `./start.sh` |
| `lol-radar-engine-v1.0.0-plantagenet-radar-db.tar.gz` | ~2 MB | 可选：仅当你想用 `/api/...` 动态接口（不是静态 JSON）时下载，解压到项目根目录覆盖 `db/` |

> 99% 的用户只需要前两个之一。雷达页/图集页读的都是 `web/data/` 静态 JSON，**不需要** radar.db。

## ⚡ 三种使用姿势

```bash
# A. 一键启动（推荐）
./start.sh                  # Linux / macOS / WSL
start.bat                   # Windows

# B. 零依赖静态服务
./start.sh static

# C. 直接打开 web/index.html
```

打开浏览器访问 http://127.0.0.1:8080/

## ✨ 首发亮点

- **L1 直透雷达**：六维能力可视化，同位置基线对照
- **L2 多维图集**：26 张图覆盖团战、运营、版本适应等 7 个谱系
- **零爆闪切换**：原子化路由 + 延迟蒙层，毫秒级切换无视觉抖动
- **真正开箱即用**：内置 8 个赛季数据，不需要重跑 ETL

## 🎯 首发数据集

LCK / LEC / LCS / LPL 共 8 个 2026 赛季。LPL 因源数据缺 @15 字段，线上压制维度会降级。

## 🔧 系统要求

- Python ≥ 3.10（生成 PDF 报告可选 WeasyPrint 系统依赖）
- 现代浏览器（Chrome 90+ / Firefox 88+ / Safari 14+）

## 📜 License

MIT —— 数据归 [Oracle's Elixir](https://oracleselixir.com/) 所有，本项目仅供非商业分析使用。

---

完整变更日志见 [CHANGELOG.md](CHANGELOG.md)。