"""进程管理器测试。"""
import sys
import time
from pathlib import Path

import pytest

from launcher.process_manager import ProcessManager


def test_process_manager_initial_state(tmp_path):
    """初始状态:三个服务都是 stopped。"""
    pm = ProcessManager(project_root=tmp_path, venv_python=Path(sys.executable))
    status = pm.get_status()
    assert status["api"]["state"] == "stopped"
    assert status["worker"]["state"] == "stopped"
    assert status["beat"]["state"] == "stopped"


def test_process_manager_start_api(tmp_path):
    """启动 API 进程(用 sleep 模拟)。"""
    pm = ProcessManager(project_root=tmp_path, venv_python=Path(sys.executable))
    # 用 sleep 命令模拟服务进程
    pm._commands = {
        "api": [sys.executable, "-c", "import time; time.sleep(10)"],
        "worker": [sys.executable, "-c", "import time; time.sleep(10)"],
        "beat": [sys.executable, "-c", "import time; time.sleep(10)"],
    }
    pm.start_service("api")
    time.sleep(0.5)
    status = pm.get_status()
    assert status["api"]["state"] == "running"
    pm.stop_all()
    time.sleep(0.5)
    assert pm.get_status()["api"]["state"] == "stopped"


def test_process_manager_stop_all(tmp_path):
    """stop_all 停止所有进程。"""
    pm = ProcessManager(project_root=tmp_path, venv_python=Path(sys.executable))
    pm._commands = {
        "api": [sys.executable, "-c", "import time; time.sleep(10)"],
        "worker": [sys.executable, "-c", "import time; time.sleep(10)"],
        "beat": [sys.executable, "-c", "import time; time.sleep(10)"],
    }
    pm.start_service("api")
    pm.start_service("worker")
    pm.start_service("beat")
    time.sleep(0.5)
    pm.stop_all()
    time.sleep(0.5)
    status = pm.get_status()
    assert status["api"]["state"] == "stopped"
    assert status["worker"]["state"] == "stopped"
    assert status["beat"]["state"] == "stopped"


def test_process_manager_restart_service(tmp_path):
    """restart_service 重启单个服务。"""
    pm = ProcessManager(project_root=tmp_path, venv_python=Path(sys.executable))
    pm._commands = {
        "api": [sys.executable, "-c", "import time; time.sleep(10)"],
        "worker": [sys.executable, "-c", "import time; time.sleep(10)"],
        "beat": [sys.executable, "-c", "import time; time.sleep(10)"],
    }
    pm.start_service("api")
    time.sleep(0.5)
    pm.restart_service("api")
    time.sleep(0.5)
    assert pm.get_status()["api"]["state"] == "running"
    pm.stop_all()


def test_process_manager_logs_written(tmp_path):
    """子进程 stdout/stderr 写到日志文件。"""
    pm = ProcessManager(project_root=tmp_path, venv_python=Path(sys.executable))
    pm._commands = {
        "api": [sys.executable, "-c", "print('API started'); import time; time.sleep(10)"],
        "worker": [sys.executable, "-c", "import time; time.sleep(10)"],
        "beat": [sys.executable, "-c", "import time; time.sleep(10)"],
    }
    pm.start_service("api")
    time.sleep(1)
    log_file = tmp_path / "data" / "logs" / "api.log"
    assert log_file.exists()
    assert "API started" in log_file.read_text()
    pm.stop_all()


def test_process_manager_dead_process_detected(tmp_path):
    """进程退出后状态变 stopped 或 crashed。"""
    pm = ProcessManager(project_root=tmp_path, venv_python=Path(sys.executable))
    pm._commands = {
        "api": [sys.executable, "-c", "print('exit immediately')"],
        "worker": [sys.executable, "-c", "import time; time.sleep(10)"],
        "beat": [sys.executable, "-c", "import time; time.sleep(10)"],
    }
    pm.start_service("api")
    time.sleep(1)
    status = pm.get_status()
    assert status["api"]["state"] in ("stopped", "crashed")


def test_process_manager_get_logs_tail(tmp_path):
    """get_logs_tail 返回最近日志。"""
    pm = ProcessManager(project_root=tmp_path, venv_python=Path(sys.executable))
    pm._commands = {
        "api": [sys.executable, "-c", "print('log line 1'); print('log line 2'); import time; time.sleep(10)"],
        "worker": [sys.executable, "-c", "import time; time.sleep(10)"],
        "beat": [sys.executable, "-c", "import time; time.sleep(10)"],
    }
    pm.start_service("api")
    time.sleep(1)
    logs = pm.get_logs_tail(lines=10)
    assert any("log line" in line for line in logs)
    pm.stop_all()
