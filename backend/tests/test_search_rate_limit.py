"""搜索频率与周配额服务单元测试。

关联 spec: docs/superpowers/specs/2026-07-25-crawl-rate-limit-design.md
"""
from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from app.models.search_usage import SearchUsage
from app.services.search_rate_limit import (
    SearchRateLimiter,
    increment_weekly_search,
    iso_week_key,
    weekly_search_count,
)


def test_first_search_has_no_delay_then_uses_injected_interval() -> None:
    limiter = SearchRateLimiter(10, 15, uniform=lambda low, high: 12.0)

    assert limiter.next_delay() is None  # 任务内第一次搜索不等待
    assert limiter.next_delay() == 12.0
    assert limiter.next_delay() == 12.0


def test_delay_passes_configured_bounds_to_uniform() -> None:
    seen: list[tuple[float, float]] = []
    limiter = SearchRateLimiter(8, 20, uniform=lambda low, high: seen.append((low, high)) or low)

    limiter.next_delay()
    assert limiter.next_delay() == 8
    assert seen == [(8, 20)]


def test_iso_week_key_uses_shanghai_iso_week() -> None:
    # 2026-01-01 是周四，属于 2026 年 ISO 第 1 周
    assert iso_week_key(datetime(2026, 1, 1, 0, 30, tzinfo=ZoneInfo("Asia/Shanghai"))) == "2026-W01"
    # 2026-07-25 是周六，属于 2026 年 ISO 第 30 周
    assert iso_week_key(datetime(2026, 7, 25, 12, 0, tzinfo=ZoneInfo("Asia/Shanghai"))) == "2026-W30"


def test_weekly_usage_increment_and_count(db_session: Session) -> None:
    assert weekly_search_count(db_session, "2026-W30") == 0

    assert increment_weekly_search(db_session, "2026-W30") == 1
    assert increment_weekly_search(db_session, "2026-W30") == 2
    assert weekly_search_count(db_session, "2026-W30") == 2


def test_weekly_usage_isolated_between_weeks(db_session: Session) -> None:
    increment_weekly_search(db_session, "2026-W29")
    increment_weekly_search(db_session, "2026-W29")

    assert weekly_search_count(db_session, "2026-W30") == 0
    assert db_session.query(SearchUsage).count() == 1
