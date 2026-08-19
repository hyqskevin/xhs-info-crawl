"""任务运行时辅助：守卫、日志、进度、调度常量、异常类。

- ``assert_execution_active`` / ``finish_stop_if_requested``：run_token + 状态守卫；
- ``log`` / ``set_progress``：TaskLog 写入 + CrawlTask 进度更新；
- ``rate_limit_sleep``：可被 stop 守卫打断的 sleep；
- ``find_opencli``：shutil.which 的薄封装，便于测试 monkeypatch；
- ``ExecutionStopped`` / ``ExecutionSuperseded``：run_crawl 内部终止信号。
"""
from __future__ import annotations

from collections.abc import Callable
from contextlib import contextmanager
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
import logging
import shutil
import threading
import time

from sqlalchemy import func, select, update

from app.models.schedule import ScheduledCrawl
from app.models.task import CrawlTask, TaskLog


logger = logging.getLogger(__name__)

_DISPATCH_TZ = ZoneInfo("Asia/Shanghai")
_BUSY_STATUSES = ("PENDING", "RUNNING", "STOP_REQUESTED")
_TERMINAL_STATUSES = ("STOPPED", "COMPLETED", "COMPLETED_WITH_ERRORS", "FAILED")

# 当前线程所属 crawl 任务的 stop_event；thread-local 保证多 worker/多 task 隔离
_current_stop_event = threading.local()


class ExecutionStopped(Exception):
    pass


class ExecutionSuperseded(Exception):
    pass


@contextmanager
def stop_event_scope(stop_event: threading.Event | None):
    """在当前线程登记 stop_event；assert_execution_active 检查它。

    用法：``run_crawl`` 入口 ``with stop_event_scope(watchdog.stop_event):``。
    search.py / notes.py 等模块级函数调用 ``assert_execution_active`` 时无需传 event ——。
    """
    prev = getattr(_current_stop_event, "value", None)
    _current_stop_event.value = stop_event
    try:
        yield
    finally:
        _current_stop_event.value = prev


def find_opencli(bin_name: str) -> str | None:
    """解析 opencli 可执行文件路径（shutil.which 的薄封装，便于测试 monkeypatch）。"""
    return shutil.which(bin_name)


def rate_limit_sleep(seconds: float, guard: Callable[[], None] | None = None) -> None:
    """可中断的频率控制 sleep：0.5s 分片，每片执行 guard（执行栅栏），stop 请求 0.5s 内响应。"""
    deadline = time.monotonic() + max(0.0, seconds)
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return
        time.sleep(min(0.5, remaining))
        if guard:
            guard()


def assert_execution_active(
    db,
    task_id: int,
    run_token: str,
    stop_event: threading.Event | None = None,
) -> None:
    row = db.execute(
        select(CrawlTask.status, CrawlTask.run_token).where(CrawlTask.id == task_id)
    ).one_or_none()
    if row is None or row.run_token != run_token:
        raise ExecutionSuperseded()
    if row.status in {"STOP_REQUESTED", "STOPPED"}:
        raise ExecutionStopped()
    if row.status != "RUNNING":
        raise ExecutionSuperseded()
    # Watchdog 命中 STOP_REQUESTED 后会 set Event；主线程下一次 guard 检查即抛 ExecutionStopped
    effective_event = stop_event if stop_event is not None else getattr(_current_stop_event, "value", None)
    if effective_event is not None and effective_event.is_set():
        raise ExecutionStopped()


def log(db, task_id: int, level: str, message: str) -> None:
    db.add(TaskLog(task_id=task_id, level=level, message=message))
    db.commit()


def set_progress(db, task: CrawlTask, run_token: str, stage: str, current_note: str | None = None) -> None:
    changed = db.execute(
        update(CrawlTask)
        .where(
            CrawlTask.id == task.id,
            CrawlTask.run_token == run_token,
            CrawlTask.status == "RUNNING",
        )
        .values(current_stage=stage, current_note=current_note)
    )
    db.commit()
    if changed.rowcount != 1:
        assert_execution_active(db, task.id, run_token)
    db.refresh(task)


def finish_stop_if_requested(db, task_id: int, run_token: str) -> bool:
    current = db.get(CrawlTask, task_id)
    db.refresh(current)
    if current.run_token != run_token:
        raise ExecutionSuperseded()
    if current.status not in ("STOP_REQUESTED", "STOPPED"):
        return False
    if current.status != "STOPPED":
        current.status = "STOPPED"
        current.current_stage = None
        current.current_note = None
        current.finished_at = datetime.now(timezone.utc)
        db.commit()
        log(db, current.id, "INFO", "任务已安全停止")
    return True
