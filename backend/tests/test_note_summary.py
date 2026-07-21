"""推文列表 summary 长度保护测试。"""
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.security import create_access_token
from app.models.config import City
from app.models.note import Note, NoteImage


def _auth() -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token({'sub': 'admin', 'role': 'admin'})}"}


def _city(db: Session) -> None:
    db.add(City(name="nb", code="nb", enabled=True))
    db.commit()


def _seed_note(db: Session, content: str, ocr_texts: list[str]) -> int:
    note = Note(
        task_id=1,
        platform_note_id=f"sum-test-{hash(content) & 0xFFFF:X}",
        title="测试推文",
        content=content,
        source_url="https://xhs.demo/x",
        city_code="nb",
        status="PROCESSED",
        review_status="PENDING",
        raw_data={},
    )
    db.add(note)
    db.commit()
    db.refresh(note)
    for index, text in enumerate(ocr_texts, 1):
        db.add(NoteImage(note_id=note.id, storage_key=f"k{index}", original_url=f"https://xhs.demo/{index}.jpg", ocr_status="OCR_DONE", ocr_text=text))
    db.commit()
    db.refresh(note)
    return note.id


def test_summary_includes_content_and_five_ocr_blocks_at_most(client: TestClient, db_session: Session) -> None:
    _city(db_session)
    note_id = _seed_note(db_session, content="正文段落", ocr_texts=[f"图片{i}文字" for i in range(1, 9)])

    response = client.get("/api/v1/notes", headers=_auth())

    assert response.status_code == 200
    items = response.json()["data"]["items"]
    note_item = next(item for item in items if item["id"] == note_id)
    summary = note_item["summary"]
    assert "正文段落" in summary
    for i in range(1, 6):
        assert f"[图片 {i} OCR]" in summary
    assert "[图片 6 OCR]" not in summary
    assert "[图片 7 OCR]" not in summary


def test_summary_truncated_when_exceeds_4kb(client: TestClient, db_session: Session) -> None:
    _city(db_session)
    long_text = "字" * 500
    note_id = _seed_note(db_session, content="正文段落", ocr_texts=[long_text for _ in range(50)])

    response = client.get("/api/v1/notes", headers=_auth())

    assert response.status_code == 200
    items = response.json()["data"]["items"]
    note_item = next(item for item in items if item["id"] == note_id)
    assert len(note_item["summary"].encode("utf-8")) <= 4096
    assert note_item["summary_truncated"] is True


def test_summary_under_4kb_not_truncated(client: TestClient, db_session: Session) -> None:
    _city(db_session)
    note_id = _seed_note(db_session, content="简短正文", ocr_texts=["图1", "图2", "图3"])

    response = client.get("/api/v1/notes", headers=_auth())

    assert response.status_code == 200
    items = response.json()["data"]["items"]
    note_item = next(item for item in items if item["id"] == note_id)
    assert note_item["summary_truncated"] is False


def test_summary_empty_when_no_content_and_no_ocr(client: TestClient, db_session: Session) -> None:
    _city(db_session)
    note_id = _seed_note(db_session, content="", ocr_texts=[])

    response = client.get("/api/v1/notes", headers=_auth())

    assert response.status_code == 200
    items = response.json()["data"]["items"]
    note_item = next(item for item in items if item["id"] == note_id)
    assert note_item["summary"] == ""
    assert note_item["summary_truncated"] is False


def test_list_response_includes_summary_truncated_field_for_every_row(client: TestClient, db_session: Session) -> None:
    _city(db_session)
    _seed_note(db_session, content="", ocr_texts=[])

    response = client.get("/api/v1/notes", headers=_auth())

    assert response.status_code == 200
    items = response.json()["data"]["items"]
    assert len(items) >= 1
    for item in items:
        assert "summary_truncated" in item
        assert isinstance(item["summary_truncated"], bool)
