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
# 默认模式即可(Windows 默认 copy,MacOS 默认 symlink,MacOS 我们手动替换)
& $VenvPython -m venv (Join-Path $PkgDir "runtime\venv")
$VenvPip = Join-Path $PkgDir "runtime\venv\Scripts\pip.exe"
# 不强制升级 pip,避免 Windows 编码问题;venv 自带 pip 足够
& $VenvPip install -r (Join-Path $RootDir "backend\requirements-runtime.txt")
& $VenvPip install -r (Join-Path $RootDir "launcher\requirements.txt")

# 修复 venv/pyvenv.cfg 烧了 CI runner 绝对路径 的问题:
# CPython 创建 venv 时会在 pyvenv.cfg 里写 `home = <创建时 base python 的绝对路径>`。
# 打包脚本运行在 GitHub Actions runner 上,pyvenv.cfg 里的 home 烧的是
# runner 的 workspace 路径(如 D:\a\xhs-info-crawl\xhs-info-crawl\dist\build\xhs-info-crawl\runtime\python)。
# 打包成 zip 发给用户后,用户在 C:\Users\wpx\Downloads\xhs-info-crawl\ 解压,
# 启动 venv 的 python.exe 时 CPython 按 home 找 base python 找不到
# → 报错 `No Python at '<runner 路径>'`,用户 2026-08-21 实测。
# 修复方案:patch pyvenv.cfg 的 home 为相对路径 ..\python(相对 venv 自身),
# CPython 接受相对 home,实测见 macOS 实验 (相对路径 ../python/bin 被接受,不再报 No Python at)。
# 关联 spec: docs/superpowers/specs/2026-08-21-windows-packaging-pyvenv-relocatable-design.md
Write-Host "==> patch pyvenv.cfg 的 home 为相对路径(避免烧 CI runner 路径)..."
$PyvenvCfg = Join-Path $PkgDir "runtime\venv\pyvenv.cfg"
if (Test-Path $PyvenvCfg) {
    $CfgContent = Get-Content $PyvenvCfg -Raw
    # 用正则替换 `home = ...` 这一行为相对路径(无论原始是绝对还是相对)
    $CfgContent = $CfgContent -replace 'home\s*=\s*.*', 'home = ..\python'
    # include-system-site-packages 设成 false(默认就是,但保险)
    Set-Content -Path $PyvenvCfg -Value $CfgContent -Encoding UTF8 -NoNewline
} else {
    Write-Host "    警告: $PyvenvCfg 不存在,跳过 patch"
}

# 修复 venv 可能缺少 python3XY.dll 问题:
# python-build-standalone 创建 venv 后,venv 目录下可能缺 dll,导致 python.exe 启动失败。
# 解决:把 base python 的 dll 复制到 venv 根目录(Windows 通常不需要,但保险起见)
Write-Host "==> 修复 venv dll..."
$VenvDir = Join-Path $PkgDir "runtime\venv"
$PythonBaseDir = Join-Path $PkgDir "runtime\python"
Get-ChildItem $PythonBaseDir -Filter "python3*.dll" | ForEach-Object {
    Copy-Item $_.FullName -Destination $VenvDir -Force
}
Get-ChildItem $PythonBaseDir -Filter "python3*.dll" | Where-Object { $_.Name -like "vcruntime*" -or $_.Name -like "api-ms-*" } | ForEach-Object {
    Copy-Item $_.FullName -Destination $VenvDir -Force
}

# 3. 复制后端源码(排除测试代码)
Write-Host "==> 复制后端源码(排除 tests)..."
New-Item -ItemType Directory -Force -Path (Join-Path $PkgDir "app\backend") | Out-Null
# 用 robocopy 排除 tests 目录(Windows 自带)
# robocopy 退出码 0-7 都视为成功,8+ 视为失败
$BackendSrc = Join-Path $RootDir "backend"
$BackendDst = Join-Path $PkgDir "app\backend"
$RobocopyOutput = robocopy $BackendSrc $BackendDst /E /XD tests __pycache__ .pytest_cache /XF .coverage /NFL /NDL /NJH /NJS /NC /NS 2>&1
if ($LASTEXITCODE -ge 8) {
    throw "robocopy 失败,退出码 $LASTEXITCODE,输出: ${RobocopyOutput}"
}
# 重置退出码,避免 PowerShell $ErrorActionPreference="Stop" 终止
$global:LASTEXITCODE = 0

# 4. 复制前端构建产物
Write-Host "==> 复制前端构建产物..."
$FrontendDistSrc = Join-Path $RootDir "frontend\dist"
$FrontendDistDst = Join-Path $PkgDir "app\frontend\dist"
New-Item -ItemType Directory -Force -Path $FrontendDistDst | Out-Null
Copy-Item -Recurse (Join-Path $FrontendDistSrc "*") $FrontendDistDst

# 5. 复制启动器(不含 ui/src 和 node_modules)
Write-Host "==> 复制启动器..."
$LauncherDist = Join-Path $PkgDir "launcher\ui\dist"
New-Item -ItemType Directory -Force -Path $LauncherDist | Out-Null
Copy-Item (Join-Path $RootDir "launcher\*.py") $LauncherDist\..\ -Force
Copy-Item (Join-Path $RootDir "launcher\requirements.txt") $LauncherDist\..\ -Force
Copy-Item -Recurse (Join-Path $RootDir "launcher\ui\dist\*") $LauncherDist\

# 修复 index.html 的绝对路径为相对路径,
# 否则 PyWebView 用 file:// 加载时找不到 /assets/... (会白屏)
$IndexHtml = Join-Path $LauncherDist "index.html"
if (Test-Path $IndexHtml) {
    Write-Host "==> 修复 index.html 资源路径为相对路径..."
    (Get-Content $IndexHtml -Raw) `
        -replace 'src="/assets/', 'src="./assets/' `
        -replace 'href="/assets/', 'href="./assets/' `
        | Set-Content -Path $IndexHtml -Encoding UTF8 -NoNewline
}

# 修复 frontend/dist 的绝对路径为相对路径(launcher 用 python -m http.server
# 暴露 frontend/dist,浏览器通过 http://127.0.0.1:<web_port>/ 访问,
# 相对路径才能正确加载 assets)
$FrontendIndex = Join-Path $PkgDir "app\frontend\dist\index.html"
if (Test-Path $FrontendIndex) {
    Write-Host "==> 修复 frontend/dist/index.html 资源路径为相对路径..."
    (Get-Content $FrontendIndex -Raw) `
        -replace 'src="/assets/', 'src="./assets/' `
        -replace 'href="/assets/', 'href="./assets/' `
        | Set-Content -Path $FrontendIndex -Encoding UTF8 -NoNewline
}

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
setlocal
set DIR=%~dp0
cd /d "%DIR%"
rem python-build-standalone Windows 也可能需要 PYTHONHOME 指向 base python
set PYTHONHOME=%DIR%runtime\python
set PYTHONPATH=%DIR%;%PYTHONPATH%
cd /d "%DIR%launcher"
rem 输出到 log 文件,即便窗口关闭也能看到错误
"%DIR%runtime\venv\Scripts\python.exe" "%DIR%launcher\main.py" > "%DIR%data\logs\launcher.log" 2>&1
if errorlevel 1 (
    echo.
    echo ========================================
    echo  启动失败,请查看日志:
    echo   %DIR%data\logs\launcher.log
    echo ========================================
    echo.
    pause
)
"@
Set-Content -Path (Join-Path $PkgDir "start.bat") -Value $startBatContent -Encoding UTF8

# 创建 start.vbs (终端用户首选入口,不弹 cmd 黑窗口)
# Windows 没有像 macOS 那样把目录包装成 .app 的概念,正确入口是 .vbs (隐藏 cmd 窗口)。
# start.bat 给高级用户调试用(失败时 pause);start.vbs 给终端用户(双击静默启动)。
#
# 实现:
# - 取本 vbs 自身的目录 → 用 start.bat 的绝对路径 → 用 WScript.Shell.Run 启动
# - WindowStyle=0 (HideWindow) → 子进程不弹 cmd 黑窗口
# - WaitOnReturn=False → vbs 不阻塞,不等 launcher 退出
#
# 关联 spec: docs/superpowers/specs/2026-08-21-windows-packaging-pyvenv-relocatable-design.md § 2.1
# 关联设计: docs/packaging-design.md §2.11 问题 ㉘
Write-Host "==> 创建 start.vbs (静默入口,不弹 cmd 窗口)..."
# 单引号 here-string (@'...'@) 不会做 PS 转义,内容字面输出。
# 收尾的 '@  必须新行起 (PS 规则);中间行不能包含 '@ 全文。
$startVbsContent = @'
' start.vbs - 静默启动入口,不弹 cmd 黑窗口
' 双击此处启动 launcher,日志会写到 data\logs\launcher.log(由 start.bat 重定向)
Dim fso, scriptPath, scriptDir, batPath, WshShell
Set fso = CreateObject("Scripting.FileSystemObject")
scriptPath = WScript.ScriptFullName
scriptDir = fso.GetParentFolderName(scriptPath)
batPath = scriptDir & "\start.bat"
Set WshShell = CreateObject("WScript.Shell")
' Run with WindowStyle=0 (HideWindow), WaitOnReturn=False (do not block)
WshShell.Run """" & batPath & """", 0, False
Set WshShell = Nothing
Set fso = Nothing
'@
Set-Content -Path (Join-Path $PkgDir "start.vbs") -Value $startVbsContent -NoNewline -Encoding UTF8

# 9. 压缩
Write-Host "==> 压缩产物..."
$ZipPath = Join-Path $BuildDir "xhs-info-crawl-$Version-windows.zip"
Compress-Archive -Path $PkgDir -DestinationPath $ZipPath -Force

Write-Host "==> 完成: $ZipPath"
