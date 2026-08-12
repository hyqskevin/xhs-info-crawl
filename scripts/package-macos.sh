#!/bin/bash
set -e

# macOS 打包脚本:产出 xhs-info-crawl-<version>-macos.zip
# 用法: ./scripts/package-macos.sh <version>
# 依赖: frontend/dist 和 launcher/ui/dist 已构建完成
# Python: python-build-standalone cpython-3.11.9 (astral-sh)

VERSION=${1:?"用法: ./scripts/package-macos.sh <version>"}
ROOT_DIR=$(cd "$(dirname "$0")/.." && pwd)
BUILD_DIR=$ROOT_DIR/dist/build
PKG_DIR=$BUILD_DIR/xhs-info-crawl
# python-build-standalone 用 triple 命名: aarch64-apple-darwin (不是 darwin-arm64)
PYTHON_VERSION="cpython-3.11.9+20240415"
PYTHON_ARCHIVE="$PYTHON_VERSION-aarch64-apple-darwin-install_only.tar.gz"
PYTHON_URL="https://github.com/astral-sh/python-build-standalone/releases/download/20240415/$PYTHON_ARCHIVE"

echo "==> 打包 macOS v$VERSION"
echo "项目根目录: $ROOT_DIR"

# 0. 清理旧构建
rm -rf $BUILD_DIR
mkdir -p $PKG_DIR

# 1. 下载便携版 Python 3.11.9(python-build-standalone)
echo "==> 下载便携版 Python..."
PYTHON_TGZ=$BUILD_DIR/python.tar.gz
curl -fL $PYTHON_URL -o $PYTHON_TGZ
echo "==> 解压 Python..."
tar xzf $PYTHON_TGZ -C $BUILD_DIR
echo "解压后 BUILD_DIR 顶层内容:"
ls -la $BUILD_DIR/
# 查找解压后的 python 目录(含 bin/python3),不假设目录名
PYTHON_SRC=$(find $BUILD_DIR -maxdepth 3 -name "python3" -path "*/bin/*" -type f 2>/dev/null -exec dirname {} \; -quit | xargs dirname 2>/dev/null)
if [ -z "$PYTHON_SRC" ]; then
    echo "错误:解压后未找到含 bin/python3 的目录"
    echo "find 结果:"
    find $BUILD_DIR -maxdepth 3 -name "python3*" 2>/dev/null | head -10
    exit 1
fi
mkdir -p $PKG_DIR/runtime
mv $PYTHON_SRC $PKG_DIR/runtime/python
rm -f $PYTHON_TGZ

# 2. 创建 venv 并安装依赖(不含 ocr extra)
echo "==> 创建 venv 并安装依赖..."
$PKG_DIR/runtime/python/bin/python3 -m venv $PKG_DIR/runtime/venv
$PKG_DIR/runtime/venv/bin/pip install --upgrade pip
$PKG_DIR/runtime/venv/bin/pip install -r $ROOT_DIR/backend/requirements-runtime.txt
$PKG_DIR/runtime/venv/bin/pip install -r $ROOT_DIR/launcher/requirements.txt

# 3. 复制后端源码
echo "==> 复制后端源码..."
cp -r $ROOT_DIR/backend $PKG_DIR/app/backend

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
DIR="$(dirname "$(dirname "$(dirname "$0")")")"
exec "$DIR/xhs-info-crawl/runtime/venv/bin/python" "$DIR/xhs-info-crawl/launcher/main.py"
EOF
chmod +x $BUILD_DIR/xhs-info-crawl.app/Contents/MacOS/start.sh

# 9. 压缩
echo "==> 压缩产物..."
cd $BUILD_DIR
zip -r xhs-info-crawl-$VERSION-macos.zip xhs-info-crawl xhs-info-crawl.app

echo "==> 完成: $BUILD_DIR/xhs-info-crawl-$VERSION-macos.zip"
