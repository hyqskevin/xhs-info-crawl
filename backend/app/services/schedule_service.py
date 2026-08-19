"""定时任务跨运行失败熔断服务（spec: 2026-08-19-schedule-circuit-breaker-retry-design.md）。

职责：
- ``record_schedule_success``：任务成功终态 → 清连续失败计数与冷却（跨运行级清零）。
- ``record_schedule_failure``：任务失败终态 → 累计连续失败；达阈值进入冷却（cooldown_until）。
- ``should_record_schedule_failure``：判断该任务终态是否算一次"熔断性失败"。

仅对 ``type == "scheduled"`` 且有 ``params.schedule_id`` 的任务生效；手动任务不参与。
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.schedule import ScheduledCrawl

# 终态为 PAUSED 时，仅当 error_message 命中这些"熔断/登录类"关键词才累计失败；
# 纯停止/用户暂停（无这些关键词）不计失败。
_HALT_MARKERS = ("CrawlHalted", "所有账号均已失效", "等待登录超时", "连续", "疑似")


def _schedule_id_of(task) -> int | None:
    if getattr(task, "type", None) != "scheduled":
        return None
    params = getattr(task, "params", None) or {}
    return params.get("schedule_id")


def should_record_schedule_failure(task) -> bool:
    """该任务终态是否算一次跨运行熔断失败。

    - FAILED → 计失败；
    - PAUSED 且 error_message 命中熔断/登录类标记 → 计失败；
    - 其余（COMPLETED、PAUSED 但非熔断、超时省略号）→ 不计。
    """
    if _schedule_id_of(task) is None:
        return False
    status = getattr(task, "status", None)
    if status == "FAILED":
        return True
    if status == "PAUSED":
        err = getattr(task, "error_message", None) or ""
        return any(marker in err for marker in _HALT_MARKERS)
    return False


def record_schedule_success(db: Session, task) -> None:
    """任务成功终态 → 清连续失败计数与冷却。无 scheduling 关联则静默跳过。"""
    schedule_id = _schedule_id_of(task)
    if schedule_id is None:
        return
    schedule = db.get(ScheduledCrawl, schedule_id)
    if schedule is None:
        return
    schedule.consecutive_failures = 0
    schedule.cooldown_until = None
    db.commit()


def record_schedule_failure(db: Session, task) -> None:
    """任务失败终态 → 累计连续失败；达阈值进入冷却。未达阈值则 cooldown=now（可尽快重跑）。"""
    schedule_id = _schedule_id_of(task)
    if schedule_id is None:
        return
    if not should_record_schedule_failure(task):
        return
    schedule = db.get(ScheduledCrawl, schedule_id)
    if schedule is None:
        return
    settings = get_settings()
    limit = schedule.consecutive_fail_limit or settings.schedule_consecutive_fail_limit
    interval = schedule.retry_interval_minutes or settings.schedule_retry_interval_minutes
    schedule.consecutive_failures = (schedule.consecutive_failures or 0) + 1
    now = datetime.now(timezone.utc)
    if schedule.consecutive_failures >= max(limit, 1):
        # 达到阈值 → 进入冷却，到期后由 retry_failed_schedules 自动重启
        schedule.cooldown_until = now + timedelta(minutes=max(interval, 1))
    else:
        # 未达阈值 → 不阻塞，允许尽快重跑
        schedule.cooldown_until = now
    db.commit()