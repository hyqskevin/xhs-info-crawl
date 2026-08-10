"""OpenCLI 连接测试。"""
import subprocess
from unittest.mock import patch, MagicMock

from launcher.opencli_checker import check_opencli, OpenCLIResult, OPENCLI_DOWNLOAD_URL


def test_opencli_download_url_valid():
    """download url 是 opencli 官方下载页。"""
    assert "opencli" in OPENCLI_DOWNLOAD_URL.lower()
    assert OPENCLI_DOWNLOAD_URL.startswith("https://")


def test_check_opencli_success():
    """opencli doctor 成功时返回 ok=true。"""
    mock_proc = MagicMock()
    mock_proc.returncode = 0
    mock_proc.stdout = "opencli version 1.8.6\ndaemon: ok\nextension: connected\n"
    mock_proc.stderr = ""

    with patch("launcher.opencli_checker.subprocess.run", return_value=mock_proc):
        result = check_opencli()

    assert result.ok is True
    assert "1.8.6" in result.version
    assert result.reason == ""


def test_check_opencli_not_installed():
    """opencli 命令不存在时返回 not_installed。"""
    with patch("launcher.opencli_checker.subprocess.run", side_effect=FileNotFoundError("not found")):
        result = check_opencli()

    assert result.ok is False
    assert result.reason == "not_installed"
    assert "未安装" in result.message


def test_check_opencli_daemon_not_running():
    """opencli doctor 返回 daemon not running。"""
    mock_proc = MagicMock()
    mock_proc.returncode = 1
    mock_proc.stdout = ""
    mock_proc.stderr = "daemon not running\n"

    with patch("launcher.opencli_checker.subprocess.run", return_value=mock_proc):
        result = check_opencli()

    assert result.ok is False
    assert result.reason == "daemon_not_running"
    assert "OpenCLIApp 未启动" in result.message


def test_check_opencli_extension_not_connected():
    """opencli doctor 返回 extension not connected。"""
    mock_proc = MagicMock()
    mock_proc.returncode = 1
    mock_proc.stdout = ""
    mock_proc.stderr = "extension not connected\n"

    with patch("launcher.opencli_checker.subprocess.run", return_value=mock_proc):
        result = check_opencli()

    assert result.ok is False
    assert result.reason == "extension_not_connected"
    assert "Chrome 扩展" in result.message


def test_check_opencli_timeout():
    """opencli doctor 超时。"""
    with patch("launcher.opencli_checker.subprocess.run", side_effect=subprocess.TimeoutExpired(cmd="opencli", timeout=10)):
        result = check_opencli()

    assert result.ok is False
    assert result.reason == "timeout"
    assert "超时" in result.message


def test_check_opencli_other_failure():
    """opencli doctor 其他失败。"""
    mock_proc = MagicMock()
    mock_proc.returncode = 1
    mock_proc.stdout = ""
    mock_proc.stderr = "some unknown error\n"

    with patch("launcher.opencli_checker.subprocess.run", return_value=mock_proc):
        result = check_opencli()

    assert result.ok is False
    assert result.reason == "unknown_error"
    assert "some unknown error" in result.message
