"""推文编辑页活动重提取与手动新增测试（spec: 2026-08-03-note-edit-activities-re-extract-design）。"""

from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.security import create_access_token
from app.models.activity import Activity
from app.models.note import Note, NoteImage


def _auth() -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token({'sub': 'admin', 'role': 'admin'})}"}


def _note_with_images(db: Session, status: str = "PROCESSED") -> Note:
    note = Note(
        task_id=1,
        platform_note_id="test-note-re-extract",
        title="周末活动合集",
        content="本周末有很多活动",
        source_url="https://www.xiaohongshu.com/explore/test-note-re-extract",
        city_code="nb",
        status=status,
        review_status="PENDING",
        published_at=datetime(2026, 8, 3, 10, 0, tzinfo=timezone.utc),
        raw_data={},
    )
    db.add(note)
    db.flush()
    db.add(NoteImage(
        note_id=note.id,
        storage_key="test/image1.jpg",
        ocr_text="[IMAGE 1]\n宁波周末市集 8月8日-10日 老外滩",
        ocr_status="done",
    ))
    db.add(NoteImage(
        note_id=note.id,
        storage_key="test/image2.jpg",
        ocr_text="[IMAGE 2]\n音乐节 8月15日 文化广场",
        ocr_status="done",
    ))
    db.commit()
    return note


# ---------- re-extract ----------


def test_re_extract_creates_activities_from_existing_ocr(
    client: TestClient,
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """有 OCR 文本时，重新提取应产生活动。"""
    note = _note_with_images(db_session)

    # mock extract_activities 返回可控数据（必须 mock notes 模块的引用，不是 crawl_task）
    from app.api.v1 import notes as notes_module
    extracted = [
        {"name": "宁波周末市集", "start_time": "2026-08-08T10:00:00", "end_time": "2026-08-10T22:00:00",
         "location": "老外滩", "type": "市集", "summary": "周末市集活动", "confidence": 0.9, "source_image_indexes": [1]},
        {"name": "音乐节", "start_time": "2026-08-15T14:00:00", "end_time": None,
         "location": "文化广场", "type": "演出", "summary": "音乐节", "confidence": 0.85, "source_image_indexes": [2]},
    ]
    monkeypatch.setattr(notes_module, "extract_activities", lambda *_args, **_kwargs: extracted)

    resp = client.post(
        f"/api/v1/notes/{note.id}/re-extract",
        headers=_auth(),
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["status"] == "PROCESSED"
    assert data["extracted_count"] == 2
    assert len(data["activities"]) == 2

    db_session.refresh(note)
    assert note.status == "PROCESSED"
    activities = db_session.query(Activity).filter(
        Activity.note_id == note.id, Activity.deleted_at.is_(None)
    ).all()
    assert len(activities) == 2


def test_re_extract_note_not_found(client: TestClient) -> None:
    resp = client.post("/api/v1/notes/99999/re-extract", headers=_auth())
    assert resp.status_code == 404


def test_re_extract_note_no_images_returns_empty(
    client: TestClient,
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """无图片的推文重新提取，应返回空活动。"""
    note = Note(
        task_id=1,
        platform_note_id="no-img-note",
        title="无图推文",
        content="没有图片",
        source_url="https://www.xiaohongshu.com/explore/no-img-note",
        city_code="nb",
        status="NO_ACTIVITIES",
        review_status="PENDING",
        published_at=datetime(2026, 8, 3, tzinfo=timezone.utc),
        raw_data={},
    )
    db_session.add(note)
    db_session.commit()

    from app.api.v1 import notes as notes_module
    monkeypatch.setattr(notes_module, "extract_activities", lambda *_args, **_kwargs: [])

    resp = client.post(f"/api/v1/notes/{note.id}/re-extract", headers=_auth())
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["extracted_count"] == 0
    assert data["activities"] == []


def test_re_extract_clears_old_activities(
    client: TestClient,
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """重新提取应先软删除旧活动，再写入新活动。"""
    note = _note_with_images(db_session)
    old = Activity(
        note_id=note.id, name="旧活动", city_code="nb", type="展览",
        start_time=datetime(2026, 8, 1, tzinfo=timezone.utc),
    )
    db_session.add(old)
    db_session.commit()

    from app.api.v1 import notes as notes_module
    extracted = [
        {"name": "新活动", "start_time": "2026-08-10T10:00:00", "end_time": None,
         "location": "新地点", "type": "市集", "summary": "", "confidence": 0.9, "source_image_indexes": []},
    ]
    monkeypatch.setattr(notes_module, "extract_activities", lambda *_args, **_kwargs: extracted)

    resp = client.post(f"/api/v1/notes/{note.id}/re-extract", headers=_auth())
    assert resp.status_code == 200

    # 旧活动被软删除
    db_session.refresh(old)
    assert old.deleted_at is not None

    # 新活动存在
    new_activities = db_session.query(Activity).filter(
        Activity.note_id == note.id, Activity.deleted_at.is_(None)
    ).all()
    assert len(new_activities) == 1
    assert new_activities[0].name == "新活动"


# ---------- 手动新增活动 ----------


def test_create_activity_for_note_succeeds(client: TestClient, db_session: Session) -> None:
    note = _note_with_images(db_session)

    resp = client.post(
        f"/api/v1/notes/{note.id}/activities",
        headers=_auth(),
        json={
            "name": "手动添加的活动",
            "location": "测试地点",
            "start_time": "2026-08-10T10:00:00",
            "end_time": "2026-08-10T18:00:00",
            "type": "市集",
            "summary": "手动补充的活动",
        },
    )
    assert resp.status_code == 201
    data = resp.json()["data"]
    assert data["name"] == "手动添加的活动"
    assert data["location"] == "测试地点"
    assert data["type"] == "市集"
    assert data["note_id"] == note.id

    activity = db_session.get(Activity, data["id"])
    assert activity is not None
    assert activity.deleted_at is None


def test_create_activity_for_note_not_found(client: TestClient) -> None:
    resp = client.post(
        "/api/v1/notes/99999/activities",
        headers=_auth(),
        json={"name": "x", "location": "", "type": "展览"},
    )
    assert resp.status_code == 404


def test_create_activity_for_note_validation(client: TestClient, db_session: Session) -> None:
    note = _note_with_images(db_session)

    resp = client.post(
        f"/api/v1/notes/{note.id}/activities",
        headers=_auth(),
        json={"name": "", "type": ""},
    )
    assert resp.status_code == 422