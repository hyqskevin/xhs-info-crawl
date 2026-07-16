#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

set -a
source "$ROOT_DIR/.env"
set +a

command -v opencli >/dev/null || { echo "缺少 OpenCLI，请先运行 npm install -g @jackwener/opencli"; exit 1; }

echo "正在检查 OpenCLI 浏览器连接..."
opencli doctor >/dev/null

echo "正在检查小红书登录态（Cookie 仅由 OpenCLI 从 Chrome 会话中复用，不会输出或保存）..."
if ! opencli xiaohongshu whoami -f json --window background >/dev/null; then
  echo "未登录或登录态已过期。请在当前 Chrome 登录小红书，然后重新运行 make test-opencli。"
  exit 77
fi

query="${1:-上海 周末活动}"
limit="${2:-3}"
echo "登录检查通过，执行只读搜索：${query}（${limit} 条）"
exec opencli xiaohongshu search "$query" --limit "$limit" -f json --window background --trace retain-on-failure
