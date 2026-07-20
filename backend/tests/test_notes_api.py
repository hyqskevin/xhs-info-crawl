from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.security import create_access_token
from app.models.activity import Activity
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
        Activity(note_id=note.id, name="活动一", city_code="nb", type="展览", status="RAW"),
        Activity(note_id=note.id, name="活动二", city_code="nb", type="演出", status="RAW"),
    ])
    db.commit()
    return note


def test_notes_list_returns_one_row_per_post(client: TestClient, db_session: Session) -> None:
    note = _note_with_activities(db_session)

    response = client.get("/api/v1/notes", headers=_auth())

    assert response.status_code == 200
    assert response.json()["data"]["items"] == [
        {
            "id": note.id,
            "title": "宁波周末合集",
            "city_code": "nb",
            "published_at": None,
            "created_at": note.created_at.isoformat(),
            "processing_status": "PROCESSED",
            "review_status": "PENDING",
            "activity_count": 2,
            "source_url": note.source_url,
        }
    ]


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


def test_batch_approve_notes_approves_post_not_children(client: TestClient, db_session: Session) -> None:
    note = _note_with_activities(db_session)

    response = client.post("/api/v1/notes/batch/approve", json={"ids": [note.id]}, headers=_auth())

    assert response.status_code == 200
    db_session.refresh(note)
    assert note.review_status == "APPROVED"
    assert {item.status for item in db_session.query(Activity).all()} == {"RAW"}
