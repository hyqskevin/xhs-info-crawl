"""Tests covering the removal of Activity.status and introduction of Activity.deleted_at.

关联 spec: docs/superpowers/specs/2026-07-21-remove-activity-approval-status-design.md
"""
from datetime import datetime, timezone
from typing import Iterable

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.core.security import create_access_token
from app.models.activity import Activity
from app.models.note import Note
from app.models.report import WeeklyReport


@pytest.fixture
def headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token({'sub': 'admin', 'role': 'admin'})}"}


def _make_activity(note: Note | None, name: str, *, city: str = "shanghai", start: datetime | None = None, end: datetime | None = None, deleted: bool = False) -> Activity:
    activity = Activity(
        note_id=note.id if note is not None else None,
        name=name,
        city_code=city,
        start_time=start,
        end_time=end,
        location="徐汇滨江",
        price="免费",
        type="演出",
        source_url="https://example.com/" + name,
        summary="OCR 摘要",
        confidence=0.85,
    )
    if deleted:
        activity.deleted_at = datetime.now(timezone.utc)
    return activity


def test_activity_model_no_longer_exposes_status_column() -> None:
    """Activity 不再包含 status 列（不论已审核、未审核、已发布等）。"""
    column_names = {column.name for column in Activity.__table__.columns}
    assert "status" not in column_names
    assert "deleted_at" in column_names


def test_visible_activities_filter_excludes_soft_deleted(db_session: Session) -> None:
    note = Note(task_id=1, platform_note_id="n-visibility", title="活动详情", content="页面正文", source_url="https://xhs/n-visibility", city_code="shanghai", status="PROCESSED", raw_data={})
    db_session.add(note)
    db_session.flush()

    visible_a = _make_activity(note, "可见 A", start=datetime(2025, 8, 1, 18, tzinfo=timezone.utc))
    visible_b = _make_activity(note, "可见 B", start=datetime(2025, 8, 2, 18, tzinfo=timezone.utc))
    hidden = _make_activity(note, "隐藏", start=datetime(2025, 8, 3, 18, tzinfo=timezone.utc), deleted=True)
    db_session.add_all([visible_a, visible_b, hidden])
    db_session.commit()

    rows = db_session.scalars(select(Activity).where(Activity.note_id == note.id).order_by(Activity.id)).all()
    visible = [row for row in rows if row.deleted_at is None]
    assert {row.name for row in visible} == {"可见 A", "可见 B"}
    assert any(row.deleted_at is not None for row in rows)


def test_list_endpoint_filters_by_deleted_at_only(client: TestClient, db_session: Session, headers: dict[str, str]) -> None:
    db_session.add_all([
        _make_activity(None, "保留 1"),
        _make_activity(None, "保留 2"),
        _make_activity(None, "软删", deleted=True),
    ])
    db_session.commit()

    response = client.get("/api/v1/activities", headers=headers)
    assert response.status_code == 200
    assert response.json()["pagination"]["total"] == 2
    names = {item["name"] for item in response.json()["data"]["items"]}
    assert names == {"保留 1", "保留 2"}


def test_delete_endpoint_persists_deleted_at(client: TestClient, db_session: Session, headers: dict[str, str]) -> None:
    activity = _make_activity(None, "会消失")
    db_session.add(activity)
    db_session.commit()

    response = client.delete(f"/api/v1/activities/{activity.id}", headers=headers)
    assert response.status_code == 200

    db_session.expire_all()
    refreshed = db_session.get(Activity, activity.id)
    assert refreshed is not None
    assert refreshed.deleted_at is not None

    response_after = client.get(f"/api/v1/activities/{activity.id}", headers=headers)
    assert response_after.status_code == 404


def test_batch_approve_returns_410_with_note_review_pointer(client: TestClient, db_session: Session, headers: dict[str, str]) -> None:
    activity = _make_activity(None, "迁移活动")
    db_session.add(activity)
    db_session.commit()

    response = client.post("/api/v1/activities/batch/approve", json={"ids": [activity.id]}, headers=headers)

    assert response.status_code == 410
    detail = response.json().get("message") or response.json().get("detail") or ""
    assert "notes" in detail and "review" in detail


def test_weekly_report_includes_all_non_deleted_activities_regardless_of_review(client: TestClient, db_session: Session, headers: dict[str, str]) -> None:
    """周报收录只看推文维度（APPROVED + 本周发布），子活动全部进入不审核。"""
    # 当周 = 2025-W29（2025-07-14 ~ 2025-07-20）
    published = datetime(2025, 7, 16, 10, tzinfo=timezone.utc)

    approved_note = Note(
        task_id=1, platform_note_id="note-approved", title="已审核推文", content="正文 A", source_url="https://xhs/n1",
        city_code="shanghai", status="PROCESSED", review_status="APPROVED", published_at=published, raw_data={},
    )
    pending_note = Note(
        task_id=1, platform_note_id="note-pending", title="待审核", content="正文 B", source_url="https://xhs/n2",
        city_code="shanghai", status="PROCESSED", review_status="PENDING", published_at=published, raw_data={},
    )
    outside_note = Note(
        task_id=1, platform_note_id="note-outside", title="其他周", content="正文 C", source_url="https://xhs/n3",
        city_code="shanghai", status="PROCESSED", review_status="APPROVED",
        published_at=datetime(2025, 8, 16, tzinfo=timezone.utc), raw_data={},
    )
    db_session.add_all([approved_note, pending_note, outside_note])
    db_session.flush()

    # approved_note 下 3 条子活动（含一条软删）
    a1 = _make_activity(approved_note, "A1 主活动", start=datetime(2025, 8, 1, 18, tzinfo=timezone.utc))
    a2 = _make_activity(approved_note, "A2 限时活动", start=datetime(2025, 7, 25, 18, tzinfo=timezone.utc))  # 不在本周
    a3 = _make_activity(approved_note, "A3 未来活动", start=datetime(2025, 9, 1, 18, tzinfo=timezone.utc))
    a_deleted = _make_activity(approved_note, "A 隐藏", start=datetime(2025, 7, 18, 18, tzinfo=timezone.utc), deleted=True)
    db_session.add_all([a1, a2, a3, a_deleted])

    # pending_note 下 1 条子活动（应被过滤：推文未审核）
    p1 = _make_activity(pending_note, "P1", start=datetime(2025, 8, 2, 18, tzinfo=timezone.utc))
    db_session.add(p1)

    # outside_note 下 1 条子活动（应被过滤：发布不在本周）
    o1 = _make_activity(outside_note, "O1", start=datetime(2025, 9, 5, 18, tzinfo=timezone.utc))
    db_session.add(o1)

    db_session.commit()

    response = client.post(
        "/api/v1/reports/generate",
        json={"week": "2025-W29", "cities": ["shanghai"]},
        headers=headers,
    )
    assert response.status_code == 200, response.text

    report = db_session.scalar(select(WeeklyReport).where(WeeklyReport.week == "2025-W29"))
    assert report is not None
    # 报告中应包含全部 3 条可见子活动，命名一一命中
    for name in ("A1 主活动", "A2 限时活动", "A3 未来活动"):
        assert name in report.content, f"missing {name}: {report.content}"
    for name in ("A 隐藏", "P1", "O1"):
        assert name not in report.content, f"unexpectedly contained {name}"


def test_legacy_database_schema_can_be_dropped(db_session: Session) -> None:
    """黑盒断言：旧 status 列已不存在；如存有旧列这一句将报错。"""
    # 仅在没有 status 列的 schema 下通过
    columns = db_session.execute(text("PRAGMA table_info(activities)")).fetchall()
    column_names = {row[1] for row in columns}
    assert "status" not in column_names
    assert "deleted_at" in column_names


def test_extract_activity_row_does_not_emit_status() -> None:
    """抽取服务 normalize 不再写 status 字段。"""
    from app.services.extraction import normalize_activity_row
    now = datetime(2025, 7, 1, tzinfo=timezone.utc)
    result = normalize_activity_row(
        {"name": "夏日音乐节", "start_time": "2025-07-12T18:00:00", "location": "徐汇滨江", "type": "演出"},
        now,
    )
    assert "status" not in result


def test_merge_activities_drops_status_key() -> None:
    """dedup.merge_activities 返回 dict 不再携带 status。"""
    from app.services.dedup import merge_activities
    left = {"name": "夏日音乐节", "city_code": "shanghai", "start_time": "2025-07-12T18:00:00", "status": "RAW"}
    right = {"name": "夏日音乐节 X", "city_code": "shanghai", "start_time": "2025-07-12T18:00:00", "status": "NEEDS_REVIEW"}
    merged = merge_activities(left, right, keep="a")
    assert "status" not in merged
