#!/usr/bin/env bash
# tests/scripts/test_poster_generation.sh
# 一键回放海报生成系统的 E2E 流程。
#
# 关联：tests/poster-generation.md
# 用法：
#   ADMIN_USERNAME=admin ADMIN_PASSWORD='Admin@123' \
#   BASE_URL=http://127.0.0.1:8000 \
#   bash tests/scripts/test_poster_generation.sh

set -euo pipefail

BASE_URL="${BASE_URL:-http://127.0.0.1:8000}"
ADMIN_USERNAME="${ADMIN_USERNAME:-admin}"
ADMIN_PASSWORD="${ADMIN_PASSWORD:-Admin@123}"
API="$BASE_URL/api/v1"

# 期望时附加 IMAGE_PATH=sample.jpg 测试 AI 识别场景（可选）
# IMAGE_PATH="${IMAGE_PATH:-}"

say() { printf '\n\033[1;36m▶ %s\033[0m\n' "$*"; }
ok() { printf '\033[1;32m✓\033[0m %s\n' "$*"; }
fail() { printf '\033[1;31m✗\033[0m %s\n' "$*"; exit 1; }

assert_eq() {
  local lhs="$1" rhs="$2" msg="$3"
  if [[ "$lhs" != "$rhs" ]]; then
    fail "$msg：期望 '$rhs' 实得 '$lhs'"
  fi
  ok "$msg"
}

assert_contains() {
  local haystack="$1" needle="$2" msg="$3"
  if [[ "$haystack" != *"$needle"* ]]; then
    fail "$msg：期望包含 '$needle'"
  fi
  ok "$msg"
}

# ----- 1. 登录拿 token -----
say "步骤：登录拿 admin token"
LOGIN_RESP=$(curl -fsS -X POST "$API/auth/login" \
  -H "Content-Type: application/json" \
  -d "{\"username\":\"$ADMIN_USERNAME\",\"password\":\"$ADMIN_PASSWORD\"}")
TOKEN=$(echo "$LOGIN_RESP" | python3 -c "import sys,json;print(json.load(sys.stdin)['data']['access_token'])")
[[ -n "$TOKEN" ]] || fail "无法取得 access_token"
ok "登录成功 token 长度 ${#TOKEN}"

AUTH=( -H "Authorization: Bearer $TOKEN" )

# ----- 2. 列出模板 -----
say "场景 1.1 GET /settings/poster-templates"
curl -fsS "${AUTH[@]}" "$API/settings/poster-templates" \
  | python3 -m json.tool > /tmp/poster_templates.json
ok "返回 JSON"

# ----- 3. 手动创建模板 -----
say "场景 1.2 POST /settings/poster-templates"
NAME="橙色周末合集-$(date +%s)"
CRT=$(curl -fsS -X POST "${AUTH[@]}" "$API/settings/poster-templates" \
  -H "Content-Type: application/json" \
  -d "{
    \"name\":\"$NAME\",
    \"description\":\"自动化脚本创建\",
    \"html_template\":\"<div class=\\\"poster\\\"><h1>{{title}}</h1>{{items}}</div>\",
    \"css_text\":\".poster{background:#F26B2C;width:1242px;color:#fff;font-family:sans-serif;padding:60px}\"
  }")
TID=$(echo "$CRT" | python3 -c "import sys,json;print(json.load(sys.stdin)['data']['id'])")
[[ -n "$TID" ]] || fail "模板 ID 为空"
ok "新建模板 id=$TID"

# ----- 4. 重名拒绝 -----
say "场景 1.3 重名 POST 拒绝"
CODE=$(curl -s -o /tmp/dup.json -w "%{http_code}" -X POST "${AUTH[@]}" \
  "$API/settings/poster-templates" -H "Content-Type: application/json" \
  -d "{\"name\":\"$NAME\",\"html_template\":\"<x/>\"}")
if [[ "$CODE" != "409" && "$CODE" != "422" ]]; then
  fail "重名 POST 期望 409/422 实得 $CODE"
fi
ok "重名 POST 拒绝（$CODE）"

# ----- 5. 编辑模板 -----
say "场景 1.4 PUT 模板 css_text"
curl -fsS -X PUT "${AUTH[@]}" "$API/settings/poster-templates/$TID" \
  -H "Content-Type: application/json" \
  -d '{"css_text":".poster{background:#F26B2C;padding:60px;color:#222}"}' > /dev/null
ok "PUT 模板成功"

# ----- 6. 删除模板 -----
say "场景 1.4 DELETE 模板"
curl -fsS -X DELETE "${AUTH[@]}" "$API/settings/poster-templates/$TID" > /dev/null
ok "DELETE 模板成功"

# ----- 7. 候选对象 -----
say "场景 2.4 GET /poster-tasks/candidates"
CAND=$(curl -fsS "${AUTH[@]}" "$API/poster-tasks/candidates?page_size=5")
COUNT=$(echo "$CAND" | python3 -c "import sys,json;print(len(json.load(sys.stdin)['data']['items']))")
ok "候选 items 长度 $COUNT（≤ 50 即合格）"
if (( COUNT > 50 )); then fail "候选条目过多"; fi

# ----- 8. 创建 draft 任务（推文粒度） -----
say "场景 2.1 POST /poster-tasks 推文粒度"
# 注：若实际库为空，可能 items 为空数组。脚本不强制要求有数据。
ITEM_NOTE='{"type":"note","id":1,"title":"示例推文","fields":{"time_range":"7.4 16:00","location":"示例地点","fee":"免费","content":""},"image_url":""}'
ITEMS_JSON="[$ITEM_NOTE]"
# 需要一个有效 template —— 我们刚刚删了。再建一个短期模板用于任务
NM2="tmp-$(date +%s)"
NT=$(curl -fsS -X POST "${AUTH[@]}" "$API/settings/poster-templates" \
  -H "Content-Type: application/json" \
  -d "{\"name\":\"$NM2\",\"html_template\":\"<div>{{items}}</div>\"}")
NTID=$(echo "$NT" | python3 -c "import sys,json;print(json.load(sys.stdin)['data']['id'])")
ok "为任务新建短期模板 id=$NTID"

# 创建任务
TASK=$(curl -fsS -X POST "${AUTH[@]}" "$API/poster-tasks" \
  -H "Content-Type: application/json" \
  -d "{
    \"name\":\"E2E-自动化任务\",
    \"template_id\":$NTID,
    \"items\":$ITEMS_JSON
  }")
TASK_ID=$(echo "$TASK" | python3 -c "import sys,json;print(json.load(sys.stdin)['data']['id'])")
ok "建任务成功 id=$TASK_ID"

# ----- 9. 更新任务 -----
say "场景 2.3 PUT /poster-tasks/{id} 修改 override_html"
curl -fsS -X PUT "${AUTH[@]}" "$API/poster-tasks/$TASK_ID" \
  -H "Content-Type: application/json" \
  -d '{"override_html":"<div>手改内容</div>"}' > /dev/null
ok "任务已更新"

# ----- 10. 预览 -----
say "场景 2.6 GET /poster-tasks/{id}/preview"
PREVIEW=$(curl -fsS "${AUTH[@]}" "$API/poster-tasks/$TASK_ID/preview")
HTML=$(echo "$PREVIEW" | python3 -c "import sys,json;print(json.load(sys.stdin)['data']['html'])")
assert_contains "$HTML" "<" "预览含 HTML 标签"
assert_contains "$HTML" "示例推文" "预览含 items 渲染"

# ----- 11. 推文图片列表 -----
say "场景 2.5 GET /posters/note-images/{note_id}"
NOTE_IMAGES=$(curl -s -o /tmp/note_imgs.json -w "%{http_code}" "${AUTH[@]}" "$API/posters/note-images/1")
# 期望 200（即使 note 1 无图也返空数组）
if [[ "$NOTE_IMAGES" != "200" ]]; then
  fail "GET /posters/note-images/1 期望 200 实得 $NOTE_IMAGES"
fi
ok "推文图片列表端点返回 200"

# ----- 12. 清理 -----
say "步骤：清理"
curl -fsS -X DELETE "${AUTH[@]}" "$API/poster-tasks/$TASK_ID" > /dev/null
curl -fsS -X DELETE "${AUTH[@]}" "$API/settings/poster-templates/$NTID" > /dev/null
ok "已清理临时资源"

printf '\n\033[1;32m所有自动化场景通过！\033[0m\n'
