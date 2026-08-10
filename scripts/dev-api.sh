#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

# 只 grep 读取启动参数，不 source 全部 .env
# 其余配置由 pydantic_settings 直接读 .env 文件，避免 os.environ 旧值覆盖 .env 新值
API_HOST="$(grep -E '^API_HOST=' .env 2>/dev/null | head -1 | cut -d= -f2- || true)"
API_PORT="$(grep -E '^API_PORT=' .env 2>/dev/null | head -1 | cut -d= -f2- || true)"
API_HOST="${API_HOST:-127.0.0.1}"
API_PORT="${API_PORT:-8000}"

exec uv run --project backend uvicorn app.main:app --app-dir backend --host "$API_HOST" --port "$API_PORT" --reload
