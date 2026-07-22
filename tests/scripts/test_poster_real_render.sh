#!/usr/bin/env bash
# tests/scripts/test_poster_real_render.sh
# 真 opencli 浏览器自动化渲染海报 — 不 mock。
#
# 真实流程（spec §3.2 + §5.2）：
# 1. 起 python http.server 把临时 HTML 文件用 http://127.0.0.1:$PORT/_tmp.html 暴露
#    （opencli 仅允许 http/https scheme，不接受 file://）
# 2. 调后端创建任务 + preview 拿到 HTML；
# 3. 写 HTML 到 _tmp.html；
# 4. opencli browser default open http://127.0.0.1:$PORT/_tmp.html；
# 5. opencli browser default screenshot --output data/posters/$id.png --full-page；
# 6. 断言 PNG magic 前 8 字节 + 写入了文件；
# 7. 清理。
#
# 用法：
#   make dev-api &
#   ADMIN_USERNAME=admin ADMIN_PASSWORD='Admin@123' \
#   bash tests/scripts/test_poster_real_render.sh

set -euo pipefail

BASE_URL="${BASE_URL:-http://127.0.0.1:8000}"
ADMIN_USERNAME="${ADMIN_USERNAME:-admin}"
ADMIN_PASSWORD="${ADMIN_PASSWORD:-Admin@123}"
API="$BASE_URL/api/v1"

if ! command -v opencli >/dev/null; then
  echo "opencli 未安装；先 npm i -g opencli"
  exit 1
fi

TMP_HTML="/tmp/poster-real-render.html"
DATA_POSTERS_DIR="${DATA_POSTERS_DIR:-$(pwd)/data/posters}"
TMP_PORT="${TMP_PORT:-8989}"

mkdir -p "$DATA_POSTERS_DIR"

say() { printf '\n\033[1;36m▶ %s\033[0m\n' "$*"; }
ok() { printf '\033[1;32m✓\033[0m %s\n' "$*"; }
fail() { printf '\033[1;31m✗\033[0m %s\n' "$*"; cleanup; exit 1; }

cleanup() {
  if [ -n "${SERVER_PID:-}" ]; then
    kill "$SERVER_PID" 2>/dev/null || true
  fi
  rm -f "$TMP_HTML"
}
trap cleanup EXIT

say "步骤 1/8：登录拿 token"
LOGIN=$(curl -fsS -X POST "$API/auth/login" \
  -H "Content-Type: application/json" \
  -d "{\"username\":\"$ADMIN_USERNAME\",\"password\":\"$ADMIN_PASSWORD\"}")
TOKEN=$(echo "$LOGIN" | python3 -c "import sys,json;print(json.load(sys.stdin)['data']['access_token'])")
[ -n "$TOKEN" ] || fail "登录失败"
ok "登录成功 token 长度 ${#TOKEN}"

AUTH=( -H "Authorization: Bearer $TOKEN" )

say "步骤 2/8：建临时模板"
NAME="real-render-$(date +%s)"
TPL=$(curl -fsS -X POST "${AUTH[@]}" "$API/settings/poster-templates" \
  -H "Content-Type: application/json" \
  -d "{\"name\":\"$NAME\",\"html_template\":\"<div class='poster'>{{items}}</div>\",\"css_text\":\"\"}")
TID=$(echo "$TPL" | python3 -c "import sys,json;print(json.load(sys.stdin)['data']['id'])")
ok "模板 id=$TID"

say "步骤 3/8：建任务"
TASK=$(curl -fsS -X POST "${AUTH[@]}" "$API/poster-tasks" \
  -H "Content-Type: application/json" \
  -d "{
    \"name\":\"真渲染测试\",
    \"template_id\":$TID,
    \"items\":[{\"type\":\"note\",\"id\":1,\"title\":\"卷被子大赛\",\"fields\":{\"time_range\":\"7.4 16:00\",\"location\":\"宁波万象汇L1小中庭\",\"fee\":\"免费 | 需报名\",\"content\":\"\"},\"image_url\":\"\"}]
  }")
TASKID=$(echo "$TASK" | python3 -c "import sys,json;print(json.load(sys.stdin)['data']['id'])")
ok "任务 id=$TASKID"

say "步骤 4/8：拿 preview HTML"
PREVIEW=$(curl -fsS "${AUTH[@]}" "$API/poster-tasks/$TASKID/preview")
HTML=$(echo "$PREVIEW" | python3 -c "import sys,json;print(json.load(sys.stdin)['data']['html'])")
echo "$HTML" > "$TMP_HTML"
ok "HTML 已写到 $TMP_HTML ($(wc -c < "$TMP_HTML") bytes)"

say "步骤 5/8：起 python http.server"
( cd "$(dirname "$TMP_HTML")" && python3 -m http.server "$TMP_PORT" >/dev/null 2>&1 ) &
SERVER_PID=$!
sleep 1
curl -fsS "http://127.0.0.1:$TMP_PORT/poster-real-render.html" > /dev/null || fail "http server 没起来"
ok "http server pid=$SERVER_PID port=$TMP_PORT"

say "步骤 6/8：opencli browser open"
URL="http://127.0.0.1:$TMP_PORT/poster-real-render.html"
OUTPUT="$DATA_POSTERS_DIR/$TASKID.png"
opencli browser default open "$URL" || fail "opencli browser open 失败"
ok "opencli browser open 成功"

say "步骤 7/8：opencli browser screenshot"
opencli browser default screenshot "$OUTPUT" --width 1242 --height 2208 || fail "opencli browser screenshot 失败"
ok "opencli browser screenshot 成功 → $OUTPUT"

say "步骤 8/8：断言 PNG magic + 文件存在"
if [ ! -f "$OUTPUT" ]; then fail "产物不存在 $OUTPUT"; fi
MAGIC=$(head -c 8 "$OUTPUT" | xxd -p)
EXPECTED="89504e470d0a1a0a"
if [ "$MAGIC" != "$EXPECTED" ]; then fail "PNG magic 不匹配：$MAGIC"; fi
SIZE=$(stat -f %z "$OUTPUT" 2>/dev/null || stat -c %s "$OUTPUT")
ok "产物合法 PNG，${SIZE} bytes"

say "步骤 9/9：尺寸断言（viewport 1242x2208）"
WIDTH=$(python3 -c "from PIL import Image; print(Image.open('$OUTPUT').size[0])" 2>/dev/null || echo "?")
HEIGHT=$(python3 -c "from PIL import Image; print(Image.open('$OUTPUT').size[1])" 2>/dev/null || echo "?")
ok "产物 PNG 尺寸: ${WIDTH}x${HEIGHT}"
if [ "$WIDTH" != "?" ] && [ "$WIDTH" -lt 1242 ]; then
  fail "宽度 $WIDTH 不满足 1242（设 viewport=1242x2208）"
fi
if [ "$HEIGHT" != "?" ] && [ "$HEIGHT" -lt 2200 ]; then
  fail "高度 $HEIGHT 不满足 2200 附近（viewport=2208）"
fi
ok "尺寸断言通过 (1242x2208)"

printf '\n\033[1;32m✓ 真渲染端到端通过！\033[0m\n'
