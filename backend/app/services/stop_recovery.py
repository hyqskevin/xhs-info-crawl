"""停止状态兜底恢复：周期性扫描长时间停在 STOP_REQUESTED 的 task，强制落 STOPPED。

为什么需要：watchdog（spec 2026-08-19）只覆盖 DB 轮询 + Event，worker 在某些
in-process 阻塞调用（MiniMax HTTP / PaddleOCR / opencli 子进程）卡住时，主线程
完全不去 assert_execution_active，watchdog set event 后仍要等当前调用超时
（默认 60s/180s）才会感知。用户感受"卡正在停止很久"。

兜底方案：beat task 每 60s 扫描 status='STOP_REQUESTED' + 最后一条 task_log
（或 started_at）超过 STUCK_THRESHOLD_SECONDS 没动 → 强制 UPDATE status='STOPPED' +
写 WARNING log，便于审计。

关联 spec: docs/superpowers/specs/2026-08-22-stop-stuck-recovery-design.md
"""
from __future__ import annotations

from datetime import datetime, timedelta

from app.core.timeutil import now_cn, to_cn_naive
from typing import TYPE_CHECKING, Callable

from sqlalchemy import func, select

from app.core.database import SessionLocal
from app.models.task import CrawlTask, TaskLog

if TYPE_CHECKING:
    pass


STUCK_THRESHOLD_SECONDS: int = 120  # STOP_REQUESTED 停留超过 120s 视为卡死


def recover_stuck_stop_requests(session_factory: Callable | None = None) -> int:
    """扫描长时间停在 STOP_REQUESTED 的 task，强制落 STOPPED。

    Args:
        session_factory: 测试可注入自己的 sessionmaker；生产默认用 SessionLocal。

    返回恢复的 task 数（便于 beat 日志观测）。
    """
    factory = session_factory or SessionLocal
    db = factory()
    try:
        cutoff = now_cn() - timedelta(seconds=STUCK_THRESHOLD_SECONDS)
        rows = db.scalars(
            select(CrawlTask).where(
                CrawlTask.status == "STOP_REQUESTED",
                CrawlTask.finished_at.is_(None),
            )
        ).all()
        recovered = 0
        now = now_cn()
        for row in rows:
            last_log_at = db.scalar(
                select(func.max(TaskLog.created_at)).where(TaskLog.task_id == row.id)
            )
            # 没有 task_logs → 用 started_at / created_at 兜底
            anchor = last_log_at or row.started_at or row.created_at
            if anchor is None:
                continue
            # anchor 存量可能是 aware（旧 UTC 写侧产生）；统一归一到北京墙钟 naive 再比较
            if anchor.tzinfo is not None:
                anchor = to_cn_naive(anchor)
            if anchor > cutoff:
                continue
            row.status = "STOPPED"
            row.current_stage = None
            row.current_note = None
            row.finished_at = now
            row.error_message = (
                f"强制停止：worker 未在 {STUCK_THRESHOLD_SECONDS}s 内响应 STOP_REQUESTED"
            )
            db.add(TaskLog(
                task_id=row.id,
                level="WARNING",
                message=(
                    f"stop_recovery: 强制停止（last_log_at={anchor.isoformat()}, "
                    f"threshold={STUCK_THRESHOLD_SECONDS}s）"
                ),
                created_at=now,
            ))
            recovered += 1
        if recovered:
            db.commit()
        return recovered
    finally:
        db.close()