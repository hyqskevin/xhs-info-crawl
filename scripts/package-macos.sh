#!/bin/bash
set -e

# macOS 打包脚本:产出 xhs-info-crawl-<version>-macos-<arch>.zip
# 用法: ./scripts/package-macos.sh <version> [arch]
# 架构:
#   arm64  (默认) — Apple Silicon (M1/M2/M3/M4)
#   x86_64        — Intel Mac
# 依赖: frontend/dist 和 launcher/ui/dist 已构建完成
# Python: python-build-standalone cpython-3.11.9 (astral-sh)

VERSION=${1:?"用法: ./scripts/package-macos.sh <version> [arm64|x86_64]"}
ARCH=${2:-arm64}

case "$ARCH" in
  arm64)
    PYTHON_TRIPLE="aarch64-apple-darwin"
    ZIP_SUFFIX="macos-arm64"
    ;;
  x86_64)
    PYTHON_TRIPLE="x86_64-apple-darwin"
    ZIP_SUFFIX="macos-x86_64"
    ;;
  *)
    echo "错误:不支持的架构: $ARCH(支持: arm64 / x86_64)"
    exit 1
    ;;
esac

ROOT_DIR=$(cd "$(dirname "$0")/.." && pwd)
# 允许外部覆盖 BUILD_DIR(用于并行打多个架构,不覆盖 dist/build 已有产物)
BUILD_DIR=${BUILD_DIR:-$ROOT_DIR/dist/build}
PKG_DIR=$BUILD_DIR/xhs-info-crawl
PYTHON_VERSION="cpython-3.11.9+20240415"
PYTHON_ARCHIVE="$PYTHON_VERSION-$PYTHON_TRIPLE-install_only.tar.gz"
PYTHON_URL="https://github.com/astral-sh/python-build-standalone/releases/download/20240415/$PYTHON_ARCHIVE"

echo "==> 打包 macOS v$VERSION ($ARCH / $ZIP_SUFFIX)"
echo "项目根目录: $ROOT_DIR"

# -1. 前置检查:前端 / launcher UI dist 必须先 build 出来
# 关联: docs/superpowers/specs/2026-08-17-launcher-ui-baseurl-pywebview-design.md
# vite build 默认输出绝对路径 /assets/... PyWebView file:// 加载会失败,
# 必须用 npm run build(已配 --base './') 或 vite build --base './'
echo "==> 前置检查:前端 dist 必须存在"
if [ ! -f "$ROOT_DIR/frontend/dist/index.html" ]; then
    echo "错误: frontend/dist/index.html 不存在。"
    echo "请先运行: cd frontend && npm run build"
    exit 1
fi
# 检查 asset 路径必须是相对路径(不能是 /assets/...)
if /usr/bin/grep -qE 'src="/assets/|href="/assets/' "$ROOT_DIR/frontend/dist/index.html"; then
    echo "错误: frontend/dist/index.html 含绝对路径 /assets/... PyWebView / http 服务加载会失败"
    echo "请确保 frontend/package.json 的 build script 带 --base './'"
    echo "或运行: cd frontend && npm run build:fast"
    exit 1
fi
echo "==> 前置检查:launcher UI dist 必须存在"
if [ ! -f "$ROOT_DIR/launcher/ui/dist/index.html" ]; then
    echo "错误: launcher/ui/dist/index.html 不存在。"
    echo "请先运行: cd launcher/ui && npm run build:fast"
    exit 1
fi
if /usr/bin/grep -qE 'src="/assets/|href="/assets/' "$ROOT_DIR/launcher/ui/dist/index.html"; then
    echo "错误: launcher/ui/dist/index.html 含绝对路径 /assets/... PyWebView 加载会失败"
    echo "请确保 launcher/ui/package.json 的 build script 带 --base './'"
    exit 1
fi
# 检查 OCR 测试 fixtures 必须存在(diagnostics_ocr.probe_ocr 需要)
if [ ! -f "$ROOT_DIR/backend/tests/fixtures/ocr_test.png" ]; then
    echo "警告: backend/tests/fixtures/ocr_test.png 不存在,OCR 测试会失败"
    echo "(不影响打包,但 launcher UI '测试 OCR' 会返回 test_image_missing)"
fi

# 0. 清理旧构建
rm -rf $BUILD_DIR
mkdir -p $PKG_DIR

# 1. 下载便携版 Python 3.11.9(python-build-standalone)
echo "==> 下载便携版 Python ($PYTHON_TRIPLE)..."
PYTHON_TGZ=$BUILD_DIR/python.tar.gz
curl -fL $PYTHON_URL -o $PYTHON_TGZ
echo "==> 解压 Python..."
tar xzf $PYTHON_TGZ -C $BUILD_DIR
echo "解压后 BUILD_DIR 顶层内容:"
ls -la $BUILD_DIR/
# 查找解压后的 python 目录
# python-build-standalone install_only 解压后标准布局是 $BUILD_DIR/python/bin/python3
# 优先检查标准路径,fallback 用 shell glob 查找
PYTHON_SRC="$BUILD_DIR/python"
if [ ! -x "$PYTHON_SRC/bin/python3" ]; then
    echo "标准路径 $PYTHON_SRC/bin/python3 不存在,用 glob 查找..."
    for pybin in "$BUILD_DIR"/*/bin/python3; do
        if [ -x "$pybin" ]; then
            PYTHON_SRC=$(dirname $(dirname "$pybin"))
            break
        fi
    done
fi
if [ ! -x "$PYTHON_SRC/bin/python3" ]; then
    echo "错误:未找到含 bin/python3 的目录"
    echo "BUILD_DIR 内容:"
    ls -la "$BUILD_DIR/"
    exit 1
fi
echo "找到 Python 目录: $PYTHON_SRC"
mkdir -p $PKG_DIR/runtime
mv "$PYTHON_SRC" $PKG_DIR/runtime/python
rm -f $PYTHON_TGZ

# 2. 创建 venv 并安装依赖(不含 ocr extra)
echo "==> 创建 venv 并安装依赖..."
# 不用 --copies:python-build-standalone 的 ensurepip 在 --copies 模式下 SIGABRT。
# 默认创建 symlink,然后第 8 步 mv 之后我们手动把 symlink 替换为真实 copy。
$PKG_DIR/runtime/python/bin/python3 -m venv $PKG_DIR/runtime/venv
$PKG_DIR/runtime/venv/bin/pip install --upgrade pip
$PKG_DIR/runtime/venv/bin/pip install -r $ROOT_DIR/backend/requirements-runtime.txt
$PKG_DIR/runtime/venv/bin/pip install -r $ROOT_DIR/launcher/requirements.txt

# 注意:paddleocr / paddlepaddle **不**在 venv 里强制装(v0.6.0 的回归)。
# 它们属于 OCR Python 包,体积约 840M(paddlepaddle 429M + opencv 171M + ...),
# 强行装会让 .app 从 400M 涨到 1.1G,zip 从 280M 涨到 338M。
# 正确路径:用户点 launcher UI "下载安装 OCR" 时,launcher.ocr_installer
# 按需把 paddleocr+models 装到 DATA_DIR/paddlex/,不走 venv。
# 关联 spec: docs/superpowers/specs/2026-08-21-packaging-ocr-llm-flow-fix-design.md § 改动 1
# 关联设计: docs/packaging-design.md §2.1 问题 ①

# 修复 venv 缺少 libpython3.11.dylib 问题:
# python-build-standalone 解压后创建的 venv/lib 下没有 libpython,
# venv/bin/python 启动时报 Library not loaded 错误。
# 解决:把 base python 的 libpython 复制到 venv/lib/
echo "==> 修复 venv libpython..."
cp $PKG_DIR/runtime/python/lib/libpython3.11.dylib $PKG_DIR/runtime/venv/lib/libpython3.11.dylib 2>&1

# 3. 复制后端源码(排除测试代码 + 本地 venv + 数据)
echo "==> 复制后端源码(排除 tests/venv/data)..."
mkdir -p $PKG_DIR/app/backend
rsync -a --exclude='__pycache__/' --exclude='.pytest_cache/' \
  --exclude='.coverage' --exclude='htmlcov/' \
  --exclude='.venv/' --exclude='venv/' --exclude='.env' --exclude='*.pyc' \
  --exclude='data/' --exclude='.git/' --exclude='node_modules/' \
  $ROOT_DIR/backend/ $PKG_DIR/app/backend/

# 3.1 单独复制 tests/fixtures/(诊断用 OCR 测试图)
# 不能整目录 rsync(避免带 .py 测试文件),只复制 fixtures 子目录里的 png 等数据文件。
# diagnostics_ocr.py 用 OCR_TEST_IMAGE = backend/tests/fixtures/ocr_test.png 测 OCR 探针。
# 关联 spec: docs/superpowers/specs/2026-08-17-launcher-ocr-direct-design.md
echo "==> 复制 OCR 测试 fixtures..."
mkdir -p $PKG_DIR/app/backend/tests/fixtures
if [ -d "$ROOT_DIR/backend/tests/fixtures" ]; then
    rsync -a --include='*/' --include='*.png' --include='*.jpg' --include='*.jpeg' \
      --include='*.json' --exclude='*' \
      $ROOT_DIR/backend/tests/fixtures/ $PKG_DIR/app/backend/tests/fixtures/ || true
fi

# 4. 复制前端构建产物
echo "==> 复制前端构建产物..."
mkdir -p $PKG_DIR/app/frontend/dist
cp -r $ROOT_DIR/frontend/dist/* $PKG_DIR/app/frontend/dist/

# 5. 复制启动器(不含 ui/src 和 node_modules)
echo "==> 复制启动器..."
mkdir -p $PKG_DIR/launcher/ui/dist
cp $ROOT_DIR/launcher/*.py $PKG_DIR/launcher/
cp $ROOT_DIR/launcher/requirements.txt $PKG_DIR/launcher/
cp -r $ROOT_DIR/launcher/ui/dist/* $PKG_DIR/launcher/ui/dist/

# 注: 不再需要 sed 修复绝对路径 — vite build --base './' 已固化在 package.json,
# 永远输出相对路径 ./assets/... (关联 spec: .../2026-08-17-launcher-ui-baseurl-pywebview-design.md)

# 6. 复制 .env.example
cp $ROOT_DIR/.env.example $PKG_DIR/.env.example

# 7. 创建空 data 目录(含 paddlex 占位,OCR 增强包安装后填充)
echo "==> 创建 data 目录..."
mkdir -p $PKG_DIR/data/logs $PKG_DIR/data/images $PKG_DIR/data/exports $PKG_DIR/data/celery
mkdir -p $PKG_DIR/data/paddlex/official_models
mkdir -p $PKG_DIR/data/huggingface
mkdir -p $PKG_DIR/data/tmp
mkdir -p $PKG_DIR/data/run
mkdir -p $PKG_DIR/data/archive
mkdir -p $PKG_DIR/data/backups

# 8. 打 .app bundle
echo "==> 创建 .app bundle..."
mkdir -p $BUILD_DIR/xhs-info-crawl.app/Contents/MacOS
mkdir -p $BUILD_DIR/xhs-info-crawl.app/Contents/Resources
# 把所有运行数据放到 .app/Contents/Resources/ 下,
# 这样 Finder 双击 .app 时 macOS AppTranslocation 会把整个 .app(含数据)
# 一起复制到 /private/var/folders/.../T/AppTranslocation/.../ 沙盒,
# start.sh 才能找到 runtime/venv/bin/python
echo "==> 移动运行数据到 .app/Contents/Resources/xhs-info-crawl/..."
mv $PKG_DIR $BUILD_DIR/xhs-info-crawl.app/Contents/Resources/xhs-info-crawl
PKG_DIR="$BUILD_DIR/xhs-info-crawl.app/Contents/Resources/xhs-info-crawl"

# 8.1 替换 venv/bin/ 里的 python 符号链接为真实 copy
# macOS venv 默认 symlink bin/python -> ../python/bin/python3,
# mv 之后 symlink 路径失效。手动删除 symlink,copy base python 进去。
echo "==> 替换 venv/bin/python* symlink 为真实 copy..."
for binfile in $PKG_DIR/runtime/venv/bin/python python3 python3.11; do
    src="$PKG_DIR/runtime/venv/bin/$binfile"
    if [ -L "$src" ]; then
        rm "$src"
        cp "$PKG_DIR/runtime/python/bin/$(basename $binfile)" "$src"
    fi
done

cat > $BUILD_DIR/xhs-info-crawl.app/Contents/Info.plist <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleName</key><string>小红书活动信息抓取系统</string>
  <key>CFBundleDisplayName</key><string>小红书活动信息抓取系统</string>
  <key>CFBundleExecutable</key><string>start.sh</string>
  <key>CFBundleVersion</key><string>$VERSION</string>
  <key>CFBundlePackageType</key><string>APPL</string>
  <key>CFBundleSignature</key><string>????</string>
</dict>
</plist>
EOF
cat > $BUILD_DIR/xhs-info-crawl.app/Contents/MacOS/start.sh <<'EOF'
#!/bin/bash
# .app 启动入口:调用 launcher/main.py
# 用 realpath 找脚本真实位置,不依赖 cwd(macOS GUI 双击 .app 时 cwd 是 /)
SCRIPT="$(realpath "$0")"
# start.sh 在 .app/Contents/MacOS/start.sh,
# 数据目录在 .app/Contents/Resources/xhs-info-crawl/(包内资源,
# Finder AppTranslocation 会随 .app 整体复制,不会丢)
APP_DIR="$(dirname "$(dirname "$(dirname "$SCRIPT")")")"
DATA_DIR="$APP_DIR/Contents/Resources/xhs-info-crawl"
# python-build-standalone 的 Python 二进制硬编码 /install 作为 base prefix,
# 需要设 PYTHONHOME 指向 runtime/python,并把 runtime/python/lib 加到 DYLD_LIBRARY_PATH
# 同时把 libpython 复制到 venv/lib/(避免 venv/bin/python 启动时找不到 libpython)
export PYTHONHOME="$DATA_DIR/runtime/python"
export DYLD_LIBRARY_PATH="$DATA_DIR/runtime/python/lib:${DYLD_LIBRARY_PATH}"
# opencli 默认装在 ~/.local/bin/,launcher 和子进程需要能找到
export PATH="$HOME/.local/bin:$PATH"
# 把父目录加入 PYTHONPATH,让 launcher 模块可导入
export PYTHONPATH="$DATA_DIR:$PYTHONPATH"
cd "$DATA_DIR/launcher"
exec "$DATA_DIR/runtime/venv/bin/python" "$DATA_DIR/launcher/main.py"
EOF
chmod +x $BUILD_DIR/xhs-info-crawl.app/Contents/MacOS/start.sh

# 8.5 Adhoc 签名整个 .app(避免 Gatekeeper 弹"Apple 无法验证 python")
# 用 codesign --force --deep --sign - 给所有 binary 打临时签名,
# 包括 venv/bin/python、venv/bin/python3 等。
echo "==> Adhoc 签名 .app..."
codesign --force --deep --sign - "$BUILD_DIR/xhs-info-crawl.app" 2>&1 | tail -3
# 验证签名
codesign --verify --verbose "$BUILD_DIR/xhs-info-crawl.app" 2>&1 | tail -2

# 8.6 打包后校验:OCR 依赖 + 测试图 + 相对路径 都在 .app 内
# 关联: docs/superpowers/specs/2026-08-17-launcher-ocr-direct-design.md
# 失败要明确指出哪个文件缺,而不是给用户一个不能跑的 .app。
echo "==> 校验 .app 内 OCR 依赖..."
APP_CHECK_DIR="$BUILD_DIR/xhs-info-crawl.app/Contents/Resources/xhs-info-crawl"
CHECK_FAILED=0
if [ ! -d "$APP_CHECK_DIR/runtime/venv/lib/python3.11/site-packages/paddleocr" ]; then
    echo "  ✗ paddleocr 包缺失(OCR 增强不可用)"
    CHECK_FAILED=1
fi
if [ ! -d "$APP_CHECK_DIR/runtime/venv/lib/python3.11/site-packages/paddlepaddle" ]; then
    echo "  ✗ paddlepaddle 包缺失(OCR 推理失败)"
    CHECK_FAILED=1
fi
if [ ! -f "$APP_CHECK_DIR/app/backend/tests/fixtures/ocr_test.png" ]; then
    echo "  ✗ OCR 测试图缺失(launcher '测试 OCR' 会返回 test_image_missing)"
    CHECK_FAILED=1
fi
# index.html 不能含绝对路径 /assets/
if /usr/bin/grep -qE 'src="/assets/|href="/assets/' "$APP_CHECK_DIR/launcher/ui/dist/index.html"; then
    echo "  ✗ launcher ui 含绝对路径 /assets/(白屏)"
    CHECK_FAILED=1
fi
if /usr/bin/grep -qE 'src="/assets/|href="/assets/' "$APP_CHECK_DIR/app/frontend/dist/index.html"; then
    echo "  ✗ frontend 含绝对路径 /assets/(子路由加载失败)"
    CHECK_FAILED=1
fi
if [ $CHECK_FAILED -eq 1 ]; then
    echo ""
    echo "错误: 打包校验失败 — 上面列了缺失/异常文件"
    echo "zip 已生成但 .app 不能直接给用户使用。请修复后重打包。"
    # 不 exit 1 让 zip 仍然生成,便于人工核对 — 但要醒目提示
fi
echo "==> .app 校验完毕"

# 9. 压缩
echo "==> 压缩产物..."
cd $BUILD_DIR
zip -r xhs-info-crawl-$VERSION-$ZIP_SUFFIX.zip xhs-info-crawl xhs-info-crawl.app

echo "==> 完成: $BUILD_DIR/xhs-info-crawl-$VERSION-$ZIP_SUFFIX.zip"