import subprocess

import pytest

from app.core.config import Settings
from app.services import task_registry
from app.services.opencli_adapter import OpenCLIAdapter


class ExecutionStoppedForTest(Exception):
    pass


class FakeProc:
    pid = 45678

    def __init__(self) -> None:
        self.returncode: int | None = None
        self.killed = False
        self.communicate_calls = 0

    def communicate(self, timeout=None):
        self.communicate_calls += 1
        if self.returncode is None:
            self.returncode = 0
        return "[]", ""

    def poll(self):
        return self.returncode

    def kill(self) -> None:
        self.killed = True
        self.returncode = -9


@pytest.fixture(autouse=True)
def clean_registry(monkeypatch, tmp_path):
    monkeypatch.setattr(task_registry, "REGISTRY_PATH", tmp_path / "registry.json")


def test_guard_failure_before_popen_starts_no_process(monkeypatch) -> None:
    popen_calls = []
    monkeypatch.setattr(subprocess, "Popen", lambda *args, **kwargs: popen_calls.append(args))
    adapter = OpenCLIAdapter(Settings())
    adapter.bind_task(
        12,
        "run-token",
        execution_guard=lambda: (_ for _ in ()).throw(ExecutionStoppedForTest()),
    )

    with pytest.raises(ExecutionStoppedForTest):
        adapter.run(["xiaohongshu", "whoami"])

    assert popen_calls == []
    assert task_registry.get(12, "run-token") is None


def test_guard_failure_after_registration_kills_new_process(monkeypatch) -> None:
    proc = FakeProc()
    monkeypatch.setattr(subprocess, "Popen", lambda *args, **kwargs: proc)
    checks = 0

    def guard() -> None:
        nonlocal checks
        checks += 1
        if checks == 2:
            raise ExecutionStoppedForTest()

    adapter = OpenCLIAdapter(Settings())
    adapter.bind_task(13, "run-token", execution_guard=guard)

    with pytest.raises(ExecutionStoppedForTest):
        adapter.run(["xiaohongshu", "whoami"])

    assert checks == 2
    assert proc.killed is True
    assert proc.communicate_calls == 1
    assert task_registry.get(13, "run-token") is None


def test_unbound_adapter_remains_compatible(monkeypatch) -> None:
    proc = FakeProc()
    monkeypatch.setattr(subprocess, "Popen", lambda *args, **kwargs: proc)

    assert OpenCLIAdapter(Settings()).run(["xiaohongshu", "whoami"]) == []
