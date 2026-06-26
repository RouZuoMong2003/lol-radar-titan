#!/usr/bin/env bash
# =============================================================================
# 打包脚本：生成可上传到 GitHub Release 的 zip / tar.gz
#
# 用法：
#   ./scripts/make_release.sh              # 默认 v1.0.0-plantagenet
#   ./scripts/make_release.sh v1.0.1       # 自定义标签
#
# 输出：
#   dist/lol-radar-engine-<tag>.zip
#   dist/lol-radar-engine-<tag>.tar.gz
#
# 包含：
#   ✅ 全部源码（前端/后端/ETL/文档）
#   ✅ web/data/ 全部静态 JSON（首发 8 个赛季）
#   ✅ start.sh / start.bat / requirements.txt
#
# 排除：
#   ❌ .venv/ __pycache__/ *.pyc
#   ❌ db/*.db db/*.pkl
#   ❌ data/*.csv（源 CSV 版权归 OE，不打包）
#   ❌ .git/ .github/ 工程内部文件（按需保留 .github 给 CI）
# =============================================================================
set -e

cd "$(dirname "$0")/.."

TAG="${1:-v1.0.0-plantagenet}"
NAME="lol-radar-engine-${TAG}"
OUT="dist"
STAGE="$OUT/$NAME"

echo "📦 Building release: $NAME"

rm -rf "$STAGE"
mkdir -p "$STAGE"

# 用 tar 的 --exclude 在管道里筛掉不需要的内容（避免硬依赖 rsync）
EXCLUDES=(
  --exclude='./.git'
  --exclude='./.venv'
  --exclude='./__pycache__'
  --exclude='*/__pycache__'
  --exclude='*.pyc'
  --exclude='*.pyo'
  --exclude='*.bak'
  --exclude='*.log'
  --exclude='*.tmp'
  --exclude='.DS_Store'
  --exclude='Thumbs.db'
  --exclude='./.gemini'
  --exclude='./.vscode'
  --exclude='./.idea'
  --exclude='./dist'
  --exclude='./db/*.db'
  --exclude='./db/*.db-shm'
  --exclude='./db/*.db-wal'
  --exclude='./db/_stage_*.pkl'
  --exclude='./data/*.csv'
  --exclude='*/preview'
)

tar -cf - "${EXCLUDES[@]}" . | tar -xf - -C "$STAGE/"

# 把 TAG 写进 VERSION
echo "$TAG" > "$STAGE/VERSION"

# 关键：强制设可执行位（源仓库在 sdcard/FAT 上时权限位丢失）
chmod +x "$STAGE/start.sh" "$STAGE/scripts/make_release.sh" 2>/dev/null || true
find "$STAGE/scripts" -name '*.sh' -exec chmod +x {} \; 2>/dev/null || true

# 生成压缩包
cd "$OUT"
echo "🗜  Zipping ..."
if command -v zip >/dev/null 2>&1; then
  zip -qr "${NAME}.zip" "$NAME"
else
  # 兜底：用 Python zipfile，避免依赖系统 zip
  python3 -c "import shutil, sys; shutil.make_archive('${NAME}', 'zip', '.', '${NAME}')"
fi
echo "🗜  Tarring ..."
tar -czf "${NAME}.tar.gz" "$NAME"

# ── 可选附件：radar.db（运行 Flask API 才需要；大多数人读 web/data/ 静态 JSON 就够） ──
if [ -f "../db/radar.db" ]; then
  echo "🗜  Packing optional radar.db ..."
  # 单独打成 tar.gz，让用户按需下载，不强塞进主包
  tar -czf "${NAME}-radar-db.tar.gz" -C .. db/radar.db db/schema.sql
fi

# 摘要
echo ""
echo "✅ Done. Artifacts:"
ls -lh "${NAME}.zip" "${NAME}.tar.gz" ${NAME}-radar-db.tar.gz 2>/dev/null \
  | awk '{print "   " $NF "  (" $5 ")"}'

# 同时给出 SHA256（GitHub Release 描述里挂上更专业）
echo ""
echo "🔐 SHA256:"
if command -v sha256sum >/dev/null 2>&1; then
  sha256sum "${NAME}.zip" "${NAME}.tar.gz" ${NAME}-radar-db.tar.gz 2>/dev/null
else
  shasum -a 256 "${NAME}.zip" "${NAME}.tar.gz" ${NAME}-radar-db.tar.gz 2>/dev/null
fi

echo ""
echo "下一步："
echo "  1. 检查 dist/${NAME}/ 内容"
echo "  2. 上传两个压缩包到 GitHub Release（tag: $TAG）"
echo "  3. Release 描述贴 RELEASE_NOTES_v1.0.0.md 的内容"