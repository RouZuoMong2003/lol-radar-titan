#!/usr/bin/env bash
# =============================================================================
# LoL Radar Engine · 零配置启动脚本 (Linux / macOS / WSL)
#
# 用法：
#   ./start.sh           启动 Flask（http://127.0.0.1:8080）
#   ./start.sh static    仅起 Python 内置静态服务器（不需任何依赖）
#
# 首次运行会自动：
#   1. 创建本地虚拟环境 .venv/
#   2. pip install -r requirements.txt
#   3. 启动 server/app.py
# =============================================================================
set -e

cd "$(dirname "$0")"

PY="${PYTHON:-python3}"
if ! command -v "$PY" >/dev/null 2>&1; then
  echo "❌ 未找到 python3，请先安装 Python ≥ 3.10：https://www.python.org/downloads/"
  exit 1
fi

VER=$("$PY" -c 'import sys; print("%d.%d" % sys.version_info[:2])')
echo "🐍 Python: $VER"

# ---- 静态模式：零依赖，直接 http.server ----
if [ "${1:-}" = "static" ]; then
  PORT="${PORT:-8080}"
  echo "📦 静态模式：http://127.0.0.1:$PORT/"
  cd web && exec "$PY" -m http.server "$PORT"
fi

# ---- Flask 模式 ----
if [ ! -d ".venv" ]; then
  echo "🔧 首次启动：创建虚拟环境 .venv/ ..."
  "$PY" -m venv .venv
fi

# shellcheck disable=SC1091
source .venv/bin/activate

if [ ! -f ".venv/.deps_installed" ] || [ requirements.txt -nt .venv/.deps_installed ]; then
  echo "📥 安装依赖 ..."
  pip install --upgrade pip >/dev/null
  pip install -r requirements.txt
  touch .venv/.deps_installed
fi

PORT="${PORT:-8080}"
echo ""
echo "🚀 LoL Radar Engine 启动中 ..."
echo "   雷达页：  http://127.0.0.1:$PORT/"
echo "   图集页：  http://127.0.0.1:$PORT/charts.html"
echo "   API：    http://127.0.0.1:$PORT/api/seasons"
echo "   按 Ctrl+C 退出"
echo ""

exec python server/app.py