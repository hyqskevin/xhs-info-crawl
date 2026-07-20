"""OpenCLIAdapter.run 应该用 subprocess.Popen 启动子进程，
并在任务上下文中注册 PID，让 stop 接口能立即 kill。
"""

import subprocess
from unittest.mock import MagicMock

import pytest


@pytest.fixture(autouse=True)
def _clean_registry():
    from pathlib import Path
    p = Path("/tmp/xhs_task_registry.json")
    if p.exists():
        p.unlink()
    yield
    if p.exists():
        p.unlink()


def _settings():
    from app.core.config import Settings
    return Settings()


def test_run_uses_popen_not_subprocess_run(monkeypatch):
    """adapter.run 应该用 Popen 而不是 subprocess.run（便于注册 PID）。"""
    from app.services.opencli_adapter import OpenCLIAdapter

    popen_calls = []
    real_popen = subprocess.Popen

    def fake_popen(*args, **kwargs):
        popen_calls.append((args, kwargs))

        class FakeProc:
            pid = 99999
            stdout = b'[]'
            stderr = b''
            returncode = 0

            def communicate(self, timeout=None):
                return self.stdout, self.stderr

            def wait(self, timeout=None):
                return self.returncode

            def poll(self):
                return self.returncode

        return FakeProc()

    monkeypatch.setattr(subprocess, "Popen", fake_popen)

    adapter = OpenCLIAdapter(_settings())
    result = adapter.run(["xiaohongshu", "whoami"])
    assert popen_calls, "应该至少调用一次 Popen"


def test_run_registers_pid_with_task_id(monkeypatch):
    """当 adapter 在任务上下文里跑 opencli 时，应该把 Popen.pid 注册到 task_registry。

    用 monkeypatch 替换 register/unregister 用来捕获调用。
    """
    from app.services import task_registry
    from app.services.opencli_adapter import OpenCLIAdapter

    calls = {"register": [], "unregister": []}

    def fake_register(task_id, pid, run_token=None):
        calls["register"].append((task_id, pid))

    def fake_unregister(task_id, run_token=None):
        calls["unregister"].append(task_id)

    monkeypatch.setattr(task_registry, "register", fake_register)
    monkeypatch.setattr(task_registry, "unregister", fake_unregister)

    class FakeProc:
        pid = 77777
        stdout = '[]'
        stderr = ''
        returncode = 0

        def communicate(self, timeout=None):
            return self.stdout, self.stderr

        def wait(self, timeout=None):
            return self.returncode

        def poll(self):
            return self.returncode

    monkeypatch.setattr(subprocess, "Popen", lambda *a, **kw: FakeProc())

    adapter = OpenCLIAdapter(_settings())
    adapter.run(["xiaohongshu", "whoami"], task_id=42)

    assert any(t == 42 for t, _ in calls["register"]), f"应该 register task 42, got {calls}"
    assert any(t == 42 for t in calls["unregister"]), f"应该 unregister task 42, got {calls}"


def test_run_unregisters_pid_after_completion(monkeypatch):
    """任务跑完后应该 unregister，避免 stale PID。"""
    from app.services import task_registry
    from app.services.opencli_adapter import OpenCLIAdapter

    class FakeProc:
        pid = 88888
        stdout = '[]'
        stderr = ''
        returncode = 0

        def communicate(self, timeout=None):
            return self.stdout, self.stderr

        def wait(self, timeout=None):
            return self.returncode

        def poll(self):
            return self.returncode

    monkeypatch.setattr(subprocess, "Popen", lambda *a, **kw: FakeProc())

    adapter = OpenCLIAdapter(_settings())
    adapter.run(["xiaohongshu", "whoami"], task_id=99)

    info = task_registry.get(99)
    assert info is None  # 任务完成后应 unregister


def test_run_without_task_id_does_not_register(monkeypatch):
    """非任务上下文跑（不传 task_id）不应注册。"""
    from app.services import task_registry
    from app.services.opencli_adapter import OpenCLIAdapter

    class FakeProc:
        pid = 11111
        stdout = '[]'
        stderr = ''
        returncode = 0

        def communicate(self, timeout=None):
            return self.stdout, self.stderr

        def wait(self, timeout=None):
            return self.returncode

        def poll(self):
            return self.returncode

    monkeypatch.setattr(subprocess, "Popen", lambda *a, **kw: FakeProc())

    adapter = OpenCLIAdapter(_settings())
    adapter.run(["xiaohongshu", "whoami"])

    # 没有 task_id，不应有注册
    assert task_registry.get(123) is None


def test_run_handles_subprocess_error(monkeypatch):
    """子进程返回非 0 时，adapter 抛 OpenCLIError，但仍要 unregister。"""
    from app.services import task_registry
    from app.services.opencli_adapter import OpenCLIAdapter
    from app.services.crawler import OpenCLIError

    class FakeProc:
        pid = 22222
        stdout = ''
        stderr = 'some error'
        returncode = 1

        def communicate(self, timeout=None):
            return self.stdout, self.stderr

        def wait(self, timeout=None):
            return self.returncode

        def poll(self):
            return self.returncode

    monkeypatch.setattr(subprocess, "Popen", lambda *a, **kw: FakeProc())

    adapter = OpenCLIAdapter(_settings())
    with pytest.raises(OpenCLIError):
        adapter.run(["xiaohongshu", "whoami"], task_id=55)

    # 即使报错，也应 unregister
    assert task_registry.get(55) is None


def test_run_registers_pid_with_execution_token(monkeypatch):
    from app.services import task_registry
    from app.services.opencli_adapter import OpenCLIAdapter

    calls = {"register": [], "unregister": []}
    monkeypatch.setattr(
        task_registry,
        "register",
        lambda task_id, pid, run_token=None: calls["register"].append((task_id, run_token, pid)),
    )
    monkeypatch.setattr(
        task_registry,
        "unregister",
        lambda task_id, run_token=None: calls["unregister"].append((task_id, run_token)),
    )

    class FakeProc:
        pid = 33333
        returncode = 0

        def communicate(self, timeout=None):
            return "[]", ""

    monkeypatch.setattr(subprocess, "Popen", lambda *a, **kw: FakeProc())

    adapter = OpenCLIAdapter(_settings())
    adapter.bind_task(77, "execution-token")
    adapter.run(["xiaohongshu", "whoami"])

    assert calls["register"] == [(77, "execution-token", 33333)]
    assert calls["unregister"] == [(77, "execution-token")]
