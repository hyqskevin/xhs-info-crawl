#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

set -a
source "$ROOT_DIR/.env"
set +a

exec uv run --project backend uvicorn app.main:app --app-dir backend --host "$API_HOST" --port "$API_PORT" --reload
