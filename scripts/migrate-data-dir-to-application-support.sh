#!/usr/bin/env bash
# 数据目录迁移:把 $HOME/.xhs-info-crawl/ 拷到 $HOME/Library/Application Support/com.xhs-info-crawl.local/
# 排除 .env(含已失效的 DATA_DIR=./data 配置),然后 6 道不变量校验,不通过自动 rmtree DEST 回滚
#
# 前置:.app 必须先关闭(uvicorn / celery worker / celery beat 都不能在跑)
# 关联 spec: docs/superpowers/specs/2026-08-24-migrate-data-dir-to-application-support-default-design.md
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"; cd "$ROOT_DIR"

SRC="${HOME}/.xhs-info-crawl"
DEST="${HOME}/Library/Application Support/com.xhs-info-crawl.local"

# 显式把路径当参数注入,避免 helper 里硬编码 / home expansion
exec uv run --project backend python -c "
import sys
sys.path.insert(0, '${ROOT_DIR}/scripts/lib')
from data_dir_migration import run_migration
from pathlib import Path
run_migration(Path('${SRC}'), Path('${DEST}'))
"