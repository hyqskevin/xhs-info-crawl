#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

set -a
source "$ROOT_DIR/.env"
set +a

exec uv run --project backend celery -A app.tasks.celery_app:celery_app beat --loglevel="$CELERY_LOG_LEVEL" --schedule "$CELERY_FOLDER/celerybeat-schedule"
