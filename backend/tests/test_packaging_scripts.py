"""打包脚本与发布工作流结构验证。

不实际执行打包(需要 GitHub Actions runner),只验证:
- 依赖清单文件存在且内容正确
- 打包脚本存在且结构正确(shebang、关键步骤)
- GitHub Actions 工作流存在且 job 结构正确
"""
from __future__ import annotations

from pathlib import Path

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
        # Windows 脚本用反斜杠,接受 / 或 \ 两种分隔符
        assert "launcher\\requirements.txt" in content or "launcher/requirements.txt" in content

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
