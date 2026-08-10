"""活动日期窗口校验：零活动/早于发布时间过滤。"""
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models.note import Note
from app.services.activity_validator import classify_zero_activity, validate_activities


def _make_note(db: Session, *, content: str, published_at: datetime | None) -> Note:
    note = Note(
        title="t",
        content=content,
        source_url="https://xhs.example/n/x",
        platform_note_id=f"p-{published_at.timestamp() if published_at else 0}",
        city_code="sh",
        task_id=0,
        status="PENDING",
        published_at=published_at,
        review_status="PENDING",
    )
    db.add(note)
    db.flush()
    return note


def _act(start_time: str | None, name: str = "活动") -> dict:
    return {
        "name": name,
        "city_code": "sh",
        "type": "演出",
        "start_time": start_time,
        "source_url": "https://xhs.example/n/x",
    }


def test_classify_no_signals_when_empty_body(db_session: Session) -> None:
    note = _make_note(db_session, content="", published_at=datetime(2026, 7, 22, 10, 0, tzinfo=timezone.utc))
    state = classify_zero_activity(note, [])
    assert state == "no_activity_signals"


def test_classify_returns_ok_when_one_activity_after_publish(db_session: Session) -> None:
    note = _make_note(
        db_session,
        content="周末有音乐节，欢迎参加",
        published_at=datetime(2026, 7, 22, 10, 0, tzinfo=timezone.utc),
    )
    activities = [_act("2026-07-23T18:00:00+00:00")]
    state = classify_zero_activity(note, activities)
    assert state == "ok"
    accepted, rejected = validate_activities(note, activities)
    assert len(accepted) == 1
    assert rejected == []


def test_validate_drops_activity_before_publish(db_session: Session) -> None:
    note = _make_note(
        db_session,
        content="周末有音乐节，欢迎参加",
        published_at=datetime(2026, 7, 22, 10, 0, tzinfo=timezone.utc),
    )
    activities = [_act("2026-07-21T18:00:00+00:00", name="过期活动")]
    accepted, rejected = validate_activities(note, activities)
    assert accepted == []
    assert rejected and any("早于" in m for m in rejected)
    # classify 应当归到 all_before_publish
    assert classify_zero_activity(note, activities) == "all_before_publish"


def test_validate_keeps_activity_same_day_earlier_than_publish(db_session: Session) -> None:
    # 同一天合法活动不再被误判：published=7/22 10:00 UTC，活动=7/22 02:00 UTC → 接受
    note = _make_note(
        db_session,
        content="7月22日起开始",
        published_at=datetime(2026, 7, 22, 10, 0, tzinfo=timezone.utc),
    )
    activities = [_act("2026-07-22T02:00:00+00:00", name="同日早场")]
    accepted, rejected = validate_activities(note, activities)
    assert len(accepted) == 1
    assert rejected == []
    assert classify_zero_activity(note, activities) == "ok"


def test_classify_minimax_empty_when_body_has_signal_but_no_activities(
    db_session: Session,
) -> None:
    note = _make_note(
        db_session,
        content="今天来参加市集，地址徐汇滨江",
        published_at=datetime(2026, 7, 22, 10, 0, tzinfo=timezone.utc),
    )
    assert classify_zero_activity(note, []) == "minimax_empty_retryable"


def test_keeps_activity_without_start_time(db_session: Session) -> None:
    note = _make_note(
        db_session,
        content="市集",
        published_at=datetime(2026, 7, 22, 10, 0, tzinfo=timezone.utc),
    )
    activities = [{"name": "日期待确认", "city_code": "sh", "type": "演出"}]
    accepted, rejected = validate_activities(note, activities)
    assert len(accepted) == 1
    assert rejected == []
