"""OCR 模型下载器测试(v0.7.0 新设计)。

OCR 模型(PP-OCRv6_medium det+rec)不再走 ocr-addon zip,
而是单独从 GitHub Release 的 ocr-models-* tag 拉。
Paddleocr Python 包本身已经打进 .app venv(见 test_packaging_scripts.py)。
"""
from __future__ import annotations

import zipfile
from pathlib import Path
from unittest.mock import patch

import pytest

from launcher.ocr_installer import (
    get_models_url,
    get_ocr_status,
    download_models,
    OcrInstallResult,
)


class TestGetModelsUrl:
    """OCR 模型 zip URL 格式。"""

    def test_get_models_url_macos_arm64(self):
        url = get_models_url("macos", "arm64")
        assert "ocr-models-3.7.0-macos-arm64.zip" in url, (
            f"macOS arm64 模型 URL 应含 ocr-models-3.7.0-macos-arm64.zip,实际: {url}"
        )
        assert url.startswith("https://"), f"URL 必须 https: {url}"

    def test_get_models_url_macos_x86_64(self):
        url = get_models_url("macos", "x86_64")
        assert "ocr-models-3.7.0-macos-x86_64.zip" in url

    def test_get_models_url_windows_x64(self):
        url = get_models_url("windows", "x64")
        assert "ocr-models-3.7.0-windows-x64.zip" in url


class TestDownloadModelsLocalHit:
    """本地已下载 → 跳过下载,直接返回 installed。"""

    def test_skips_when_det_and_rec_exist(self, tmp_path: Path):
        (tmp_path / "data" / "paddlex" / "official_models" / "PP-OCRv6_medium_det").mkdir(
            parents=True
        )
        (tmp_path / "data" / "paddlex" / "official_models" / "PP-OCRv6_medium_rec").mkdir(
            parents=True
        )

        # 应该零网络调用 → 不 monkeypatch 下载函数,会真实尝试下载(会失败,但说明确实
        # 走了网络路径 → 反例)。这里我们用 monkeypatch 监控是否被调用。
        with patch("launcher.ocr_installer._download_file") as mock_dl:
            result = download_models(
                project_root=tmp_path,
                os_name="macos",
                arch="arm64",
            )
        mock_dl.assert_not_called()
        assert result.ok is True
        assert "已安装" in result.message or "skip" in result.message.lower()

    def test_skips_when_only_det_exists(self, tmp_path: Path):
        """只有 det 没有 rec 时仍走下载路径(rec 缺失)。"""
        (tmp_path / "data" / "paddlex" / "official_models" / "PP-OCRv6_medium_det").mkdir(
            parents=True
        )

        with patch("launcher.ocr_installer._download_file") as mock_dl:
            mock_dl.return_value = True
            with patch("launcher.ocr_installer._extract_zip") as mock_extract:
                # 空 zip 让 extract 走空路径,测试只关心"是否调用下载"
                mock_extract.return_value = True
                download_models(
                    project_root=tmp_path,
                    os_name="macos",
                    arch="arm64",
                )
        mock_dl.assert_called_once(), "rec 缺失时应走下载路径"


class TestDownloadModelsExtractsToOfficialModels:
    """下载后模型文件正确解压到 PADDLE_PDX_CACHE_HOME/official_models/。"""

    def test_extracts_to_official_models(self, tmp_path: Path):
        # 创建一个真 zip,内含 official_models/PP-OCRv6_medium_det/ 目录
        models_zip = tmp_path / "models.zip"
        with zipfile.ZipFile(models_zip, "w") as zf:
            zf.writestr("official_models/PP-OCRv6_medium_det/inference.pdiparams", b"fake")
            zf.writestr("official_models/PP-OCRv6_medium_rec/inference.pdiparams", b"fake")

        def mock_download(url, dest, progress_callback=None):
            dest.write_bytes(models_zip.read_bytes())
            return True

        with patch("launcher.ocr_installer._download_file", side_effect=mock_download):
            project_root = tmp_path / "app"
            project_root.mkdir()
            result = download_models(
                project_root=project_root,
                os_name="macos",
                arch="arm64",
            )

        assert result.ok is True
        det_dir = project_root / "data" / "paddlex" / "official_models" / "PP-OCRv6_medium_det"
        rec_dir = project_root / "data" / "paddlex" / "official_models" / "PP-OCRv6_medium_rec"
        assert det_dir.exists(), f"模型解压后 det 应在 {det_dir}"
        assert rec_dir.exists(), f"模型解压后 rec 应在 {rec_dir}"
        assert (det_dir / "inference.pdiparams").exists()


class TestOcrInstallerWheelsRemoved:
    """v0.7.0:OCR Python 包已打进 venv,ocr_installer 不再处理 wheels。"""

    def test_pip_install_wheels_removed(self):
        """_pip_install_wheels 函数已删除。"""
        from launcher import ocr_installer

        assert not hasattr(ocr_installer, "_pip_install_wheels"), (
            "v0.7.0:OCR Python 包打进 venv 后,ocr_installer 不应再有"
            "_pip_install_wheels 函数(避免与 venv pip install 冲突)。"
        )

    def test_download_and_install_removed(self):
        """download_and_install 函数已删除(被 download_models 替代,只下模型)。"""
        from launcher import ocr_installer

        assert not hasattr(ocr_installer, "download_and_install"), (
            "v0.7.0:download_and_install 已删除。"
            "Python 包走 venv pip install,模型走 download_models。"
        )


# ---------------------------------------------------------------------------
# Task 5(2026-08-23 audit):OCR 模型 download_models 写死
# `project_root / "data" / "paddlex"`,但 get_ocr_status 已经支持
# PADDLE_PDX_CACHE_HOME env > .env PADDLE_PDX_CACHE_HOME > DATA_DIR/paddlex
# > project_root/data/paddlex fallback 链。装在 PADDLE_PDX_CACHE_HOME
# 指向 .app 外的用户,装完后 get_ocr_status 看到 official_models 存在
# 但 download_models 把模型装到不同路径,造成"装完判未安装"的诡异 UX。
#
# 修复:抽 `_resolve_paddlex_dir(project_root)` 模块级 helper,
# download_models 与 get_ocr_status 都用它,保证写入路径与读取路径一致。
# ---------------------------------------------------------------------------


class TestResolvePaddlexDir:
    """resolve_paddlex_dir 优先级链(由 launcher.paths 集中提供)。"""

    def test_env_var_takes_priority_over_everything(self, tmp_path, monkeypatch):
        """os.environ['PADDLE_PDX_CACHE_HOME'] > .env PADDLE_PDX_CACHE_HOME > DATA_DIR/paddlex > project_root/data/paddlex。"""
        from launcher.paths import resolve_paddlex_dir

        # .env 设置 DATA_DIR + PADDLE_PDX_CACHE_HOME
        env_file = tmp_path / ".env"
        env_file.write_text(
            "PADDLE_PDX_CACHE_HOME=/from-env-file/paddlex\n"
            "DATA_DIR=/from-env-data-dir\n"
        )
        # os.environ 同时设置 PADDLE_PDX_CACHE_HOME(优先级最高)
        env_target = tmp_path / "from-os-env"
        env_target.mkdir()
        monkeypatch.setenv("PADDLE_PDX_CACHE_HOME", str(env_target))

        resolved = resolve_paddlex_dir(tmp_path)
        assert resolved == env_target, (
            f"os.environ PADDLE_PDX_CACHE_HOME 应胜出,实际 {resolved}"
        )

    def test_env_file_paddlex_over_data_dir_paddlex(self, tmp_path, monkeypatch):
        """.env PADDLE_PDX_CACHE_HOME > .env DATA_DIR/paddlex。"""
        from launcher.paths import resolve_paddlex_dir

        env_file = tmp_path / ".env"
        env_file.write_text(
            "PADDLE_PDX_CACHE_HOME=/from-env-file/paddlex\n"
            "DATA_DIR=/from-env-data-dir\n"
        )
        monkeypatch.delenv("PADDLE_PDX_CACHE_HOME", raising=False)

        resolved = resolve_paddlex_dir(tmp_path)
        # 注意:这里解析出来的 PADDLE_PDX_CACHE_HOME 是绝对路径,等于 "/from-env-file/paddlex"
        # 因为 .env 里 PADDLE_PDX_CACHE_HOME 优先于 DATA_DIR/paddlex
        assert str(resolved) == "/from-env-file/paddlex", (
            f".env PADDLE_PDX_CACHE_HOME 应胜出,实际 {resolved}"
        )

    def test_data_dir_paddlex_when_env_missing(self, tmp_path, monkeypatch):
        """无 PADDLE_PDX_CACHE_HOME 时,fallback 到 DATA_DIR/paddlex。"""
        from launcher.paths import resolve_paddlex_dir

        env_file = tmp_path / ".env"
        env_file.write_text("DATA_DIR=/from-env-data-dir\n")
        monkeypatch.delenv("PADDLE_PDX_CACHE_HOME", raising=False)

        resolved = resolve_paddlex_dir(tmp_path)
        assert str(resolved) == "/from-env-data-dir/paddlex", (
            f"DATA_DIR/paddlex fallback 应生效,实际 {resolved}"
        )

    def test_project_root_default_when_nothing_configured(
        self, tmp_path, monkeypatch,
    ):
        """都没配置时 fallback 到 project_root/data/paddlex。"""
        from launcher.paths import resolve_paddlex_dir

        monkeypatch.delenv("PADDLE_PDX_CACHE_HOME", raising=False)
        # 不写 .env
        resolved = resolve_paddlex_dir(tmp_path)
        assert resolved == tmp_path / "data" / "paddlex", (
            f"无任何配置时应 fallback project_root/data/paddlex,实际 {resolved}"
        )

    def test_data_dir_tilde_expanded(self, tmp_path, monkeypatch):
        """.env DATA_DIR 以 ~ 开头应展开到用户主目录。"""
        from launcher.paths import resolve_paddlex_dir

        env_file = tmp_path / ".env"
        env_file.write_text("DATA_DIR=~/custom-data\n")
        monkeypatch.delenv("PADDLE_PDX_CACHE_HOME", raising=False)

        resolved = resolve_paddlex_dir(tmp_path)
        expected = Path("~/custom-data/paddlex").expanduser()
        assert resolved == expected, (
            f"~ 应展开,实际 {resolved},期望 {expected}"
        )


class TestDownloadModelsUsesResolvedPaddlexDir:
    """download_models 必须走 _resolve_paddlex_dir,而非硬编码 project_root/data/paddlex。

    回归(2026-08-23 audit):装在 PADDLE_PDX_CACHE_HOME 路径下的用户,
    download_models 装到 project_root/data/paddlex,get_ocr_status 查
    PADDLE_PDX_CACHE_HOME 路径找不到 official_models → 报未安装。
    """

    def test_download_models_writes_to_paddle_pdx_cache_home(
        self, tmp_path, monkeypatch,
    ):
        """PADDLE_PDX_CACHE_HOME 指向 .app 外时,模型装到那里,不装到 project_root/data/paddlex。"""
        # 用户配置:模型装到 tmp_path 外的一个独立目录
        external_paddlex = tmp_path / "external-paddlex"
        external_paddlex.mkdir()
        monkeypatch.setenv("PADDLE_PDX_CACHE_HOME", str(external_paddlex))

        # 准备真 zip 让 download_models 走完整解压流程
        import zipfile
        models_zip = tmp_path / "models.zip"
        with zipfile.ZipFile(models_zip, "w") as zf:
            zf.writestr("official_models/PP-OCRv6_medium_det/inference.pdiparams", b"x")
            zf.writestr("official_models/PP-OCRv6_medium_rec/inference.pdiparams", b"x")

        def mock_download(url, dest, progress_callback=None):
            dest.write_bytes(models_zip.read_bytes())
            return True

        from unittest.mock import patch
        project_root = tmp_path / "app"
        project_root.mkdir()

        with patch("launcher.ocr_installer._download_file", side_effect=mock_download):
            result = download_models(
                project_root=project_root,
                os_name="macos",
                arch="arm64",
            )

        assert result.ok is True, f"download_models 应成功,实际: {result.message}"
        # 关键断言:模型应装在 PADDLE_PDX_CACHE_HOME 路径,不是 project_root/data/paddlex
        external_models = external_paddlex / "official_models"
        assert external_models.exists(), (
            f"模型应装到 PADDLE_PDX_CACHE_HOME/official_models/, "
            f"实际目录 {external_models} 不存在"
        )
        assert (external_models / "PP-OCRv6_medium_det").exists(), (
            "det 模型应解压到 PADDLE_PDX_CACHE_HOME/official_models/"
        )
        assert (external_models / "PP-OCRv6_medium_rec").exists(), (
            "rec 模型应解压到 PADDLE_PDX_CACHE_HOME/official_models/"
        )
        # project_root/data/paddlex 不应有 official_models(避免重复占用空间)
        app_models = project_root / "data" / "paddlex" / "official_models"
        assert not app_models.exists(), (
            f"project_root/data/paddlex/official_models 不应被创建; "
            f"应只装到 PADDLE_PDX_CACHE_HOME"
        )


def test_get_addon_url_removed():
    """get_addon_url(ocr-addon-* zip URL 生成)已删除。

    顶层函数形式:历史上被错误缩进进某个 Test 类,实际与具体测试逻辑无关。
    """
    from launcher import ocr_installer

    assert not hasattr(ocr_installer, "get_addon_url"), (
        "v0.7.0:get_addon_url 已删除。ocr-addon-* release 不再使用。"
    )