#!/usr/bin/env bash
# 多 item 场景验证。
#
# 一次性建 1 个海报模板 + 3 个 item 的任务，
# 启动 http.server + opencli 真渲染并截 PNG。
# 验证成品中是否能看到 3 个 row 卡片（橙色 banner）。

set -euo pipefail
BASE_URL="${BASE_URL:-http://127.0.0.1:8000}"
ADMIN_USERNAME="${ADMIN_USERNAME:-admin}"
ADMIN_PASSWORD="${ADMIN_PASSWORD:-Admin@123}"
API="$BASE_URL/api/v1"

TOKEN=$(curl -fsS -X POST "$API/auth/login" -H "Content-Type: application/json" \
  -d "{\"username\":\"$ADMIN_USERNAME\",\"password\":\"$ADMIN_PASSWORD\"}" \
  | python3 -c 'import sys,json;print(json.load(sys.stdin)["data"]["access_token"])')
AUTH=( -H "Authorization: Bearer $TOKEN" )

NAME="multi-render-$(date +%s)"

# 1. 模板（沿用真渲染脚本的 html）
TPL=$(curl -fsS -X POST "${AUTH[@]}" "$API/settings/poster-templates" \
  -H "Content-Type: application/json" \
  -d "{\"name\":\"$NAME\",\"html_template\":\"<div class='poster'>{{items}}</div>\",\"css_text\":\"\"}")
TID=$(echo "$TPL" | python3 -c 'import sys,json;print(json.load(sys.stdin)["data"]["id"])')

# 2. 3 item 任务
TASK=$(curl -fsS -X POST "${AUTH[@]}" "$API/poster-tasks" \
  -H "Content-Type: application/json" \
  -d "{
    \"name\":\"宁波周末三个活动\",
    \"template_id\":$TID,
    \"items\":[
      {\"type\":\"note\",\"id\":1,\"title\":\"卷被子大赛\",
       \"fields\":{\"time_range\":\"7.4 16:00-17:00\",\"location\":\"宁波万象汇L1小中庭\",\"fee\":\"免费 | 需报名\",\"content\":\"\"},
       \"image_url\":\"\"},
      {\"type\":\"note\",\"id\":2,\"title\":\"少儿绘本共读\",
       \"fields\":{\"time_range\":\"7.5 10:00-11:30\",\"location\":\"宁波图书馆\",\"fee\":\"免费\",\"content\":\"\"},
       \"image_url\":\"\"},
      {\"type\":\"note\",\"id\":3,\"title\":\"户外帐篷节\",
       \"fields\":{\"time_range\":\"7.6 14:00-17:00\",\"location\":\"东钱湖水上乐园\",\"fee\":\"68元起\",\"content\":\"带防晒霜\"},
       \"image_url\":\"\"}
    ]
  }")
TASK_ID=$(echo "$TASK" | python3 -c 'import sys,json;print(json.load(sys.stdin)["data"]["id"])')

# 3. preview HTML
HTML=$(curl -fsS "${AUTH[@]}" "$API/poster-tasks/$TASK_ID/preview" \
  | python3 -c 'import sys,json;print(json.load(sys.stdin)["data"]["html"])')
echo "$HTML" > /tmp/multi-render.html

# 4. http server
PORT=8988
( cd /tmp && python3 -m http.server "$PORT" >/dev/null 2>&1 ) &
SERVER_PID=$!
trap "kill $SERVER_PID 2>/dev/null || true" EXIT
sleep 1

OUT="data/posters/${TASK_ID}.png"

# 5. opencli open + screenshot
opencli browser default open "http://127.0.0.1:$PORT/multi-render.html" >/dev/null
opencli browser default screenshot "$OUT" --width 1242 --height 2208 >/dev/null

# 6. 验证
python3 - <<EOF
from PIL import Image
img = Image.open("$OUT")
w, h = img.size
print(f"PNG: {w}x{h}")
assert w == 1242, f"width != 1242 ({w})"
assert h == 2208, f"height != 2208 ({h})"
# 抽 6 个不同 y 看是否含橙
orange = (242, 107, 44)
hits = []
for y in range(0, h, 50):
    if img.getpixel((150, y)) == orange:
        hits.append(y)
print(f"row-banner hits at x=150: {len(hits)} samples; e.g. {hits[:6]}")
# 期望 hits 至少 ≥ 2 处（上下不同 row），证明多 row 分布
assert len(set(h // 100 for h in hits)) >= 2, f"期望 ≥ 2 个不同 row 区块，实际只显示 {len(set(h // 100 for h in hits))}"
print("PASS: 真渲染多 row 可见")
EOF
