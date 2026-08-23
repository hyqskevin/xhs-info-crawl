"""测试 launcher.orphan_cleanup。

测试策略：用 subprocess.Popen 启动 sleep 60 的子进程,然后用 os.execvp 或
`/bin/sh -c "exec -a 'fake-cmdline' sleep 60"` 改它的命令行显示(伪 celery 命令行)。
这样 cleanup_orphan_celery 通过 ps 看到的命令行就是预期的,杀的是子进程本身。

cleanup_orphan_celery 必须:
- 找不到匹配 → 返回 {"terminated":[],"killed":[]};日志写入
- 找到匹配(除自己) → SIGTERM 杀;5 秒未退 → SIGKILL 兜底
- 找到自己 PID → 排除不杀
- 日志文件追加不覆盖
"""
from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest

from launcher.orphan_cleanup import cleanup_orphan_celery


@pytest.fixture
def log_path(tmp_path: Path) -> Path:
    return tmp_path / "cleanup.log"


def _spawn_fake_worker(role: str, pgid: int | None = None) -> int:
    """启动一个伪装成 celery worker 的 sleep 进程,返回 PID。

    pgid: 若指定则把子进程放到新的进程组(setpgid),模拟 launcher start_new_session=True。
    """
    cmdline_marker = f"celery -A app.tasks.celery_app {role}"
    # /bin/sh -c "exec -a 'fake cmdline' sleep 60"
    # exec -a 让 ps 显示的命令行变成 fake cmdline
    pid = subprocess.Popen(
        ["/bin/sh", "-c", f"exec -a {cmdline_marker!r} sleep 60"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        preexec_fn=os.setsid if pgid is not None else None,
    ).pid
    # 等待一下确保 exec 完成
    time.sleep(0.1)
    return pid


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except (ProcessLookupError, PermissionError):
        return False


def test_no_match_returns_empty(log_path: Path) -> None:
    """系统无 worker → 返回 terminated=[], killed=[];日志写入。"""
    result = cleanup_orphan_celery("worker", log_path, timeout_seconds=1.0)
    assert result == {"terminated": [], "killed": []}
    assert log_path.exists()
    content = log_path.read_text()
    assert "cleanup_start" in content
    assert "cleanup_done" in content
    assert "terminated=[]" in content


def test_kills_matching_worker_excludes_self(log_path: Path) -> None:
    """启动伪 worker → cleanup 杀掉它;调用方自己 PID 不被杀。"""
    # 启动 2 个伪 worker
    pid_a = _spawn_fake_worker("worker")
    pid_b = _spawn_fake_worker("worker")
    my_pid = os.getpid()

    try:
        result = cleanup_orphan_celery("worker", log_path, timeout_seconds=2.0)
        assert pid_a in result["terminated"] or pid_a in result["killed"]
        assert pid_b in result["terminated"] or pid_b in result["killed"]
        assert my_pid not in result["terminated"]
        assert my_pid not in result["killed"]
        # 给系统一点时间回收
        time.sleep(0.5)
        assert not _pid_alive(pid_a)
        assert not _pid_alive(pid_b)
    finally:
        for p in (pid_a, pid_b):
            try:
                os.kill(p, signal.SIGKILL)
            except ProcessLookupError:
                pass


def test_worker_and_beat_are_independent(log_path: Path) -> None:
    """cleanup worker 不应杀 beat。"""
    pid_worker = _spawn_fake_worker("worker")
    pid_beat = _spawn_fake_worker("beat")

    try:
        result = cleanup_orphan_celery("worker", log_path, timeout_seconds=2.0)
        assert pid_worker in (result["terminated"] + result["killed"])
        assert pid_beat not in (result["terminated"] + result["killed"])
        time.sleep(0.5)
        assert not _pid_alive(pid_worker)
        assert _pid_alive(pid_beat)
    finally:
        try:
            os.kill(pid_beat, signal.SIGKILL)
        except ProcessLookupError:
            pass


def test_timeout_triggers_sigkill(log_path: Path) -> None:
    """trap SIGTERM 不退出的进程 → 5s 超时后被 SIGKILL,归类为 killed。"""
    # trap SIGTERM 的进程:收到 SIGTERM 不退出
    proc = subprocess.Popen(
        ["/bin/sh", "-c",
         f"trap '' TERM; exec -a 'celery -A app.tasks.celery_app worker' sleep 60"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    time.sleep(0.1)

    try:
        # timeout 2 秒以加快测试
        result = cleanup_orphan_celery("worker", log_path, timeout_seconds=2.0)
        assert proc.pid in result["killed"], f"expected {proc.pid} in killed, got {result}"
        assert proc.pid not in result["terminated"]
        time.sleep(0.3)
        assert not _pid_alive(proc.pid)
    finally:
        try:
            os.kill(proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass


def test_log_file_is_appended_not_overwritten(log_path: Path) -> None:
    """多次调用 → 日志追加,前一行的内容仍在。"""
    cleanup_orphan_celery("worker", log_path, timeout_seconds=1.0)
    first_size = log_path.stat().st_size

    cleanup_orphan_celery("worker", log_path, timeout_seconds=1.0)
    second_size = log_path.stat().st_size

    assert second_size > first_size
    # 第二次 cleanup_start 应在文件末尾,但前一次的 cleanup_done 也应能找到
    content = log_path.read_text()
    assert content.count("cleanup_start") == 2
    assert content.count("cleanup_done") == 2


def test_cli_invocation(tmp_path: Path) -> None:
    """python -m launcher.orphan_cleanup --role worker --log X 走命令行也能正常工作。"""
    log = tmp_path / "cli.log"
    rc = subprocess.run(
        [sys.executable, "-m", "launcher.orphan_cleanup", "--role", "worker",
         "--log", str(log), "--timeout", "1.0"],
        capture_output=True, text=True,
    )
    assert rc.returncode == 0, f"stdout={rc.stdout} stderr={rc.stderr}"
    assert log.exists()
    assert "cleanup_done" in log.read_text()
