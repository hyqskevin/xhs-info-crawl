"""OCR 增强包安装器测试。"""
import hashlib
from pathlib import Path
from unittest.mock import patch

import pytest

from launcher.ocr_installer import (
    get_addon_url,
    get_ocr_status,
    download_and_install,
    OcrInstallResult,
    MIN_DISK_BYTES,
)


def test_get_addon_url_macos_arm64():
    """macOS arm64 的下载 URL。"""
    url = get_addon_url("macos", "arm64", "3.7.0")
    assert "paddleocr-addon-3.7.0-macos-arm64.zip" in url
    assert url.startswith("https://")


def test_get_addon_url_windows_x64():
    """Windows x64 的下载 URL。"""
    url = get_addon_url("windows", "x64", "3.7.0")
    assert "paddleocr-addon-3.7.0-windows-x64.zip" in url


def test_get_ocr_status_not_installed(tmp_path: Path):
    """未安装时 status=not_installed。"""
    status = get_ocr_status(project_root=tmp_path)
    assert status["status"] == "not_installed"


def test_get_ocr_status_installed(tmp_path: Path):
    """已安装(有 official_models 目录 + VERSION 文件)时 status=installed。"""
    (tmp_path / "data" / "paddlex" / "official_models").mkdir(parents=True)
    (tmp_path / "data" / "paddlex" / "official_models" / "model.dat").touch()
    (tmp_path / "data" / "paddlex" / ".ocr_addon_version").write_text("version: 3.7.0\n")

    status = get_ocr_status(project_root=tmp_path)
    assert status["status"] == "installed"
    assert status["version"] == "3.7.0"


def test_get_ocr_status_installing(tmp_path: Path):
    """安装中(有 .installing 标记)时 status=installing。"""
    (tmp_path / "data" / "paddlex").mkdir(parents=True)
    (tmp_path / "data" / "paddlex" / ".installing").touch()

    status = get_ocr_status(project_root=tmp_path)
    assert status["status"] == "installing"


def test_download_and_install_success(tmp_path: Path, monkeypatch):
    """下载安装成功(用 mock 模拟下载和解压)。"""
    fake_zip_content = b"fake zip bytes"

    def mock_download(url, dest, progress_callback=None):
        dest.write_bytes(fake_zip_content)
        return True

    def mock_sha256(path):
        return hashlib.sha256(fake_zip_content).hexdigest()

    def mock_extract(zip_path, dest_dir):
        (dest_dir / "data" / "paddlex" / "official_models").mkdir(parents=True)
        (dest_dir / "data" / "paddlex" / "official_models" / "model.dat").touch()
        (dest_dir / "data" / "paddlex" / ".ocr_addon_version").write_text("version: 3.7.0\n")
        (dest_dir / "wheels").mkdir()
        (dest_dir / "wheels" / "paddleocr-3.7.0-py3-none-any.whl").touch()
        return True

    def mock_pip_install(wheels_dir, venv_python):
        return True

    monkeypatch.setattr("launcher.ocr_installer._download_file", mock_download)
    monkeypatch.setattr("launcher.ocr_installer._sha256", mock_sha256)
    monkeypatch.setattr("launcher.ocr_installer._extract_zip", mock_extract)
    monkeypatch.setattr("launcher.ocr_installer._pip_install_wheels", mock_pip_install)

    result = download_and_install(
        project_root=tmp_path,
        os_name="macos",
        arch="arm64",
        version="3.7.0",
        venv_python=tmp_path / "python",
    )

    assert result.ok is True
    assert (tmp_path / "data" / "paddlex" / "official_models").exists()
    assert (tmp_path / "data" / "paddlex" / ".ocr_addon_version").exists()


def test_download_and_install_disk_space_check(tmp_path: Path, monkeypatch):
    """磁盘空间不足时返回失败。"""
    def mock_disk_free(path):
        return 100 * 1024 * 1024  # 100 MB

    monkeypatch.setattr("launcher.ocr_installer._get_disk_free_bytes", mock_disk_free)

    result = download_and_install(
        project_root=tmp_path,
        os_name="macos",
        arch="arm64",
        version="3.7.0",
        venv_python=tmp_path / "python",
    )

    assert result.ok is False
    assert "磁盘空间不足" in result.message


def test_download_and_install_sha256_mismatch(tmp_path: Path, monkeypatch):
    """SHA256 校验失败时回滚。"""
    fake_zip_content = b"fake zip bytes"

    def mock_download(url, dest, progress_callback=None):
        dest.write_bytes(fake_zip_content)
        return True

    def mock_sha256(path):
        return "wronghash"

    monkeypatch.setattr("launcher.ocr_installer._download_file", mock_download)
    monkeypatch.setattr("launcher.ocr_installer._sha256", mock_sha256)

    result = download_and_install(
        project_root=tmp_path,
        os_name="macos",
        arch="arm64",
        version="3.7.0",
        venv_python=tmp_path / "python",
        expected_sha256="expectedhash",
    )

    assert result.ok is False
    assert "SHA256" in result.message
