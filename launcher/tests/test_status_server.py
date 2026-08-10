"""状态服务测试。"""
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest
from fastapi.testclient import TestClient

from launcher.status_server import StatusServer


@pytest.fixture
def status_server(tmp_path):
    """构造一个 StatusServer,用 mock ProcessManager。"""
    pm = MagicMock()
    pm.get_status.return_value = {
        "api": {"state": "running", "pid": 1234},
        "worker": {"state": "running", "pid": 1235},
        "beat": {"state": "running", "pid": 1236},
    }
    pm.get_logs_tail.return_value = ["[14:30:01] API started"]
    server = StatusServer(process_manager=pm, project_root=tmp_path, venv_python=Path(sys.executable))
    return server


def test_get_status(status_server):
    """GET /status 返回三服务状态。"""
    app = status_server.app
    with TestClient(app) as client:
        resp = client.get("/status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["api"]["state"] == "running"
        assert data["worker"]["state"] == "running"
        assert data["beat"]["state"] == "running"


def test_restart_service(status_server):
    """POST /service/{name}/restart 重启指定服务。"""
    app = status_server.app
    with TestClient(app) as client:
        resp = client.post("/service/api/restart")
        assert resp.status_code == 200
        status_server.process_manager.restart_service.assert_called_once_with("api")


def test_stop_all(status_server):
    """POST /service/all/stop 停止所有服务。"""
    app = status_server.app
    with TestClient(app) as client:
        resp = client.post("/service/all/stop")
        assert resp.status_code == 200
        status_server.process_manager.stop_all.assert_called_once()


def test_opencli_test(status_server):
    """GET /opencli/test 测试 OpenCLI 连接。"""
    app = status_server.app
    mock_result = MagicMock()
    mock_result.ok = True
    mock_result.version = "1.8.6"
    mock_result.reason = ""
    mock_result.message = "连接正常"
    with patch("launcher.status_server.check_opencli", return_value=mock_result):
        with TestClient(app) as client:
            resp = client.get("/opencli/test")
            assert resp.status_code == 200
            data = resp.json()
            assert data["ok"] is True
            assert "1.8.6" in data["version"]


def test_opencli_download_url(status_server):
    """GET /opencli/download-url 返回下载 URL。"""
    app = status_server.app
    with TestClient(app) as client:
        resp = client.get("/opencli/download-url")
        assert resp.status_code == 200
        data = resp.json()
        assert data["url"].startswith("https://")
        assert "opencli" in data["url"].lower()


def test_ocr_status_not_installed(status_server):
    """GET /ocr/status 返回未安装状态。"""
    app = status_server.app
    with TestClient(app) as client:
        resp = client.get("/ocr/status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "not_installed"


def test_ocr_status_installed(status_server, tmp_path):
    """GET /ocr/status 返回已安装状态。"""
    (tmp_path / "data" / "paddlex" / "official_models").mkdir(parents=True)
    (tmp_path / "data" / "paddlex" / "official_models" / "model.dat").touch()
    (tmp_path / "data" / "paddlex" / ".ocr_addon_version").write_text("version: 3.7.0\n")
    app = status_server.app
    with TestClient(app) as client:
        resp = client.get("/ocr/status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "installed"
        assert data["version"] == "3.7.0"


def test_ocr_install_triggers_download(status_server, tmp_path):
    """POST /ocr/install 触发下载安装(异步)。"""
    app = status_server.app
    mock_result = MagicMock()
    mock_result.ok = True
    mock_result.message = "安装成功"
    mock_result.version = "3.7.0"
    with patch("launcher.status_server.download_and_install", return_value=mock_result):
        with TestClient(app) as client:
            resp = client.post("/ocr/install")
            assert resp.status_code == 200
            data = resp.json()
            assert data["ok"] is True or data["message"] == "安装已启动"


def test_logs_tail(status_server):
    """GET /logs/tail 返回最近日志。"""
    app = status_server.app
    with TestClient(app) as client:
        resp = client.get("/logs/tail?lines=10")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data["lines"], list)
