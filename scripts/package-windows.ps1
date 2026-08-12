# Windows 打包脚本:产出 xhs-info-crawl-<version>-windows.zip
# 用法: .\scripts\package-windows.ps1 -Version <version>
# 依赖: frontend\dist 和 launcher\ui\dist 已构建完成
# Python: python-build-standalone cpython-3.11.9 (astral-sh)

param(
    [Parameter(Mandatory=$true)]
    [string]$Version
)

$ErrorActionPreference = "Stop"
# 强制 UTF-8 编码,避免 Windows 默认 cp1252 导致 pip 输出 UnicodeDecodeError
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"

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
Write-Host "==> 解压 Python..."
tar xzf $PythonTgz -C $BuildDir
Write-Host "解压后 BuildDir 顶层内容:"
Get-ChildItem $BuildDir | Format-Table Name, Mode, Length
# 递归查找含 python.exe 的目录(不假设目录名,也不限制深度)
$PythonExe = Get-ChildItem $BuildDir -Recurse -Filter "python.exe" -File | Select-Object -First 1
if (-not $PythonExe) {
    throw "解压后未找到 python.exe,检查 $BuildDir 内容"
}
$PythonDir = Split-Path $PythonExe.FullName -Parent
# 如果是 install_only 布局,python.exe 在 <root>/python/install/python.exe,
# 我们要的是 <root>/python/install 作为 runtime/python
# 但如果直接在 <root>/python.exe,那就用 <root>
$PythonDest = Join-Path $PkgDir "runtime\python"
New-Item -ItemType Directory -Force -Path (Split-Path $PythonDest) | Out-Null
Move-Item $PythonDir $PythonDest
Remove-Item $PythonTgz -Force

# 2. 创建 venv 并安装依赖(不含 ocr extra)
Write-Host "==> 创建 venv 并安装依赖..."
$VenvPython = Join-Path $PkgDir "runtime\python\python.exe"
& $VenvPython -m venv (Join-Path $PkgDir "runtime\venv")
$VenvPip = Join-Path $PkgDir "runtime\venv\Scripts\pip.exe"
# 不强制升级 pip,避免 Windows 编码问题;venv 自带 pip 足够
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
