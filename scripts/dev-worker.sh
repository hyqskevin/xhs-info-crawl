#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

exec uv run --project backend celery -A app.tasks.celery_app:celery_app worker --pool=solo --loglevel=INFO
