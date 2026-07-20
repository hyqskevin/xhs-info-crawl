import subprocess

import pytest

from app.core.config import Settings
from app.services import task_registry
from app.services.opencli_adapter import OpenCLIAdapter
from app.services.crawler import VerificationRequired


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


def test_guard_failure_after_process_exit_wins_over_killed_return_code(monkeypatch) -> None:
    stopped = False

    class ExternallyKilledProc(FakeProc):
        def communicate(self, timeout=None):
            nonlocal stopped
            self.communicate_calls += 1
            self.returncode = -9
            stopped = True
            return "", "opencli process killed"

    proc = ExternallyKilledProc()
    monkeypatch.setattr(subprocess, "Popen", lambda *args, **kwargs: proc)

    def guard() -> None:
        if stopped:
            raise ExecutionStoppedForTest()

    adapter = OpenCLIAdapter(Settings())
    adapter.bind_task(14, "run-token", execution_guard=guard)

    with pytest.raises(ExecutionStoppedForTest):
        adapter.run(["xiaohongshu", "whoami"])

    assert proc.communicate_calls == 1
    assert task_registry.get(14, "run-token") is None


def test_unbound_adapter_remains_compatible(monkeypatch) -> None:
    proc = FakeProc()
    monkeypatch.setattr(subprocess, "Popen", lambda *args, **kwargs: proc)

    assert OpenCLIAdapter(Settings()).run(["xiaohongshu", "whoami"]) == []


def test_search_closes_session_tab_when_middle_command_stops(monkeypatch) -> None:
    adapter = OpenCLIAdapter(Settings())
    calls: list[tuple[list[str], dict]] = []

    def fake_run(args, **kwargs):
        calls.append((args, kwargs))
        if args[:2] == ["xiaohongshu", "whoami"]:
            return {"logged_in": True}
        if args[:3] == ["browser", adapter.session, "open"]:
            return {"opened": True}
        if args[:3] == ["browser", adapter.session, "close"]:
            return {"closed": True}
        raise ExecutionStoppedForTest()

    monkeypatch.setattr(adapter, "run", fake_run)

    with pytest.raises(ExecutionStoppedForTest):
        adapter.search_recent("宁波 活动", "一周内")

    close_calls = [
        (args, kwargs)
        for args, kwargs in calls
        if args[:3] == ["browser", adapter.session, "close"]
    ]
    assert close_calls == [
        (["browser", adapter.session, "close"], {"enforce_execution": False, "timeout": 10})
    ]


def test_search_keeps_session_tab_open_when_verification_is_required(monkeypatch) -> None:
    adapter = OpenCLIAdapter(Settings())
    calls: list[list[str]] = []

    def fake_run(args, **kwargs):
        calls.append(args)
        if args[:3] == ["browser", adapter.session, "click"]:
            adapter._preserve_browser_tab = True
            raise VerificationRequired("检测到小红书安全验证")
        return {} if args[:2] == ["xiaohongshu", "whoami"] else True

    monkeypatch.setattr(adapter, "run", fake_run)

    with pytest.raises(VerificationRequired):
        adapter.search_recent("宁波 活动")

    assert not any(args[:3] == ["browser", adapter.session, "close"] for args in calls)


def test_note_attempts_cleanup_when_open_command_is_interrupted(monkeypatch) -> None:
    adapter = OpenCLIAdapter(Settings())
    calls: list[tuple[list[str], dict]] = []

    def fake_run(args, **kwargs):
        calls.append((args, kwargs))
        if args[:2] == ["xiaohongshu", "whoami"]:
            return {"logged_in": True}
        if args[:3] == ["browser", adapter.session, "close"]:
            return {"closed": True}
        if args[:3] == ["browser", adapter.session, "open"]:
            raise ExecutionStoppedForTest()
        return {}

    monkeypatch.setattr(adapter, "run", fake_run)

    with pytest.raises(ExecutionStoppedForTest):
        adapter.note("https://www.xiaohongshu.com/explore/note-id")

    assert any(
        args[:3] == ["browser", adapter.session, "close"] for args, _ in calls
    )


def test_cleanup_failure_uses_warning_sink_without_masking_result(monkeypatch) -> None:
    warnings = []
    adapter = OpenCLIAdapter(Settings())
    adapter.bind_task(14, "run-token", warning_sink=warnings.append)

    def fake_run(args, **kwargs):
        if args[:2] == ["xiaohongshu", "whoami"]:
            return {"logged_in": True}
        if args[:3] == ["browser", adapter.session, "open"]:
            return {"opened": True}
        if args[:3] == ["browser", adapter.session, "eval"]:
            script = args[3]
            if "optionExists" in script or "targetText" in script:
                return True
            return []
        if args[:3] == ["browser", adapter.session, "close"]:
            raise RuntimeError("close failed")
        return True

    monkeypatch.setattr(adapter, "run", fake_run)

    assert adapter.search_recent("宁波 活动", "不限") == []
    assert len(warnings) == 1
    assert "浏览器标签页清理失败" in warnings[0]
