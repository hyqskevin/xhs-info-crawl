"""poster 路径校验统一 + notes OCR 异常可见性（spec: 2026-07-27-poster-path-and-ocr-logging-design.md）。

- 8.1 note_image_by_id 用 str.startswith 可被同前缀兄弟目录绕过，应改 is_relative_to 后 404。
- 8.2 notes 列表 OCR 聚合异常不得静默吞掉，应记 WARNING 日志且响应仍 200。
"""
import logging
from types import SimpleNamespace

from sqlalchemy import select

from app.api.v1 import poster_tasks
from app.core.security import create_access_token
from app.models.note import Note, NoteImage


def _auth() -> dict:
    return {"Authorization": f"Bearer {create_access_token({'sub': 'admin', 'role': 'admin'})}"}


def test_note_image_by_id_rejects_sibling_prefix_escape(client, db_session, tmp_path, monkeypatch):
    """storage_key 逃逸到 base 的同前缀兄弟目录时必须 404。

    base=/tmp/x/data，target=/tmp/x/data-evil/secret.jpg：
    str.startswith 误判通过（bug），is_relative_to 正确拒绝。
    """
    base = tmp_path / "data"
    evil = tmp_path / "data-evil"
    base.mkdir()
    evil.mkdir()
    secret = evil / "secret.jpg"
    secret.write_bytes(b"not-a-real-jpeg-but-secret")
    monkeypatch.setattr(poster_tasks, "get_settings", lambda: SimpleNamespace(data_dir=base))

    note = Note(task_id=1, platform_note_id="ab" * 12, title="t", content="", source_url="u", city_code="nb", status="DONE")
    db_session.add(note)
    db_session.flush()
    image = NoteImage(note_id=note.id, storage_key="../data-evil/secret.jpg")
    db_session.add(image)
    db_session.commit()

    resp = client.get(f"/api/v1/posters/note-image-by-id/{image.id}", headers=_auth())
    assert resp.status_code == 404


def test_note_image_by_id_serves_legitimate_file(client, db_session, tmp_path, monkeypatch):
    """正常 storage_key 不受影响，仍返回 200。"""
    base = tmp_path / "data"
    legit = base / "archive" / "img.jpg"
    legit.parent.mkdir(parents=True)
    legit.write_bytes(b"jpeg-bytes")
    monkeypatch.setattr(poster_tasks, "get_settings", lambda: SimpleNamespace(data_dir=base))

    note = Note(task_id=1, platform_note_id="cd" * 12, title="t", content="", source_url="u", city_code="nb", status="DONE")
    db_session.add(note)
    db_session.flush()
    image = NoteImage(note_id=note.id, storage_key="archive/img.jpg")
    db_session.add(image)
    db_session.commit()

    resp = client.get(f"/api/v1/posters/note-image-by-id/{image.id}", headers=_auth())
    assert resp.status_code == 200
    assert resp.content == b"jpeg-bytes"


def test_notes_list_ocr_aggregation_failure_logs_warning(client, db_session, monkeypatch, caplog):
    """OCR 聚合查询失败：响应仍 200（降级无 OCR），但必须留下 WARNING 日志。"""
    note = Note(task_id=1, platform_note_id="ef" * 12, title="t", content="", source_url="u", city_code="nb", status="DONE")
    db_session.add(note)
    db_session.commit()

    real_execute = db_session.execute

    def flaky_execute(statement, *args, **kwargs):
        if "note_images" in str(statement):
            raise RuntimeError("simulated db failure")
        return real_execute(statement, *args, **kwargs)

    monkeypatch.setattr(db_session, "execute", flaky_execute)

    with caplog.at_level(logging.WARNING):
        resp = client.get("/api/v1/notes", headers=_auth())
    assert resp.status_code == 200
    assert any(item["id"] == note.id for item in resp.json()["data"]["items"])
    assert any("OCR" in record.message and record.levelno == logging.WARNING for record in caplog.records)
