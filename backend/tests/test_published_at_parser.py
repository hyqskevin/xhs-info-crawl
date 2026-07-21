"""Tests for parse_published_at and extract_published_at.

关联 spec: docs/superpowers/specs/2026-07-21-parse-real-published-at-design.md
"""
from datetime import datetime, timedelta, timezone

import pytest

from app.services.published_at import (
    SHANGHAI,
    extract_published_at,
    parse_published_at,
)


@pytest.fixture
def now_local() -> datetime:
    # 2026-08-10 12:00 Asia/Shanghai
    return datetime(2026, 8, 10, 12, 0, tzinfo=SHANGHAI)


def test_parse_absolute_iso_date_returns_utc(now_local: datetime) -> None:
    result = parse_published_at("2025-07-20", now_local=now_local)
    assert result.source == "absolute"
    assert result.confidence == 1.0
    assert result.value == datetime(2025, 7, 20, 0, 0, tzinfo=SHANGHAI).astimezone(timezone.utc)


def test_parse_absolute_iso_with_time(now_local: datetime) -> None:
    result = parse_published_at("2025-07-20 18:30", now_local=now_local)
    assert result.source == "absolute"
    assert result.value == datetime(2025, 7, 20, 18, 30, tzinfo=SHANGHAI).astimezone(timezone.utc)


def test_parse_chinese_style_absolute_date(now_local: datetime) -> None:
    result = parse_published_at("2025年7月20日 18:30", now_local=now_local)
    assert result.source == "absolute"
    assert result.value == datetime(2025, 7, 20, 18, 30, tzinfo=SHANGHAI).astimezone(timezone.utc)


def test_parse_slash_date(now_local: datetime) -> None:
    result = parse_published_at("2025/07/20", now_local=now_local)
    assert result.source == "absolute"
    assert result.value == datetime(2025, 7, 20, 0, 0, tzinfo=SHANGHAI).astimezone(timezone.utc)


def test_parse_month_day_with_explicit_pair_infers_year(now_local: datetime) -> None:
    result = parse_published_at("07-20 18:00", now_local=now_local)
    assert result.source == "month_day"
    assert result.value == datetime(2026, 7, 20, 18, 0, tzinfo=SHANGHAI).astimezone(timezone.utc)


def test_parse_month_day_in_past_year_rolls_back_to_last_year(now_local: datetime) -> None:
    # 当前已是 2026-08，"01-05" 在未来，超过基准则回退
    result = parse_published_at("01-05", now_local=now_local)
    assert result.source == "month_day"
    assert result.value == datetime(2026, 1, 5, 0, 0, tzinfo=SHANGHAI).astimezone(timezone.utc)


def test_parse_month_day_future_rolls_back_to_previous_year(now_local: datetime) -> None:
    # 12-15 在 now_local=2026-08-10 之后，应回退到 2025-12-15
    result = parse_published_at("12-15", now_local=now_local)
    assert result.source == "month_day"
    assert result.value == datetime(2025, 12, 15, 0, 0, tzinfo=SHANGHAI).astimezone(timezone.utc)


def test_parse_relative_day(now_local: datetime) -> None:
    result = parse_published_at("2天前", now_local=now_local)
    assert result.source == "relative_day"
    expected = (now_local - timedelta(days=2)).astimezone(timezone.utc)
    assert result.value == expected


def test_parse_relative_hour(now_local: datetime) -> None:
    result = parse_published_at("5小时前", now_local=now_local)
    assert result.source == "relative_hour"
    expected = (now_local - timedelta(hours=5)).astimezone(timezone.utc)
    assert result.value == expected


def test_parse_relative_minute(now_local: datetime) -> None:
    result = parse_published_at("30分钟前", now_local=now_local)
    assert result.source == "relative_minute"
    expected = (now_local - timedelta(minutes=30)).astimezone(timezone.utc)
    assert result.value == expected


def test_parse_empty_text_returns_none(now_local: datetime) -> None:
    result = parse_published_at("", now_local=now_local)
    assert result.source == "none"
    assert result.value is None
    assert result.confidence == 0.0


def test_parse_garbage_text_returns_none(now_local: datetime) -> None:
    result = parse_published_at("随便一行字", now_local=now_local)
    assert result.value is None
    assert result.source == "none"


def test_parse_invalid_date_components_returns_none(now_local: datetime) -> None:
    # 2025-13-40 不是合法日期
    result = parse_published_at("2025-13-40", now_local=now_local)
    assert result.value is None


@pytest.mark.parametrize("detail", [
    {"published_at": "2025-07-20T18:30:00+08:00"},
    {"publishTime": "2025-07-20 18:30"},
    {"date": "2025-07-20"},
    {"time": "2025年7月20日"},
    {"content": "本页发布于 2025-07-20 18:30"},
    {"title": "夏日 / 2025-07-20"},
    {"snippet": "5小时前发布"},
])
def test_extract_published_at_finds_value(detail: dict, now_local: datetime) -> None:
    fallback = datetime(2026, 1, 1, tzinfo=timezone.utc)
    assert extract_published_at(detail, fallback_now=fallback) is not None


def test_extract_published_at_returns_none_when_unparseable(now_local: datetime) -> None:
    fallback = datetime(2026, 1, 1, tzinfo=timezone.utc)
    assert extract_published_at({"title": "随便标题", "content": "内容"}, fallback_now=fallback) is None


def test_extract_published_at_returns_absolute_from_relative_payload(now_local: datetime) -> None:
    fallback = datetime(2026, 8, 10, 12, 0, tzinfo=timezone.utc)
    result = extract_published_at({"content": "正文 1天前"}, fallback_now=fallback)
    assert result is not None
    expected = (fallback.astimezone(SHANGHAI) - timedelta(days=1)).astimezone(timezone.utc)
    assert result == expected
