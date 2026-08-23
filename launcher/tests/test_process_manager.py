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


def test_popen_uses_start_new_session(tmp_path, monkeypatch):
    """start_service 启动 Popen 时传 start_new_session=True(避免 SIGHUP 链杀)。

    关联 spec: docs/superpowers/specs/2026-08-16-launcher-cleanup-on-exit-design.md § 1
    """
    if sys.platform == "win32":
        pytest.skip("start_new_session 是 Unix 概念,Windows 用 CREATE_NEW_PROCESS_GROUP")

    captured_kwargs = {}

    def fake_popen(cmd, **kwargs):
        captured_kwargs.update(kwargs)
        from unittest.mock import MagicMock
        m = MagicMock()
        m.pid = 12345
        m.poll.return_value = None
        m.wait.return_value = 0
        return m

    monkeypatch.setattr("subprocess.Popen", fake_popen)

    pm = ProcessManager(project_root=tmp_path, venv_python=Path(sys.executable))
    pm._commands = {
        "api": [sys.executable, "-c", "import time; time.sleep(10)"],
        "worker": [sys.executable, "-c", "import time; time.sleep(10)"],
        "beat": [sys.executable, "-c", "import time; time.sleep(10)"],
        "web": [sys.executable, "-c", "import time; time.sleep(10)"],
    }
    pm.start_service("api")

    assert captured_kwargs.get("start_new_session") is True


def test_cleanup_idempotent(tmp_path):
    """cleanup 可重复调用,子进程不会被重复 SIGTERM。"""
    pm = ProcessManager(project_root=tmp_path, venv_python=Path(sys.executable))
    pm._commands = {
        "api": [sys.executable, "-c", "import time; time.sleep(10)"],
        "worker": [sys.executable, "-c", "import time; time.sleep(10)"],
        "beat": [sys.executable, "-c", "import time; time.sleep(10)"],
        "web": [sys.executable, "-c", "import time; time.sleep(10)"],
    }
    pm.start_service("api")
    pm.start_service("worker")
    time.sleep(0.3)

    pm.cleanup()
    pm.cleanup()
    pm.cleanup()

    assert pm._cleaned is True
    assert pm.get_status()["api"]["state"] == "stopped"
    assert pm.get_status()["worker"]["state"] == "stopped"


def test_stop_service_kills_after_timeout(tmp_path, monkeypatch):
    """stop_service:terminate 后 wait 超时 → SIGKILL 整个进程组。"""
    import signal as sig_mod
    from unittest.mock import MagicMock

    killpg_calls = []
    monkeypatch.setattr("os.killpg", lambda pgid, s: killpg_calls.append((pgid, s)))

    proc = MagicMock()
    proc.pid = 4242
    proc.poll.return_value = None
    import subprocess as sp
    proc.wait.side_effect = [sp.TimeoutExpired(cmd=["sleep"], timeout=0.1), 0]

    pm = ProcessManager(project_root=tmp_path, venv_python=Path(sys.executable))
    pm._processes["stub"] = proc
    pm.stop_service("stub", timeout=0.1)

    proc.terminate.assert_called_once()
    proc.kill.assert_not_called()
    assert killpg_calls == [(4242, sig_mod.SIGKILL)]


def test_kill_process_group_uses_killpg(tmp_path, monkeypatch):
    """_kill_process_group 用 os.killpg(pgid, SIGKILL) 杀整个进程组(Unix)。"""
    if sys.platform == "win32":
        pytest.skip("Windows 走 taskkill /T,不走 os.killpg")
    import signal as sig_mod

    killpg_calls = []
    monkeypatch.setattr("os.killpg", lambda pgid, s: killpg_calls.append((pgid, s)))

    pm = ProcessManager(project_root=tmp_path, venv_python=Path(sys.executable))
    pm._kill_process_group(7777)
    assert killpg_calls == [(7777, sig_mod.SIGKILL)]


# ──────────────────────────────────────────────────────────────────────
# v0.7.0+5 launcher 监控缺口测试
# 关联 spec: docs/superpowers/specs/2026-08-23-migration-0028-sqlite-current-timestamp-binding-design.md §3.1+3.3
# ──────────────────────────────────────────────────────────────────────


def test_start_service_writes_launch_marker(tmp_path):
    """start_service 在日志头写 `=== launched at <iso8601> pid=<pid> ===` 分隔符。"""
    pm = ProcessManager(project_root=tmp_path, venv_python=Path(sys.executable))
    pm._commands = {
        "api": [sys.executable, "-c", "import time; time.sleep(10)"],
        "worker": [sys.executable, "-c", "import time; time.sleep(10)"],
        "beat": [sys.executable, "-c", "import time; time.sleep(10)"],
    }
    pm.start_service("api")
    try:
        log_file = tmp_path / "data" / "logs" / "api.log"
        text = log_file.read_text()
        assert "=== launched at " in text
        assert "pid=" in text
        assert "pid=__PID__" not in text
    finally:
        pm.stop_all()


def test_get_status_includes_last_launch_at(tmp_path):
    """get_status 返回 last_launch_at ISO 字符串。"""
    pm = ProcessManager(project_root=tmp_path, venv_python=Path(sys.executable))
    pm._commands = {
        "api": [sys.executable, "-c", "import time; time.sleep(10)"],
        "worker": [sys.executable, "-c", "import time; time.sleep(10)"],
        "beat": [sys.executable, "-c", "import time; time.sleep(10)"],
    }
    pm.start_service("api")
    try:
        status = pm.get_status()
        assert status["api"]["last_launch_at"] is not None
        assert "T" in status["api"]["last_launch_at"]
    finally:
        pm.stop_all()


def test_get_status_exposes_last_error_on_crash(tmp_path):
    """crashed 时 last_error = stderr 末尾 8 行,用户能直接看到真错误。"""
    pm = ProcessManager(project_root=tmp_path, venv_python=Path(sys.executable))
    pm._commands = {
        "api": [
            sys.executable,
            "-c",
            "import sys; sys.stderr.write('migration 0028 sqlite3 binding error\\n'); "
            "sys.stderr.write('type current_timestamp is not supported\\n'); "
            "sys.exit(1)",
        ],
        "worker": [sys.executable, "-c", "import time; time.sleep(10)"],
        "beat": [sys.executable, "-c", "import time; time.sleep(10)"],
    }
    pm.start_service("api")
    time.sleep(1.0)
    status = pm.get_status()
    assert status["api"]["state"] == "crashed"
    assert status["api"]["last_error"] is not None
    assert "sqlite3" in (status["api"]["last_error"] or "")
    assert "current_timestamp" in (status["api"]["last_error"] or "")


def test_get_status_clears_last_error_on_restart(tmp_path):
    """重启 api 后 last_error 应清空。"""
    pm = ProcessManager(project_root=tmp_path, venv_python=Path(sys.executable))
    pm._commands = {
        "api": [sys.executable, "-c", "import sys; sys.stderr.write('first fail\\n'); sys.exit(1)"],
        "worker": [sys.executable, "-c", "import time; time.sleep(10)"],
        "beat": [sys.executable, "-c", "import time; time.sleep(10)"],
    }
    pm.start_service("api")
    time.sleep(1.0)
    assert pm.get_status()["api"]["last_error"] is not None

    pm._commands["api"] = [sys.executable, "-c", "import time; time.sleep(10)"]
    pm.restart_service("api")
    time.sleep(0.5)
    status = pm.get_status()
    assert status["api"]["state"] == "running"
    assert status["api"]["last_error"] is None
    pm.stop_all()