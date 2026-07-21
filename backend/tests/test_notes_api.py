from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.security import create_access_token
from app.models.activity import Activity
from app.models.config import City
from app.models.note import Note, NoteImage


def _auth() -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token({'sub': 'admin', 'role': 'admin'})}"}


def _note_with_activities(db: Session) -> Note:
    note = Note(
        task_id=1,
        platform_note_id="post-1",
        title="宁波周末合集",
        content="正文",
        source_url="https://www.xiaohongshu.com/explore/post-1",
        city_code="nb",
        status="PROCESSED",
        review_status="PENDING",
        raw_data={},
    )
    db.add(note)
    db.flush()
    db.add_all([
        Activity(note_id=note.id, name="活动一", city_code="nb", type="展览"),
        Activity(note_id=note.id, name="活动二", city_code="nb", type="演出"),
    ])
    db.commit()
    return note


def test_notes_list_returns_one_row_per_post(client: TestClient, db_session: Session) -> None:
    note = _note_with_activities(db_session)

    response = client.get("/api/v1/notes", headers=_auth())

    assert response.status_code == 200
    items = response.json()["data"]["items"]
    assert items[0] == {
        "id": note.id,
        "title": "宁波周末合集",
        "city_code": "nb",
        "published_at": None,
        "created_at": note.created_at.isoformat(),
        "processing_status": "PROCESSED",
        "review_status": "PENDING",
        "activity_count": 2,
        "source_url": note.source_url,
        "summary": "正文：正文",
        "summary_truncated": False,
    }


def test_note_detail_contains_all_child_activities(client: TestClient, db_session: Session) -> None:
    note = _note_with_activities(db_session)
    db_session.add(NoteImage(note_id=note.id, storage_key="", ocr_text="图片文字", ocr_status="success"))
    db_session.commit()

    response = client.get(f"/api/v1/notes/{note.id}", headers=_auth())

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["title"] == note.title
    assert [item["name"] for item in data["activities"]] == ["活动一", "活动二"]
    assert data["images"][0]["ocr_text"] == "图片文字"
    assert data["summary"] == "正文：正文\n[图片 1 OCR] 图片文字"


def test_batch_approve_notes_approves_post_not_children(client: TestClient, db_session: Session) -> None:
    note = _note_with_activities(db_session)

    response = client.post("/api/v1/notes/batch/approve", json={"ids": [note.id]}, headers=_auth())

    assert response.status_code == 200
    db_session.refresh(note)
    assert note.review_status == "APPROVED"
    assert db_session.query(Activity).count() == 2


def test_update_note_changes_editable_fields_but_keeps_source_url(client: TestClient, db_session: Session) -> None:
    note = _note_with_activities(db_session)
    db_session.add(City(name="上海", code="shanghai", enabled=True))
    db_session.commit()
    published_at = datetime(2026, 7, 21, 10, 30, tzinfo=timezone.utc)

    response = client.put(
        f"/api/v1/notes/{note.id}",
        headers=_auth(),
        json={
            "title": "  更新后的推文  ",
            "content": "更新后的正文",
            "city_code": "shanghai",
            "published_at": published_at.isoformat(),
            "source_url": "https://malicious.example/changed",
        },
    )

    assert response.status_code == 200
    db_session.refresh(note)
    assert note.title == "更新后的推文"
    assert note.content == "更新后的正文"
    assert note.city_code == "shanghai"
    assert note.published_at == published_at.replace(tzinfo=None)
    assert note.source_url == "https://www.xiaohongshu.com/explore/post-1"
    detail = client.get(f"/api/v1/notes/{note.id}", headers=_auth()).json()["data"]
    assert detail["title"] == "更新后的推文"
    assert detail["content"] == "更新后的正文"
    assert detail["published_at"] == published_at.replace(tzinfo=None).isoformat()


@pytest.mark.parametrize(
    ("payload", "expected_detail"),
    [
        ({"title": "   ", "content": "正文", "city_code": "nb", "published_at": None}, "标题不能为空"),
        ({"title": "标题", "content": "正文", "city_code": "disabled", "published_at": None}, "城市不存在或未启用"),
    ],
)
def test_update_note_rejects_invalid_title_or_city(
    client: TestClient,
    db_session: Session,
    payload: dict,
    expected_detail: str,
) -> None:
    note = _note_with_activities(db_session)
    db_session.add(City(name="停用城市", code="disabled", enabled=False))
    db_session.commit()

    response = client.put(f"/api/v1/notes/{note.id}", headers=_auth(), json=payload)

    assert response.status_code == 422
    assert expected_detail in str(response.json())


@pytest.mark.parametrize("target", ["APPROVED", "REJECTED"])
def test_review_single_note_sets_requested_status(
    client: TestClient,
    db_session: Session,
    target: str,
) -> None:
    note = _note_with_activities(db_session)

    response = client.post(
        f"/api/v1/notes/{note.id}/review",
        headers=_auth(),
        json={"status": target},
    )

    assert response.status_code == 200
    assert response.json()["data"] == {"id": note.id, "review_status": target}
    db_session.refresh(note)
    assert note.review_status == target


def test_review_single_note_rejects_unknown_status(client: TestClient, db_session: Session) -> None:
    note = _note_with_activities(db_session)

    response = client.post(
        f"/api/v1/notes/{note.id}/review",
        headers=_auth(),
        json={"status": "PENDING"},
    )

    assert response.status_code == 422


def _seed_notes_for_keyword_search(db: Session) -> list[Note]:
    """为关键字搜索测试 seed 3 条已审核通过的推文。"""
    notes_data = [
        ("nb-yishu", "nb", "上海周末艺术展汇总", "今天去看展"),
        ("nb-coffee", "nb", "宁波咖啡店打卡", "一杯咖啡"),
        ("nb-yishu2", "nb", "宁波艺术展活动汇总", "展览详情"),
    ]
    rows: list[Note] = []
    for pid, city, title, content in notes_data:
        note = Note(
            task_id=1,
            platform_note_id=pid,
            title=title,
            content=content,
            source_url=f"https://www.xiaohongshu.com/explore/{pid}",
            city_code=city,
            status="PROCESSED",
            review_status="APPROVED",
            raw_data={},
        )
        db.add(note)
        rows.append(note)
    db.commit()
    return rows


def test_list_notes_supports_keyword_filter_against_title(client: TestClient, db_session: Session) -> None:
    _seed_notes_for_keyword_search(db_session)

    response = client.get("/api/v1/notes?keyword=艺术展", headers=_auth())

    assert response.status_code == 200
    titles = [row["title"] for row in response.json()["data"]["items"]]
    assert "上海周末艺术展汇总" in titles
    assert "宁波艺术展活动汇总" in titles
    assert "宁波咖啡店打卡" not in titles
    assert response.json()["pagination"]["total"] == 2


def test_list_notes_supports_keyword_filter_against_content(client: TestClient, db_session: Session) -> None:
    _seed_notes_for_keyword_search(db_session)

    response = client.get("/api/v1/notes?keyword=咖啡", headers=_auth())

    assert response.status_code == 200
    titles = [row["title"] for row in response.json()["data"]["items"]]
    assert titles == ["宁波咖啡店打卡"]


def test_list_notes_empty_or_missing_keyword_returns_all(client: TestClient, db_session: Session) -> None:
    seeded = _seed_notes_for_keyword_search(db_session)

    response_empty = client.get("/api/v1/notes?keyword=", headers=_auth())
    response_missing = client.get("/api/v1/notes", headers=_auth())

    assert response_empty.status_code == 200
    assert response_missing.status_code == 200
    assert response_empty.json()["pagination"]["total"] == len(seeded)
    assert response_missing.json()["pagination"]["total"] == len(seeded)


def test_list_notes_keyword_with_no_match_returns_empty(client: TestClient, db_session: Session) -> None:
    _seed_notes_for_keyword_search(db_session)

    response = client.get("/api/v1/notes?keyword=不存在的关键字", headers=_auth())

    assert response.status_code == 200
    assert response.json()["data"]["items"] == []
    assert response.json()["pagination"]["total"] == 0
