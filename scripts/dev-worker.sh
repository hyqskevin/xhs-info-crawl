#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

# 只 grep 读取启动参数，不 source 全部 .env
POOL="$(grep -E '^CELERY_WORKER_POOL=' .env 2>/dev/null | head -1 | cut -d= -f2- || true)"
CONCURRENCY="$(grep -E '^CELERY_WORKER_CONCURRENCY=' .env 2>/dev/null | head -1 | cut -d= -f2- || true)"
LOG_LEVEL="$(grep -E '^CELERY_LOG_LEVEL=' .env 2>/dev/null | head -1 | cut -d= -f2- || true)"
POOL="${POOL:-solo}"
CONCURRENCY="${CONCURRENCY:-1}"
LOG_LEVEL="${LOG_LEVEL:-INFO}"

# PaddleOCR 缓存目录重定向到项目内，避免沙箱限制写 ~/.paddlex
export PADDLE_PDX_CACHE_HOME="$ROOT_DIR/data/paddlex"
# huggingface_hub 模型缓存重定向（paddlex 传递依赖，预防写 ~/.cache/huggingface）
export HF_HOME="$ROOT_DIR/data/huggingface"

# 启动前清理上次残留的 celery worker(dev 模式 uv run wrapper 跟 shell 同 PGID,
# 仅靠命令行精确匹配 + 排除调用方 PID,详见 spec 2026-08-22-worker-cleanup-on-startup §4.3)
LOG_DIR="$ROOT_DIR/data/logs"
mkdir -p "$LOG_DIR"
PYTHONPATH="$ROOT_DIR" "$ROOT_DIR/backend/.venv/bin/python" -m launcher.orphan_cleanup \
  --role worker \
  --log "$LOG_DIR/dev-worker-cleanup.log" \
  --timeout 5.0 || true

exec uv run --project backend celery -A app.tasks.celery_app:celery_app worker --pool="$POOL" --concurrency="$CONCURRENCY" --loglevel="$LOG_LEVEL"
