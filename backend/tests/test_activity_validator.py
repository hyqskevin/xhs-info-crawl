"""Tests for activity_validator and extraction降级 when Note.published_at is available.

关联 spec: docs/superpowers/specs/2026-07-21-zero-activity-and-window-fix-design.md
"""
from datetime import datetime, timedelta, timezone

import pytest

from app.services.activity_validator import (
    classify_zero_activity,
    validate_activities,
)


def _dt(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


class FakeNote:
    def __init__(self, *, published_at=None, content: str = "", raw_data: dict | None = None):
        self.published_at = published_at
        self.content = content
        self.raw_data = raw_data or {}


@pytest.fixture
def note_at() -> datetime:
    return datetime(2026, 7, 17, 12, 0, tzinfo=timezone.utc)


# ----- validate_activities -----

def test_validate_keeps_activity_after_published_at(note_at):
    note = FakeNote(published_at=note_at)
    activities = [
        {"name": "夏日有闲市", "start_time": (note_at + timedelta(days=1)).isoformat()},
    ]
    accepted, rejected = validate_activities(note, activities)
    assert len(accepted) == 1
    assert rejected == []


def test_validate_skips_activity_before_published_at(note_at):
    note = FakeNote(published_at=note_at)
    activities = [
        {"name": "过期活动", "start_time": (note_at - timedelta(days=1)).isoformat()},
    ]
    accepted, rejected = validate_activities(note, activities)
    assert accepted == []
    assert rejected and "过期活动" in rejected[0]


def test_validate_keeps_activity_without_start_time(note_at):
    note = FakeNote(published_at=note_at)
    activities = [{"name": "时间未知", "start_time": None}]
    accepted, rejected = validate_activities(note, activities)
    assert len(accepted) == 1
    assert rejected == []


def test_validate_keeps_all_when_published_at_is_none():
    note = FakeNote(published_at=None)
    activities = [
        {"name": "a", "start_time": "2020-01-01T00:00:00+00:00"},
        {"name": "b", "start_time": "2030-01-01T00:00:00+00:00"},
    ]
    accepted, rejected = validate_activities(note, activities)
    assert len(accepted) == 2
    assert rejected == []


def test_validate_rejects_unparseable_start_time(note_at):
    note = FakeNote(published_at=note_at)
    accepted, rejected = validate_activities(note, [{"name": "x", "start_time": "不是时间"}])
    assert accepted == []
    assert rejected and "无法解析" in rejected[0]


# ----- classify_zero_activity -----

def test_classify_returns_ok_when_one_activity_after(note_at):
    note = FakeNote(published_at=note_at, content="页面", raw_data={})
    extracted = [{"name": "a", "start_time": (note_at + timedelta(days=2)).isoformat()}]
    assert classify_zero_activity(note, extracted) == "ok"


def test_classify_returns_all_before_publish_when_all_skipped(note_at):
    note = FakeNote(published_at=note_at, content="页面", raw_data={})
    extracted = [
        {"name": "a", "start_time": (note_at - timedelta(days=3)).isoformat()},
        {"name": "b", "start_time": (note_at - timedelta(days=1)).isoformat()},
    ]
    assert classify_zero_activity(note, extracted) == "all_before_publish"


def test_classify_returns_minimax_empty_retryable_when_content_has_signals(note_at):
    note = FakeNote(published_at=note_at, content="本周六徐汇有市集，欢迎参与！", raw_data={})
    assert classify_zero_activity(note, []) == "minimax_empty_retryable"


def test_classify_returns_no_signals_when_body_is_empty(note_at):
    note = FakeNote(published_at=note_at, content="", raw_data={})
    assert classify_zero_activity(note, []) == "no_activity_signals"


def test_classify_returns_no_signals_when_body_has_no_activity_keywords(note_at):
    note = FakeNote(published_at=note_at, content="今日午后阳光很好，咖啡香气弥漫。", raw_data={})
    assert classify_zero_activity(note, []) == "no_activity_signals"


# ----- extraction 降级解析（与 validator 配合）-----

def test_extraction_month_day_uses_note_published_at_for_year(note_at):
    from app.services.extraction import normalize_activity_row
    now = note_at.replace(tzinfo=None)
    # 推文发布时间 7.17，活动识别为 "7.18 18:00"（无年份）
    row = {"name": "市集", "start_time": "7.18 18:00", "location": "徐汇", "type": "市集"}
    out = normalize_activity_row(row, now)
    assert out["start_time"] is not None
    parsed = datetime.fromisoformat(out["start_time"])
    assert parsed.year == 2026
    assert parsed.month == 7 and parsed.day == 18


def test_extraction_chinese_dot_separator_supported(note_at):
    from app.services.extraction import normalize_activity_row
    now = note_at.replace(tzinfo=None)
    row = {"name": "市集", "start_time": "7.18 18:00", "location": "徐汇", "type": "市集"}
    # 7.18 在数据库里以点分隔也应识别
    out = normalize_activity_row({"name": "市集", "start_time": "7.18", "location": "x", "type": "展览"}, now)
    parsed = datetime.fromisoformat(out["start_time"])
    assert parsed.year == 2026
    assert parsed.month == 7


def test_extraction_short_format_rolls_forward_to_next_year_when_past(note_at):
    from app.services.extraction import normalize_activity_row
    now = note_at.replace(tzinfo=None)
    # 活动识别 "1.18" 对比 now=2026-07-17 已过，跨年回退 -> 2027-01-18
    out = normalize_activity_row({"name": "展览", "start_time": "1.18", "location": "x", "type": "展览"}, now)
    parsed = datetime.fromisoformat(out["start_time"])
    assert parsed.year == 2027
    # 同年未来月保留本年
    out2 = normalize_activity_row({"name": "展览", "start_time": "9.18", "location": "x", "type": "展览"}, now)
    parsed2 = datetime.fromisoformat(out2["start_time"])
    assert parsed2.year == 2026
