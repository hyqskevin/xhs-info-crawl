#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

# 只 grep 读取启动参数，不 source 全部 .env
LOG_LEVEL="$(grep -E '^CELERY_LOG_LEVEL=' .env 2>/dev/null | head -1 | cut -d= -f2- || true)"
CELERY_FOLDER="$(grep -E '^CELERY_FOLDER=' .env 2>/dev/null | head -1 | cut -d= -f2- || true)"
LOG_LEVEL="${LOG_LEVEL:-INFO}"
CELERY_FOLDER="${CELERY_FOLDER:-./data/celery}"

# PaddleOCR 缓存目录重定向到项目内，避免沙箱限制写 ~/.paddlex
export PADDLE_PDX_CACHE_HOME="$ROOT_DIR/data/paddlex"
# huggingface_hub 模型缓存重定向（paddlex 传递依赖，预防写 ~/.cache/huggingface）
export HF_HOME="$ROOT_DIR/data/huggingface"

# 启动前清理上次残留的 celery beat(同 dev-worker.sh 注释)
LOG_DIR="$ROOT_DIR/data/logs"
mkdir -p "$LOG_DIR"
PYTHONPATH="$ROOT_DIR" "$ROOT_DIR/backend/.venv/bin/python" -m launcher.orphan_cleanup \
  --role beat \
  --log "$LOG_DIR/dev-beat-cleanup.log" \
  --timeout 5.0 || true

exec uv run --project backend celery -A app.tasks.celery_app:celery_app beat --loglevel="$LOG_LEVEL" --schedule "$CELERY_FOLDER/celerybeat-schedule"
