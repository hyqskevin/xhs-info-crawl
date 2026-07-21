from datetime import datetime, timezone

from app.services.activity_window import ActivityWindow
from app.services.extraction import normalize_activity_datetime


def test_window_includes_reference_day_and_day_60_but_rejects_day_61() -> None:
    window = ActivityWindow(datetime(2026, 7, 17, tzinfo=timezone.utc), 60, "Asia/Shanghai")

    assert window.classify("2026-07-17T00:00:00", None) == "valid"
    assert window.classify("2026-09-15T23:59:59", None) == "valid"
    assert window.classify("2026-09-16T00:00:00", None) == "future"


def test_window_rejects_finished_history_but_keeps_ongoing_activity() -> None:
    window = ActivityWindow(datetime(2026, 7, 17, tzinfo=timezone.utc), 60, "Asia/Shanghai")

    assert window.classify("2024-07-17T18:00:00", None) == "past"
    assert window.classify("2026-07-01T00:00:00", "2026-07-20T00:00:00") == "valid"


def test_window_treats_missing_start_as_unknown() -> None:
    window = ActivityWindow(datetime(2026, 7, 17, tzinfo=timezone.utc), 60, "Asia/Shanghai")

    assert window.classify(None, None) == "unknown"


def test_yearless_date_uses_next_year_when_past_now() -> None:
    """新规则：无年份月日若 < now，加 1 年。不再因 60 天窗口返回 None。"""
    reference = datetime(2026, 12, 20)

    assert normalize_activity_datetime("1月5日", reference, 60).startswith("2027-01-05")
    # 7月1日 (now=2026-12-20 已过) 也加 1 年到 2027-07-01
    assert normalize_activity_datetime("7月1日", reference, 60).startswith("2027-07-01")


def test_explicit_year_is_never_rewritten() -> None:
    reference = datetime(2026, 7, 17)

    assert normalize_activity_datetime("2024-07-17", reference, 60) == "2024-07-17T00:00:00"
