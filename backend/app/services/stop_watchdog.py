"""StopWatchdog：worker 内部守护线程，30s 一次轮询 task 状态，命中 STOP_REQUESTED 即 set Event。

为什么需要：用户点停止时，API 写库 + kill task_registry 里的 opencli 子进程；二者都不能打断
in-process 同步调用（PaddleOCR / MiniMax HTTP 等没注册 PID 的 Python 阻塞）。Watchdog 是兜底，
让主线程下一次 assert_execution_active 检查能感知到 stop。

关联 spec: docs/superpowers/specs/2026-08-19-crawl-stop-watchdog-design.md
"""
from __future__ import annotations

import logging
import threading
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass


logger = logging.getLogger(__name__)


class StopWatchdog:
    """独立线程轮询 DB 的 STOP_REQUESTED，命中即 set Event 让主线程感知。"""

    POLL_INTERVAL_SECONDS: float = 30.0  # 生产默认；测试可 monkeypatch 加速

    def __init__(
        self,
        task_id: int,
        run_token: str,
        session_factory=None,
    ) -> None:
        self.task_id = task_id
        self.run_token = run_token
        self.stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        # 测试可注入自己的 session_factory（conftest 用临时 DB）
        self._session_factory = session_factory

    def start(self) -> None:
        self._thread = threading.Thread(
            target=self._loop,
            name=f"stop-watchdog-{self.task_id}",
            daemon=True,
        )
        self._thread.start()

    def stop(self, timeout: float = 2.0) -> None:
        """主线程结束前调用：set Event 唤醒循环 + join 收尾。"""
        self.stop_event.set()
        thread = self._thread
        if thread is not None:
            thread.join(timeout=timeout)

    def _loop(self) -> None:
        from sqlalchemy import select

        if self._session_factory is None:
            from app.core.database import SessionLocal

            session_factory = SessionLocal
        else:
            session_factory = self._session_factory

        from app.models.task import CrawlTask

        while not self.stop_event.is_set():
            db = session_factory()
            try:
                row = db.execute(
                    select(CrawlTask.status, CrawlTask.run_token).where(CrawlTask.id == self.task_id)
                ).one_or_none()
            except Exception as exc:  # pragma: no cover - watchdog 自身异常不抛出
                logger.warning("watchdog 轮询异常 task_id=%s: %s", self.task_id, exc)
                # 继续轮询（不要让 transient 错误导致永远停不下来）
                self.stop_event.wait(timeout=self.POLL_INTERVAL_SECONDS)
                continue
            finally:
                try:
                    db.close()
                except Exception:  # pragma: no cover
                    pass

            if row is None or row.run_token != self.run_token:
                # task 被清理或换 token,不再管
                return
            status = row.status
            if status in ("STOPPED", "COMPLETED", "COMPLETED_WITH_ERRORS", "FAILED"):
                return  # 终态,不再轮询
            if status in ("STOP_REQUESTED",):
                self.stop_event.set()
                return
            # RUNNING / PENDING / 其他 → 等下一轮
            # stop_event.wait 能被 stop() 立即唤醒
            self.stop_event.wait(timeout=self.POLL_INTERVAL_SECONDS)