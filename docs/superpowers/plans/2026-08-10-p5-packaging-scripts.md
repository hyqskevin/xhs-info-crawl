# P5 打包脚本 + GitHub Actions Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现主程序和 OCR 增强包的打包脚本与 GitHub Actions 工作流,推送 tag 时自动构建并发布 macOS/Windows 用户包、源码 zip 和 OCR 增强包。

**Architecture:** 两个独立的 GitHub Actions 工作流(主程序 release.yml + OCR 增强包 release-ocr-addon.yml),各自调用平台特定的打包脚本(scripts/package-macos.sh / scripts/package-windows.ps1 / scripts/package-ocr-addon.sh)。打包脚本下载便携版 Python、创建 venv、复制源码与构建产物、压缩成 zip。本地用 dry-run 模式验证脚本结构,CI 上跑真实构建。

**Tech Stack:** Bash + PowerShell + GitHub Actions YAML + python-build-standalone + pip

**Spec:** `docs/superpowers/specs/2026-08-10-one-click-packaging-design.md` § 6.1-6.7

---

## 文件结构

```
.
├── .github/
│   └── workflows/
│       ├── ci.yml                          # 已存在,不改动
│       ├── release.yml                     # 新建:主程序发布工作流
│       └── release-ocr-addon.yml           # 新建:OCR 增强包发布工作流
├── .gitattributes                          # 新建:源码 zip 排除规则
├── backend/
│   └── requirements-runtime.txt            # 新建:从 pyproject.toml 提取的运行时依赖(不含 ocr extra)
├── launcher/
│   └── requirements.txt                    # 新建:启动器 Python 依赖(pywebview/fastapi/httpx)
├── scripts/
│   ├── package-macos.sh                    # 新建:macOS 打包脚本
│   ├── package-windows.ps1                 # 新建:Windows 打包脚本
│   └── package-ocr-addon.sh                # 新建:OCR 增强包打包脚本
└── tests/
    └── scripts/
        └── test_packaging_scripts.py       # 新建:打包脚本结构验证测试
```

---

## 执行策略

6 个任务,按依赖顺序执行:

- **Task 1**: 依赖清单文件(backend/requirements-runtime.txt + launcher/requirements.txt)
- **Task 2**: .gitattributes 源码 zip 排除规则
- **Task 3**: macOS 打包脚本 scripts/package-macos.sh
- **Task 4**: Windows 打包脚本 scripts/package-windows.ps1
- **Task 5**: OCR 增强包打包脚本 scripts/package-ocr-addon.sh
- **Task 6**: GitHub Actions 工作流(release.yml + release-ocr-addon.yml)

每个任务用 TDD:先写测试看到失败,再实现看到通过。测试用 Python 验证脚本结构和文件内容,不实际执行打包(需 GitHub Actions runner)。

---

## Task 1: 依赖清单文件

**Files:**
- Create: `backend/requirements-runtime.txt`
- Create: `launcher/requirements.txt`
- Create: `tests/scripts/test_packaging_scripts.py`

**说明:**
- `backend/requirements-runtime.txt` 从 `backend/pyproject.toml` 的 `[project.dependencies]` 提取(不含 ocr extra),供打包脚本 `pip install -r` 使用
- `launcher/requirements.txt` 包含启动器 Python 依赖:pywebview、fastapi、httpx(启动器独立于后端,自己 import 这些)

- [ ] **Step 1: 创建测试 tests/scripts/test_packaging_scripts.py**

```python
"""打包脚本与发布工作流结构验证。

不实际执行打包(需要 GitHub Actions runner),只验证:
- 依赖清单文件存在且内容正确
- 打包脚本存在且结构正确(shebang、关键步骤)
- GitHub Actions 工作流存在且 job 结构正确
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
BACKEND_REQ = ROOT / "backend" / "requirements-runtime.txt"
LAUNCHER_REQ = ROOT / "launcher" / "requirements.txt"
SCRIPTS_DIR = ROOT / "scripts"
WORKFLOWS_DIR = ROOT / ".github" / "workflows"


class TestRequirementsFiles:
    """依赖清单文件结构验证。"""

    def test_backend_requirements_runtime_exists(self):
        assert BACKEND_REQ.exists(), f"缺少 {BACKEND_REQ}"

    def test_backend_requirements_runtime_contains_fastapi(self):
        content = BACKEND_REQ.read_text(encoding="utf-8")
        assert "fastapi" in content.lower()

    def test_backend_requirements_runtime_contains_celery(self):
        content = BACKEND_REQ.read_text(encoding="utf-8")
        assert "celery" in content.lower()

    def test_backend_requirements_runtime_excludes_paddleocr(self):
        """运行时依赖不含 ocr extra(paddleocr 走 OCR 增强包)。"""
        content = BACKEND_REQ.read_text(encoding="utf-8")
        assert "paddleocr" not in content.lower()
        assert "paddlepaddle" not in content.lower()

    def test_launcher_requirements_exists(self):
        assert LAUNCHER_REQ.exists(), f"缺少 {LAUNCHER_REQ}"

    def test_launcher_requirements_contains_pywebview(self):
        content = LAUNCHER_REQ.read_text(encoding="utf-8")
        assert "pywebview" in content.lower()

    def test_launcher_requirements_contains_fastapi(self):
        content = LAUNCHER_REQ.read_text(encoding="utf-8")
        assert "fastapi" in content.lower()

    def test_launcher_requirements_contains_httpx(self):
        content = LAUNCHER_REQ.read_text(encoding="utf-8")
        assert "httpx" in content.lower()
```

- [ ] **Step 2: 运行测试看到失败**

Run: `cd backend && pytest tests/scripts/test_packaging_scripts.py::TestRequirementsFiles -v`
Expected: FAIL (文件不存在)

- [ ] **Step 3: 创建 backend/requirements-runtime.txt**

从 `backend/pyproject.toml` 的 `[project.dependencies]` 提取(去掉版本约束的引号,保持 pip 格式):

```text
# 后端运行时依赖(不含 ocr extra,OCR 走增强包)
# 从 pyproject.toml [project.dependencies] 提取
alembic>=1.14,<2
celery>=5.4,<6
fastapi>=0.115,<1
httpx>=0.28,<1
openpyxl>=3.1,<4
pwdlib[argon2]>=0.2,<1
pyjwt>=2.10,<3
pydantic-settings>=2.7,<3
sqlalchemy>=2.0,<3
uvicorn[standard]>=0.34,<1
```

- [ ] **Step 4: 创建 launcher/requirements.txt**

```text
# 启动器 Python 依赖(独立于后端)
pywebview>=5.3,<6
fastapi>=0.115,<1
httpx>=0.28,<1
```

- [ ] **Step 5: 运行测试看到通过**

Run: `cd backend && pytest tests/scripts/test_packaging_scripts.py::TestRequirementsFiles -v`
Expected: 8 tests passed

- [ ] **Step 6: Commit**

```bash
git add backend/requirements-runtime.txt launcher/requirements.txt tests/scripts/test_packaging_scripts.py
git commit -m "feat(packaging): add runtime requirements files for backend and launcher"
```

---

## Task 2: .gitattributes 源码 zip 排除规则

**Files:**
- Create: `.gitattributes`
- Modify: `tests/scripts/test_packaging_scripts.py` (追加 TestGitAttributes 类)

**说明:** `git archive` 打源码 zip 时排除开发产物(.venv、node_modules、data 等)。

- [ ] **Step 1: 追加测试到 tests/scripts/test_packaging_scripts.py**

在文件末尾追加:

```python
class TestGitAttributes:
    """源码 zip 排除规则验证。"""

    def test_gitattributes_exists(self):
        assert (ROOT / ".gitattributes").exists()

    def test_gitattributes_excludes_venv(self):
        content = (ROOT / ".gitattributes").read_text(encoding="utf-8")
        assert ".venv/" in content
        assert "export-ignore" in content

    def test_gitattributes_excludes_node_modules(self):
        content = (ROOT / ".gitattributes").read_text(encoding="utf-8")
        assert "node_modules/" in content

    def test_gitattributes_excludes_data_db(self):
        content = (ROOT / ".gitattributes").read_text(encoding="utf-8")
        assert "data/" in content or "*.db" in content

    def test_gitattributes_excludes_dist(self):
        content = (ROOT / ".gitattributes").read_text(encoding="utf-8")
        assert "dist/" in content
```

- [ ] **Step 2: 运行测试看到失败**

Run: `cd backend && pytest tests/scripts/test_packaging_scripts.py::TestGitAttributes -v`
Expected: FAIL (.gitattributes 不存在)

- [ ] **Step 3: 创建 .gitattributes**

```gitattributes
# 源码 zip 排除规则(git archive --format=zip)
# 开发产物不进源码包
.venv/ export-ignore
backend/.venv/ export-ignore
node_modules/ export-ignore
frontend/node_modules/ export-ignore
launcher/ui/node_modules/ export-ignore
dist/ export-ignore
frontend/dist/ export-ignore
launcher/ui/dist/ export-ignore

# 运行数据
data/ export-ignore
*.db export-ignore
data/images/ export-ignore
data/exports/ export-ignore
data/backups/ export-ignore
data/logs/ export-ignore
data/paddlex/ export-ignore
data/huggingface/ export-ignore
data/celery/ export-ignore
data/tmp/ export-ignore
data/archive/ export-ignore

# 敏感文件
.env export-ignore

# IDE 和系统文件
.trae/ export-ignore
.DS_Store export-ignore
__pycache__/ export-ignore
*.pyc export-ignore
*.log export-ignore
.pytest_cache/ export-ignore
backend/.pytest_cache/ export-ignore
*.tsbuildinfo export-ignore
```

- [ ] **Step 4: 运行测试看到通过**

Run: `cd backend && pytest tests/scripts/test_packaging_scripts.py::TestGitAttributes -v`
Expected: 5 tests passed

- [ ] **Step 5: Commit**

```bash
git add .gitattributes tests/scripts/test_packaging_scripts.py
git commit -m "feat(packaging): add .gitattributes for source zip export-ignore"
```

---

## Task 3: macOS 打包脚本

**Files:**
- Create: `scripts/package-macos.sh`
- Modify: `tests/scripts/test_packaging_scripts.py` (追加 TestPackageMacos 类)

**说明:** 下载便携版 Python(python-build-standalone)、创建 venv、装依赖、复制源码和构建产物、打 .app bundle、压缩。

- [ ] **Step 1: 追加测试到 tests/scripts/test_packaging_scripts.py**

在文件末尾追加:

```python
class TestPackageMacos:
    """macOS 打包脚本结构验证。"""

    def test_script_exists(self):
        assert (SCRIPTS_DIR / "package-macos.sh").exists()

    def test_script_has_shebang(self):
        content = (SCRIPTS_DIR / "package-macos.sh").read_text(encoding="utf-8")
        assert content.startswith("#!/bin/bash")

    def test_script_has_set_strict_mode(self):
        content = (SCRIPTS_DIR / "package-macos.sh").read_text(encoding="utf-8")
        assert "set -e" in content

    def test_script_downloads_python_build_standalone(self):
        content = (SCRIPTS_DIR / "package-macos.sh").read_text(encoding="utf-8")
        assert "python-build-standalone" in content
        assert "cpython-3.11" in content

    def test_script_creates_venv(self):
        content = (SCRIPTS_DIR / "package-macos.sh").read_text(encoding="utf-8")
        assert "-m venv" in content

    def test_script_installs_backend_requirements(self):
        content = (SCRIPTS_DIR / "package-macos.sh").read_text(encoding="utf-8")
        assert "requirements-runtime.txt" in content

    def test_script_installs_launcher_requirements(self):
        content = (SCRIPTS_DIR / "package-macos.sh").read_text(encoding="utf-8")
        assert "launcher/requirements.txt" in content

    def test_script_copies_backend_source(self):
        content = (SCRIPTS_DIR / "package-macos.sh").read_text(encoding="utf-8")
        assert "backend" in content
        assert "app/backend" in content

    def test_script_copies_frontend_dist(self):
        content = (SCRIPTS_DIR / "package-macos.sh").read_text(encoding="utf-8")
        assert "frontend/dist" in content

    def test_script_copies_launcher_ui_dist(self):
        content = (SCRIPTS_DIR / "package-macos.sh").read_text(encoding="utf-8")
        assert "launcher/ui/dist" in content

    def test_script_creates_data_dirs(self):
        content = (SCRIPTS_DIR / "package-macos.sh").read_text(encoding="utf-8")
        assert "data/logs" in content
        assert "data/paddlex" in content
        assert "data/huggingface" in content
        assert "data/tmp" in content

    def test_script_creates_app_bundle(self):
        content = (SCRIPTS_DIR / "package-macos.sh").read_text(encoding="utf-8")
        assert ".app" in content
        assert "Info.plist" in content
        assert "CFBundleExecutable" in content

    def test_script_creates_start_sh(self):
        content = (SCRIPTS_DIR / "package-macos.sh").read_text(encoding="utf-8")
        assert "start.sh" in content
        assert "launcher/main.py" in content

    def test_script_zips_output(self):
        content = (SCRIPTS_DIR / "package-macos.sh").read_text(encoding="utf-8")
        assert "zip" in content
        assert "macos" in content

    def test_script_accepts_version_argument(self):
        content = (SCRIPTS_DIR / "package-macos.sh").read_text(encoding="utf-8")
        # 第一个参数是 VERSION
        assert "VERSION=$1" in content or "VERSION=${1:" in content
```

- [ ] **Step 2: 运行测试看到失败**

Run: `cd backend && pytest tests/scripts/test_packaging_scripts.py::TestPackageMacos -v`
Expected: FAIL (脚本不存在)

- [ ] **Step 3: 创建 scripts/package-macos.sh**

```bash
#!/bin/bash
set -e

# macOS 打包脚本:产出 xhs-info-crawl-<version>-macos.zip
# 用法: ./scripts/package-macos.sh <version>
# 依赖: frontend/dist 和 launcher/ui/dist 已构建完成

VERSION=${1:?"用法: ./scripts/package-macos.sh <version>"}
ROOT_DIR=$(cd "$(dirname "$0")/.." && pwd)
BUILD_DIR=$ROOT_DIR/dist/build
PKG_DIR=$BUILD_DIR/xhs-info-crawl
PYTHON_VERSION="cpython-3.11.9+20240415"
PYTHON_ARCHIVE="$PYTHON_VERSION-darwin-arm64-install_only.tar.gz"
PYTHON_URL="https://github.com/astral-sh/python-build-standalone/releases/download/20240415/$PYTHON_ARCHIVE"

echo "==> 打包 macOS v$VERSION"
echo "项目根目录: $ROOT_DIR"

# 0. 清理旧构建
rm -rf $BUILD_DIR
mkdir -p $PKG_DIR

# 1. 下载便携版 Python 3.11.9(python-build-standalone)
echo "==> 下载便携版 Python..."
curl -L $PYTHON_URL | tar xz -C $BUILD_DIR
mv $BUILD_DIR/python $PKG_DIR/runtime/python

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
# .app 启动入口
DIR="$(dirname "$(dirname "$(dirname "$0")")")"
exec "$DIR/xhs-info-crawl/runtime/venv/bin/python" "$DIR/xhs-info-crawl/launcher/main.py"
EOF
chmod +x $BUILD_DIR/xhs-info-crawl.app/Contents/MacOS/start.sh

# 9. 压缩
echo "==> 压缩产物..."
cd $BUILD_DIR
zip -r xhs-info-crawl-$VERSION-macos.zip xhs-info-crawl xhs-info-crawl.app

echo "==> 完成: $BUILD_DIR/xhs-info-crawl-$VERSION-macos.zip"
```

- [ ] **Step 4: 运行测试看到通过**

Run: `cd backend && pytest tests/scripts/test_packaging_scripts.py::TestPackageMacos -v`
Expected: 15 tests passed

- [ ] **Step 5: 赋予执行权限**

Run: `chmod +x scripts/package-macos.sh`

- [ ] **Step 6: Commit**

```bash
git add scripts/package-macos.sh tests/scripts/test_packaging_scripts.py
git commit -m "feat(packaging): add macOS packaging script"
```

---

## Task 4: Windows 打包脚本

**Files:**
- Create: `scripts/package-windows.ps1`
- Modify: `tests/scripts/test_packaging_scripts.py` (追加 TestPackageWindows 类)

**说明:** 逻辑对应 macOS 版,差异:下载 x86_64 Windows Python、venv 路径用 Scripts\python.exe、用 PyInstaller 出 exe 启动器入口、压缩成 zip。

- [ ] **Step 1: 追加测试到 tests/scripts/test_packaging_scripts.py**

在文件末尾追加:

```python
class TestPackageWindows:
    """Windows 打包脚本结构验证。"""

    def test_script_exists(self):
        assert (SCRIPTS_DIR / "package-windows.ps1").exists()

    def test_script_has_param_version(self):
        content = (SCRIPTS_DIR / "package-windows.ps1").read_text(encoding="utf-8")
        assert "param" in content.lower()
        assert "version" in content.lower()

    def test_script_has_strict_mode(self):
        content = (SCRIPTS_DIR / "package-windows.ps1").read_text(encoding="utf-8")
        assert "$ErrorActionPreference" in content or "Set-StrictMode" in content

    def test_script_downloads_python_build_standalone(self):
        content = (SCRIPTS_DIR / "package-windows.ps1").read_text(encoding="utf-8")
        assert "python-build-standalone" in content
        assert "x86_64-pc-windows-msvc" in content

    def test_script_creates_venv(self):
        content = (SCRIPTS_DIR / "package-windows.ps1").read_text(encoding="utf-8")
        assert "-m venv" in content or "venv" in content.lower()

    def test_script_installs_backend_requirements(self):
        content = (SCRIPTS_DIR / "package-windows.ps1").read_text(encoding="utf-8")
        assert "requirements-runtime.txt" in content

    def test_script_installs_launcher_requirements(self):
        content = (SCRIPTS_DIR / "package-windows.ps1").read_text(encoding="utf-8")
        assert "launcher/requirements.txt" in content

    def test_script_copies_backend_source(self):
        content = (SCRIPTS_DIR / "package-windows.ps1").read_text(encoding="utf-8")
        assert "backend" in content

    def test_script_copies_frontend_dist(self):
        content = (SCRIPTS_DIR / "package-windows.ps1").read_text(encoding="utf-8")
        assert "frontend" in content
        assert "dist" in content

    def test_script_copies_launcher_ui_dist(self):
        content = (SCRIPTS_DIR / "package-windows.ps1").read_text(encoding="utf-8")
        assert "launcher" in content

    def test_script_creates_data_dirs(self):
        content = (SCRIPTS_DIR / "package-windows.ps1").read_text(encoding="utf-8")
        assert "data" in content
        assert "paddlex" in content

    def test_script_zips_output(self):
        content = (SCRIPTS_DIR / "package-windows.ps1").read_text(encoding="utf-8")
        assert "zip" in content.lower() or "Compress-Archive" in content
        assert "windows" in content.lower()

    def test_script_creates_start_bat(self):
        content = (SCRIPTS_DIR / "package-windows.ps1").read_text(encoding="utf-8")
        assert "start.bat" in content or "start.ps1" in content
```

- [ ] **Step 2: 运行测试看到失败**

Run: `cd backend && pytest tests/scripts/test_packaging_scripts.py::TestPackageWindows -v`
Expected: FAIL (脚本不存在)

- [ ] **Step 3: 创建 scripts/package-windows.ps1**

```powershell
# Windows 打包脚本:产出 xhs-info-crawl-<version>-windows.zip
# 用法: .\scripts\package-windows.ps1 -Version <version>
# 依赖: frontend\dist 和 launcher\ui\dist 已构建完成

param(
    [Parameter(Mandatory=$true)]
    [string]$Version
)

$ErrorActionPreference = "Stop"

$RootDir = Resolve-Path "$PSScriptRoot\.."
$BuildDir = Join-Path $RootDir "dist\build"
$PkgDir = Join-Path $BuildDir "xhs-info-crawl"
$PythonVersion = "cpython-3.11.9+20240415"
$PythonArchive = "$PythonVersion-x86_64-pc-windows-msvc-install_only.tar.gz"
$PythonUrl = "https://github.com/astral-sh/python-build-standalone/releases/download/20240415/$PythonArchive"

Write-Host "==> 打包 Windows v$Version"
Write-Host "项目根目录: $RootDir"

# 0. 清理旧构建
if (Test-Path $BuildDir) { Remove-Item -Recurse -Force $BuildDir }
New-Item -ItemType Directory -Force -Path $PkgDir | Out-Null

# 1. 下载便携版 Python 3.11.9(python-build-standalone)
Write-Host "==> 下载便携版 Python..."
$PythonTgz = Join-Path $BuildDir $PythonArchive
Invoke-WebRequest -Uri $PythonUrl -OutFile $PythonTgz
tar xzf $PythonTgz -C $BuildDir
Move-Item (Join-Path $BuildDir "python") (Join-Path $PkgDir "runtime\python")

# 2. 创建 venv 并安装依赖(不含 ocr extra)
Write-Host "==> 创建 venv 并安装依赖..."
$VenvPython = Join-Path $PkgDir "runtime\python\python.exe"
& $VenvPython -m venv (Join-Path $PkgDir "runtime\venv")
$VenvPip = Join-Path $PkgDir "runtime\venv\Scripts\pip.exe"
& $VenvPip install --upgrade pip
& $VenvPip install -r (Join-Path $RootDir "backend\requirements-runtime.txt")
& $VenvPip install -r (Join-Path $RootDir "launcher\requirements.txt")

# 3. 复制后端源码
Write-Host "==> 复制后端源码..."
Copy-Item -Recurse (Join-Path $RootDir "backend") (Join-Path $PkgDir "app\backend")

# 4. 复制前端构建产物
Write-Host "==> 复制前端构建产物..."
$FrontendDistSrc = Join-Path $RootDir "frontend\dist"
$FrontendDistDst = Join-Path $PkgDir "app\frontend\dist"
New-Item -ItemType Directory -Force -Path $FrontendDistDst | Out-Null
Copy-Item -Recurse (Join-Path $FrontendDistSrc "*") $FrontendDistDst

# 5. 复制启动器(不含 ui\src 和 node_modules)
Write-Host "==> 复制启动器..."
$LauncherUiDistDst = Join-Path $PkgDir "launcher\ui\dist"
New-Item -ItemType Directory -Force -Path $LauncherUiDistDst | Out-Null
Copy-Item (Join-Path $RootDir "launcher\*.py") (Join-Path $PkgDir "launcher\")
Copy-Item (Join-Path $RootDir "launcher\requirements.txt") (Join-Path $PkgDir "launcher\")
Copy-Item -Recurse (Join-Path $RootDir "launcher\ui\dist\*") $LauncherUiDistDst

# 6. 复制 .env.example
Copy-Item (Join-Path $RootDir ".env.example") (Join-Path $PkgDir ".env.example")

# 7. 创建空 data 目录
Write-Host "==> 创建 data 目录..."
$dataDirs = @("logs", "images", "exports", "celery", "tmp", "run", "archive", "backups")
foreach ($d in $dataDirs) {
    New-Item -ItemType Directory -Force -Path (Join-Path $PkgDir "data\$d") | Out-Null
}
New-Item -ItemType Directory -Force -Path (Join-Path $PkgDir "data\paddlex\official_models") | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $PkgDir "data\huggingface") | Out-Null

# 8. 创建 start.bat 启动入口
Write-Host "==> 创建 start.bat..."
$startBatContent = @"
@echo off
set DIR=%~dp0
cd /d "%DIR%"
"%DIR%runtime\venv\Scripts\python.exe" "%DIR%launcher\main.py"
"@
Set-Content -Path (Join-Path $PkgDir "start.bat") -Value $startBatContent -Encoding UTF8

# 9. 压缩
Write-Host "==> 压缩产物..."
$ZipPath = Join-Path $BuildDir "xhs-info-crawl-$Version-windows.zip"
Compress-Archive -Path $PkgDir -DestinationPath $ZipPath -Force

Write-Host "==> 完成: $ZipPath"
```

- [ ] **Step 4: 运行测试看到通过**

Run: `cd backend && pytest tests/scripts/test_packaging_scripts.py::TestPackageWindows -v`
Expected: 13 tests passed

- [ ] **Step 5: Commit**

```bash
git add scripts/package-windows.ps1 tests/scripts/test_packaging_scripts.py
git commit -m "feat(packaging): add Windows packaging script"
```

---

## Task 5: OCR 增强包打包脚本

**Files:**
- Create: `scripts/package-ocr-addon.sh`
- Modify: `tests/scripts/test_packaging_scripts.py` (追加 TestPackageOcrAddon 类)

**说明:** 下载 paddleocr + paddlepaddle wheel、触发模型下载、打包成 zip。3 个平台(macos-arm64/macos-x86_64/windows-x64)用参数区分。

- [ ] **Step 1: 追加测试到 tests/scripts/test_packaging_scripts.py**

在文件末尾追加:

```python
class TestPackageOcrAddon:
    """OCR 增强包打包脚本结构验证。"""

    def test_script_exists(self):
        assert (SCRIPTS_DIR / "package-ocr-addon.sh").exists()

    def test_script_has_shebang(self):
        content = (SCRIPTS_DIR / "package-ocr-addon.sh").read_text(encoding="utf-8")
        assert content.startswith("#!/bin/bash")

    def test_script_has_set_strict_mode(self):
        content = (SCRIPTS_DIR / "package-ocr-addon.sh").read_text(encoding="utf-8")
        assert "set -e" in content

    def test_script_accepts_three_arguments(self):
        content = (SCRIPTS_DIR / "package-ocr-addon.sh").read_text(encoding="utf-8")
        assert "OS=$1" in content or 'OS=${1' in content
        assert "ARCH=$2" in content or 'ARCH=${2' in content
        assert "VERSION=$3" in content or 'VERSION=${3' in content

    def test_script_downloads_paddleocr_wheel(self):
        content = (SCRIPTS_DIR / "package-ocr-addon.sh").read_text(encoding="utf-8")
        assert "paddleocr" in content.lower()
        assert "pip download" in content or "pip install" in content

    def test_script_downloads_paddlepaddle_wheel(self):
        content = (SCRIPTS_DIR / "package-ocr-addon.sh").read_text(encoding="utf-8")
        assert "paddlepaddle" in content.lower()

    def test_script_triggers_model_download(self):
        content = (SCRIPTS_DIR / "package-ocr-addon.sh").read_text(encoding="utf-8")
        assert "PADDLE_PDX_CACHE_HOME" in content
        assert "PaddleOCR" in content or "paddleocr" in content.lower()

    def test_script_writes_version_file(self):
        content = (SCRIPTS_DIR / "package-ocr-addon.sh").read_text(encoding="utf-8")
        assert "version:" in content
        assert "built_at" in content

    def test_script_zips_output(self):
        content = (SCRIPTS_DIR / "package-ocr-addon.sh").read_text(encoding="utf-8")
        assert "zip" in content
        assert "ocr-addon" in content

    def test_script_supports_macos_arm64(self):
        content = (SCRIPTS_DIR / "package-ocr-addon.sh").read_text(encoding="utf-8")
        assert "macos" in content
        assert "arm64" in content

    def test_script_supports_windows_x64(self):
        content = (SCRIPTS_DIR / "package-ocr-addon.sh").read_text(encoding="utf-8")
        assert "windows" in content
        assert "x64" in content or "x86_64" in content

    def test_script_creates_wheels_dir(self):
        content = (SCRIPTS_DIR / "package-ocr-addon.sh").read_text(encoding="utf-8")
        assert "wheels" in content

    def test_script_creates_models_dir(self):
        content = (SCRIPTS_DIR / "package-ocr-addon.sh").read_text(encoding="utf-8")
        assert "official_models" in content
```

- [ ] **Step 2: 运行测试看到失败**

Run: `cd backend && pytest tests/scripts/test_packaging_scripts.py::TestPackageOcrAddon -v`
Expected: FAIL (脚本不存在)

- [ ] **Step 3: 创建 scripts/package-ocr-addon.sh**

```bash
#!/bin/bash
set -e

# OCR 增强包打包脚本:产出 paddleocr-addon-<version>-<os>-<arch>.zip
# 用法: ./scripts/package-ocr-addon.sh <os> <arch> <version>
# 平台支持: macos-arm64 / macos-x86_64 / windows-x64
# 依赖: 当前环境已装 Python 3.11 + pip

OS=${1:?"用法: ./scripts/package-ocr-addon.sh <os> <arch> <version>"}
ARCH=${2:?"用法: ./scripts/package-ocr-addon.sh <os> <arch> <version>"}
VERSION=${3:?"用法: ./scripts/package-ocr-addon.sh <os> <arch> <version>"}

ROOT_DIR=$(cd "$(dirname "$0")/.." && pwd)
BUILD_DIR=$ROOT_DIR/dist/ocr-addon-build
WHEELS_DIR=$BUILD_DIR/wheels
MODELS_DIR=$BUILD_DIR/data/paddlex/official_models

echo "==> 打包 OCR 增强包 $OS-$ARCH v$VERSION"

# 0. 清理旧构建
rm -rf $BUILD_DIR
mkdir -p $WHEELS_DIR $MODELS_DIR

# 1. 确定 wheel 平台标签
case "$OS-$ARCH" in
  macos-arm64)
    WHEEL_PLATFORM_TAG="macosx_11_0_arm64"
    PADDLE_PLATFORM="macosx_11_0_arm64"
    ;;
  macos-x86_64)
    WHEEL_PLATFORM_TAG="macosx_10_9_x86_64"
    PADDLE_PLATFORM="macosx_10_9_x86_64"
    ;;
  windows-x64)
    WHEEL_PLATFORM_TAG="win_amd64"
    PADDLE_PLATFORM="win_amd64"
    ;;
  *)
    echo "错误: 不支持的平台 $OS-$ARCH"
    echo "支持: macos-arm64 / macos-x86_64 / windows-x64"
    exit 1
    ;;
esac

# 2. 下载 paddleocr wheel(纯 Python,平台无关)
echo "==> 下载 paddleocr wheel..."
pip download paddleocr==$VERSION \
  --no-deps \
  -d $WHEELS_DIR/

# 3. 下载 paddlepaddle wheel(平台相关)
echo "==> 下载 paddlepaddle wheel..."
pip download paddlepaddle==3.3.1 \
  --platform $PADDLE_PLATFORM \
  --only-binary=:all: \
  --no-deps \
  -d $WHEELS_DIR/

# 4. 下载 paddleocr 依赖 wheel(一次性,跨平台)
echo "==> 下载 paddleocr 依赖 wheel..."
pip download paddleocr==$VERSION \
  -d $WHEELS_DIR/

# 5. 触发模型下载到指定目录
echo "==> 下载 OCR 模型文件..."
PADDLE_PDX_CACHE_HOME=$BUILD_DIR/data/paddlex python -c "
import os
os.environ['PADDLE_PDX_CACHE_HOME'] = '$BUILD_DIR/data/paddlex'
from paddleocr import PaddleOCR
# 初始化触发模型下载到指定目录
ocr = PaddleOCR(
    lang='ch',
    use_doc_orientation_classify=False,
    use_doc_unwarping=False,
    use_textline_orientation=False,
)
print('模型下载完成')
"

# 6. 写 VERSION 文件
echo "version: $VERSION" > $BUILD_DIR/VERSION
echo "built_at: $(date -u +%Y-%m-%dT%H:%M:%SZ)" >> $BUILD_DIR/VERSION
echo "platform: $OS-$ARCH" >> $BUILD_DIR/VERSION

# 7. 压缩
echo "==> 压缩产物..."
cd $ROOT_DIR/dist
zip -r paddleocr-addon-$VERSION-$OS-$ARCH.zip ocr-addon-build

echo "==> 完成: $ROOT_DIR/dist/paddleocr-addon-$VERSION-$OS-$ARCH.zip"
```

- [ ] **Step 4: 运行测试看到通过**

Run: `cd backend && pytest tests/scripts/test_packaging_scripts.py::TestPackageOcrAddon -v`
Expected: 13 tests passed

- [ ] **Step 5: 赋予执行权限**

Run: `chmod +x scripts/package-ocr-addon.sh`

- [ ] **Step 6: Commit**

```bash
git add scripts/package-ocr-addon.sh tests/scripts/test_packaging_scripts.py
git commit -m "feat(packaging): add OCR addon packaging script"
```

---

## Task 6: GitHub Actions 工作流

**Files:**
- Create: `.github/workflows/release.yml`
- Create: `.github/workflows/release-ocr-addon.yml`
- Modify: `tests/scripts/test_packaging_scripts.py` (追加 TestGithubWorkflows 类)

**说明:**
- `release.yml`:推 `v*.*.*` tag 触发,build-macos + build-windows + release 三 job
- `release-ocr-addon.yml`:推 `ocr-addon-*` tag 触发,3 个平台 build job + release job

- [ ] **Step 1: 追加测试到 tests/scripts/test_packaging_scripts.py**

在文件末尾追加:

```python
class TestGithubWorkflows:
    """GitHub Actions 工作流结构验证。"""

    def test_release_yml_exists(self):
        assert (WORKFLOWS_DIR / "release.yml").exists()

    def test_release_ocr_addon_yml_exists(self):
        assert (WORKFLOWS_DIR / "release-ocr-addon.yml").exists()

    def test_release_yml_triggers_on_version_tag(self):
        content = (WORKFLOWS_DIR / "release.yml").read_text(encoding="utf-8")
        assert "v*.*.*" in content or "v*" in content
        assert "tags" in content

    def test_release_yml_has_build_macos_job(self):
        content = (WORKFLOWS_DIR / "release.yml").read_text(encoding="utf-8")
        assert "build-macos" in content
        assert "macos-latest" in content

    def test_release_yml_has_build_windows_job(self):
        content = (WORKFLOWS_DIR / "release.yml").read_text(encoding="utf-8")
        assert "build-windows" in content
        assert "windows-latest" in content

    def test_release_yml_has_release_job(self):
        content = (WORKFLOWS_DIR / "release.yml").read_text(encoding="utf-8")
        assert "release" in content
        assert "needs" in content

    def test_release_yml_builds_frontend(self):
        content = (WORKFLOWS_DIR / "release.yml").read_text(encoding="utf-8")
        assert "frontend" in content
        assert "npm" in content

    def test_release_yml_builds_launcher_ui(self):
        content = (WORKFLOWS_DIR / "release.yml").read_text(encoding="utf-8")
        assert "launcher/ui" in content

    def test_release_yml_calls_package_scripts(self):
        content = (WORKFLOWS_DIR / "release.yml").read_text(encoding="utf-8")
        assert "package-macos.sh" in content
        assert "package-windows.ps1" in content

    def test_release_yml_creates_source_zip(self):
        content = (WORKFLOWS_DIR / "release.yml").read_text(encoding="utf-8")
        assert "git archive" in content or "src.zip" in content or "src" in content

    def test_release_yml_uploads_artifacts(self):
        content = (WORKFLOWS_DIR / "release.yml").read_text(encoding="utf-8")
        assert "upload-artifact" in content

    def test_release_yml_creates_github_release(self):
        content = (WORKFLOWS_DIR / "release.yml").read_text(encoding="utf-8")
        assert "softprops/action-gh-release" in content or "gh release create" in content

    def test_release_ocr_addon_triggers_on_ocr_tag(self):
        content = (WORKFLOWS_DIR / "release-ocr-addon.yml").read_text(encoding="utf-8")
        assert "ocr-addon-*" in content or "ocr-addon-" in content
        assert "tags" in content

    def test_release_ocr_addon_has_macos_arm64_job(self):
        content = (WORKFLOWS_DIR / "release-ocr-addon.yml").read_text(encoding="utf-8")
        assert "arm64" in content
        assert "macos" in content

    def test_release_ocr_addon_has_macos_x86_64_job(self):
        content = (WORKFLOWS_DIR / "release-ocr-addon.yml").read_text(encoding="utf-8")
        assert "x86_64" in content

    def test_release_ocr_addon_has_windows_x64_job(self):
        content = (WORKFLOWS_DIR / "release-ocr-addon.yml").read_text(encoding="utf-8")
        assert "windows" in content
        assert "x64" in content or "x86_64" in content

    def test_release_ocr_addon_calls_package_script(self):
        content = (WORKFLOWS_DIR / "release-ocr-addon.yml").read_text(encoding="utf-8")
        assert "package-ocr-addon.sh" in content

    def test_release_ocr_addon_has_release_job(self):
        content = (WORKFLOWS_DIR / "release-ocr-addon.yml").read_text(encoding="utf-8")
        assert "release" in content
        assert "needs" in content
```

- [ ] **Step 2: 运行测试看到失败**

Run: `cd backend && pytest tests/scripts/test_packaging_scripts.py::TestGithubWorkflows -v`
Expected: FAIL (工作流不存在)

- [ ] **Step 3: 创建 .github/workflows/release.yml**

```yaml
name: Release

on:
  push:
    tags:
      - 'v*.*.*'

permissions:
  contents: write

jobs:
  build-macos:
    name: Build macOS
    runs-on: macos-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-node@v4
        with:
          node-version: '22'

      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'

      - name: Extract version from tag
        id: version
        run: echo "VERSION=${GITHUB_REF_NAME#v}" >> $GITHUB_OUTPUT

      - name: Install frontend deps
        run: npm --prefix frontend ci

      - name: Build frontend
        run: npm --prefix frontend run build

      - name: Install launcher UI deps
        run: npm --prefix launcher/ui ci

      - name: Build launcher UI
        run: npm --prefix launcher/ui run build

      - name: Run packaging script
        run: ./scripts/package-macos.sh ${{ steps.version.outputs.VERSION }}

      - name: Upload artifact
        uses: actions/upload-artifact@v4
        with:
          name: macos-zip
          path: dist/build/xhs-info-crawl-${{ steps.version.outputs.VERSION }}-macos.zip

  build-windows:
    name: Build Windows
    runs-on: windows-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-node@v4
        with:
          node-version: '22'

      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'

      - name: Extract version from tag
        id: version
        shell: bash
        run: echo "VERSION=${GITHUB_REF_NAME#v}" >> $GITHUB_OUTPUT

      - name: Install frontend deps
        run: npm --prefix frontend ci

      - name: Build frontend
        run: npm --prefix frontend run build

      - name: Install launcher UI deps
        run: npm --prefix launcher/ui ci

      - name: Build launcher UI
        run: npm --prefix launcher/ui run build

      - name: Run packaging script
        shell: pwsh
        run: .\scripts\package-windows.ps1 -Version ${{ steps.version.outputs.VERSION }}

      - name: Upload artifact
        uses: actions/upload-artifact@v4
        with:
          name: windows-zip
          path: dist/build/xhs-info-crawl-${{ steps.version.outputs.VERSION }}-windows.zip

  release:
    name: Create GitHub Release
    needs: [build-macos, build-windows]
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Extract version from tag
        id: version
        run: echo "VERSION=${GITHUB_REF_NAME#v}" >> $GITHUB_OUTPUT

      - name: Download macOS artifact
        uses: actions/download-artifact@v4
        with:
          name: macos-zip
          path: artifacts

      - name: Download Windows artifact
        uses: actions/download-artifact@v4
        with:
          name: windows-zip
          path: artifacts

      - name: Create source zip
        run: |
          git archive --format=zip --prefix=xhs-info-crawl/ HEAD \
            > artifacts/xhs-info-crawl-${{ steps.version.outputs.VERSION }}-src.zip

      - name: Create GitHub Release
        uses: softprops/action-gh-release@v2
        with:
          files: |
            artifacts/xhs-info-crawl-${{ steps.version.outputs.VERSION }}-macos.zip
            artifacts/xhs-info-crawl-${{ steps.version.outputs.VERSION }}-windows.zip
            artifacts/xhs-info-crawl-${{ steps.version.outputs.VERSION }}-src.zip
          generate_release_notes: true
```

- [ ] **Step 4: 创建 .github/workflows/release-ocr-addon.yml**

```yaml
name: Release OCR Addon

on:
  push:
    tags:
      - 'ocr-addon-*'

permissions:
  contents: write

jobs:
  build-macos-arm64:
    name: Build OCR Addon macOS arm64
    runs-on: macos-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'

      - name: Extract version from tag
        id: version
        run: |
          TAG=${GITHUB_REF_NAME#ocr-addon-}
          echo "VERSION=$TAG" >> $GITHUB_OUTPUT

      - name: Run packaging script
        run: ./scripts/package-ocr-addon.sh macos arm64 ${{ steps.version.outputs.VERSION }}

      - name: Upload artifact
        uses: actions/upload-artifact@v4
        with:
          name: ocr-addon-macos-arm64
          path: dist/paddleocr-addon-${{ steps.version.outputs.VERSION }}-macos-arm64.zip

  build-macos-x86_64:
    name: Build OCR Addon macOS x86_64
    runs-on: macos-13
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'

      - name: Extract version from tag
        id: version
        run: |
          TAG=${GITHUB_REF_NAME#ocr-addon-}
          echo "VERSION=$TAG" >> $GITHUB_OUTPUT

      - name: Run packaging script
        run: ./scripts/package-ocr-addon.sh macos x86_64 ${{ steps.version.outputs.VERSION }}

      - name: Upload artifact
        uses: actions/upload-artifact@v4
        with:
          name: ocr-addon-macos-x86_64
          path: dist/paddleocr-addon-${{ steps.version.outputs.VERSION }}-macos-x86_64.zip

  build-windows-x64:
    name: Build OCR Addon Windows x64
    runs-on: windows-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'

      - name: Extract version from tag
        id: version
        shell: bash
        run: |
          TAG=${GITHUB_REF_NAME#ocr-addon-}
          echo "VERSION=$TAG" >> $GITHUB_OUTPUT

      - name: Run packaging script
        shell: bash
        run: ./scripts/package-ocr-addon.sh windows x64 ${{ steps.version.outputs.VERSION }}

      - name: Upload artifact
        uses: actions/upload-artifact@v4
        with:
          name: ocr-addon-windows-x64
          path: dist/paddleocr-addon-${{ steps.version.outputs.VERSION }}-windows-x64.zip

  release:
    name: Create OCR Addon Release
    needs: [build-macos-arm64, build-macos-x86_64, build-windows-x64]
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Extract version from tag
        id: version
        run: |
          TAG=${GITHUB_REF_NAME#ocr-addon-}
          echo "VERSION=$TAG" >> $GITHUB_OUTPUT

      - name: Download all artifacts
        uses: actions/download-artifact@v4
        with:
          path: artifacts

      - name: Move artifacts to release root
        run: |
          mkdir -p release-assets
          find artifacts -name "*.zip" -exec cp {} release-assets/ \;

      - name: Create GitHub Release
        uses: softprops/action-gh-release@v2
        with:
          files: release-assets/*.zip
          name: OCR Addon ${{ steps.version.outputs.VERSION }}
          generate_release_notes: true
```

- [ ] **Step 5: 运行测试看到通过**

Run: `cd backend && pytest tests/scripts/test_packaging_scripts.py::TestGithubWorkflows -v`
Expected: 18 tests passed

- [ ] **Step 6: 运行全部打包脚本测试确认无回归**

Run: `cd backend && pytest tests/scripts/test_packaging_scripts.py -v`
Expected: 全部测试通过(8 + 5 + 15 + 13 + 13 + 18 = 72 passed)

- [ ] **Step 7: Commit**

```bash
git add .github/workflows/release.yml .github/workflows/release-ocr-addon.yml tests/scripts/test_packaging_scripts.py
git commit -m "feat(packaging): add GitHub Actions release workflows"
```

---

## Self-Review

**1. Spec coverage:**
- § 6.1 打包机准备(GitHub Actions macos-latest/windows-latest)→ release.yml + release-ocr-addon.yml ✓
- § 6.2 主程序工作流(build-macos + build-windows + release)→ release.yml ✓
- § 6.2 OCR 增强包工作流(3 平台 build + release)→ release-ocr-addon.yml ✓
- § 6.3 macOS 打包脚本(python-build-standalone + venv + 复制源码 + .app bundle + zip)→ package-macos.sh ✓
- § 6.4 Windows 打包脚本(对应 macOS 版)→ package-windows.ps1 ✓
- § 6.5 OCR 增强包构建(pip download + 模型下载 + VERSION + zip)→ package-ocr-addon.sh ✓
- § 6.6 源码 zip 包(git archive + .gitattributes)→ .gitattributes + release.yml release job ✓
- § 6.7 Release 产物清单(主程序 3 个 zip + OCR 3 个 zip)→ 两个工作流均上传 ✓

**2. Placeholder scan:**
- 无 TBD/TODO 占位
- 所有步骤都有完整代码
- 测试代码完整,无"类似 Task N"引用

**3. Type consistency:**
- `backend/requirements-runtime.txt` 在 Task 1 创建,Task 3 和 Task 4 的打包脚本引用 ✓
- `launcher/requirements.txt` 在 Task 1 创建,Task 3 和 Task 4 的打包脚本引用 ✓
- 打包脚本文件名在 Task 3/4/5 定义,Task 6 的工作流引用一致 ✓
- 测试文件 `tests/scripts/test_packaging_scripts.py` 在 Task 1 创建,后续 Task 2-6 追加类 ✓

**4. 额外检查:**
- 打包脚本不实际执行(需 GitHub Actions runner),测试用静态结构验证
- .gitattributes 的 export-ignore 规则覆盖 .venv/node_modules/data/.env/dist
- release.yml 的 release job 依赖 build-macos 和 build-windows(用 needs)
- release-ocr-addon.yml 的 release job 依赖 3 个平台 build job
- Python 版本 3.11.9 和 Node 版本 22 与 spec 对齐
