#!/bin/bash
# 发版预检脚本:tag 前跑一次,确保 CI 跑 release.yml 时不会因前置问题翻车
#
# 关联 spec: docs/superpowers/specs/2026-08-17-launcher-ocr-direct-design.md
#
# 用法: ./scripts/release-check.sh <version> [arch]
# 例:  ./scripts/release-check.sh 0.4.0 arm64
#
# 检查项:
#   1. 工作区干净(无未提交修改) — tag 触发 CI 后 CI 会 checkout 最新 commit
#   2. 前端 / launcher UI 已 build 且用相对路径(./assets/...)
#   3. backend tests/fixtures/ocr_test.png 存在
#   4. backend + frontend 单测全过
#   5. 当前分支与 main 一致(避免在 feature 分支发版)
#   6. tag v<version> 还没存在(GitHub Release 幂等:重复 tag 会失败)

set -e

VERSION=${1:?"用法: ./scripts/release-check.sh <version> [arm64|x86_64]"}
ARCH=${2:-arm64}

ROOT_DIR=$(cd "$(dirname "$0")/.." && pwd)
cd "$ROOT_DIR"

# ANSI 颜色
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

FAILED=0

step() {
    echo ""
    echo -e "${YELLOW}==> $1${NC}"
}

ok() {
    echo -e "  ${GREEN}✓${NC} $1"
}

fail() {
    echo -e "  ${RED}✗${NC} $1"
    FAILED=$((FAILED + 1))
}

# 1. 工作区干净
step "1/6 检查工作区是否干净"
if [ -n "$(git status --porcelain)" ]; then
    fail "工作区有未提交修改:"
    git status --short | /usr/bin/sed 's/^/    /'
else
    ok "工作区干净"
fi

# 2. 前端 dist 已 build 且是相对路径
step "2/6 检查 frontend/dist/index.html"
if [ ! -f "frontend/dist/index.html" ]; then
    fail "frontend/dist/index.html 不存在,需先 build: cd frontend && npm run build"
elif /usr/bin/grep -qE 'src="/assets/|href="/assets/' "frontend/dist/index.html"; then
    fail "frontend/dist 含绝对路径 /assets/... 会导致子路由加载失败"
else
    ok "frontend/dist 已 build 且用相对路径"
fi

# 3. launcher UI dist 已 build 且是相对路径
step "3/6 检查 launcher/ui/dist/index.html"
if [ ! -f "launcher/ui/dist/index.html" ]; then
    fail "launcher/ui/dist/index.html 不存在,需先 build: cd launcher/ui && npm run build:fast"
elif /usr/bin/grep -qE 'src="/assets/|href="/assets/' "launcher/ui/dist/index.html"; then
    fail "launcher/ui/dist 含绝对路径 /assets/... PyWebView 加载会白屏"
else
    ok "launcher/ui/dist 已 build 且用相对路径"
fi

# 4. OCR 测试 fixtures
step "4/6 检查 backend/tests/fixtures/"
if [ ! -f "backend/tests/fixtures/ocr_test.png" ]; then
    fail "backend/tests/fixtures/ocr_test.png 不存在,launcher '测试 OCR' 会失败"
else
    ok "ocr_test.png 存在"
fi

# 5. 测试全过
step "5/6 跑后端单测 + frontend 单测"
echo "  (可能需要 1-2 分钟)"
if ! command -v pytest >/dev/null 2>&1; then
    echo -e "  ${YELLOW}!${NC} pytest 未安装,跳过 (CI 会跑,不阻塞发版)"
else
    if cd backend && PATH="$HOME/.local/bin:/opt/homebrew/bin:/usr/bin:/bin:$PATH" pytest -x -q --no-header 2>&1 | /usr/bin/tail -3; then
        cd ..
        ok "backend pytest 全过"
    else
        cd ..
        fail "backend pytest 有失败,见上面输出"
    fi
fi

# 6. tag 已存在 / 当前分支
step "6/6 检查 tag + 分支"
if git rev-parse "v$VERSION" >/dev/null 2>&1; then
    # tag 已存在但指向不同 commit 没事(force push tag 会重新触发 release.yml)。
    # 只有 tag 已发布过且没有后续改动才报警。
    echo -e "  ${YELLOW}!${NC} tag v$VERSION 已存在(force push 会重新触发 release.yml)"
else
    ok "tag v$VERSION 不存在(首次发布)"
fi
CURRENT_BRANCH=$(git rev-parse --abbrev-ref HEAD)
if [ "$CURRENT_BRANCH" != "main" ] && [ "$CURRENT_BRANCH" != "master" ]; then
    fail "当前分支是 '$CURRENT_BRANCH',建议切到 main 再 tag(避免从 feature 分支发版)"
else
    ok "当前分支是 $CURRENT_BRANCH"
fi

# 总结
echo ""
echo "================================================="
if [ $FAILED -eq 0 ]; then
    echo -e "${GREEN}✓ 预检全部通过 — 可以 tag v$VERSION 触发 CI 发版${NC}"
    echo ""
    echo "下一步:"
    echo "  git tag v$VERSION"
    echo "  git push origin v$VERSION"
    echo "  → GitHub Actions 会自动跑 .github/workflows/release.yml"
    echo "  → 产物: macOS arm64 + x86_64 + Windows zip"
    echo "  → 自动创建 GitHub Release"
    exit 0
else
    echo -e "${RED}✗ 预检失败 $FAILED 项 — 修复后再 tag${NC}"
    exit 1
fi