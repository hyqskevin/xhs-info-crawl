#!/usr/bin/env bash
# tests/scripts/test_poster_real_render.sh
# 真 opencli 集成测试占位。
#
# 真实流程（spec §3.2.7 + §5.2）：
# 1. 启 python -m http.server 用于 opencli 浏览；
# 2. 调 API 创建任务 + preview 拿到 HTML；
# 3. 写 HTML 到临时文件，通过 http.server 暴露；
# 4. opencli browser open http://127.0.0.1:<port>/_tmp.html；
# 5. opencli browser screenshot --output data/posters/<id>.png --full-page；
# 6. 断言 PNG magic 前 8 字节；
# 7. 清理 http.server。
#
# 当前状态：本脚本占位——**未实施**。
# 见 tests/poster-generation-CHANGELOG.md §3.2。

set -euo pipefail

say() { printf '\n\033[1;36m▶ %s\033[0m\n' "$*"; }
ok()  { printf '\033[1;32m✓\033[0m %s\n' "$*"; }
fail(){ printf '\033[1;31m✗\033[0m %s\n' "$*"; exit 1; }

BASE_URL="${BASE_URL:-http://127.0.0.1:8000}"
ADMIN_USERNAME="${ADMIN_USERNAME:-admin}"
ADMIN_PASSWORD="${ADMIN_PASSWORD:-Admin@123}"

if ! command -v opencli >/dev/null; then
  fail "opencli 未安装；本脚本依赖 opencli"
fi

# 占位：以下逻辑未实装
fail "tests/scripts/test_poster_real_render.sh 尚未实施——见 tests/poster-generation-CHANGELOG.md §3.2"
