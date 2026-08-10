"""去重候选接口：默认过滤悬空对（note_a/note_b 不可见）。"""
from datetime import datetime, timezone

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.security import create_access_token
from app.models.duplicate import NoteDuplicateCandidate
from app.models.note import Note


def _auth() -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token({'sub': 'admin', 'role': 'admin'})}"}


_SEQ = {"n": 0}


def _next_platform_id() -> str:
    _SEQ["n"] += 1
    return f"p-{_SEQ['n']}"


def _make_note(
    db: Session, *, title: str, review_status: str = "PENDING"
) -> Note:
    note = Note(
        title=title,
        content="",
        source_url=f"https://xhs.example/n/{title}",
        platform_note_id=_next_platform_id(),
        city_code="sh",
        task_id=0,
        status="PENDING",
        published_at=datetime.now(timezone.utc),
        review_status=review_status,
    )
    db.add(note)
    db.flush()
    return note


def test_pending_list_excludes_orphan_a_side(client, db_session: Session) -> None:
    a_deleted = _make_note(db_session, title="orphan-A", review_status="MERGED")
    b_visible = _make_note(db_session, title="visible-B")

    cand = NoteDuplicateCandidate(
        note_a_id=a_deleted.id,
        note_b_id=b_visible.id,
        similarity=0.9,
        status="pending",
    )
    db_session.add(cand)
    db_session.commit()

    resp = client.get("/api/v1/duplicates", headers=_auth())
    assert resp.status_code == 200
    items = resp.json()["data"]["items"]
    ids = {row["id"] for row in items}
    assert cand.id not in ids


def test_pending_list_excludes_orphan_b_side(client, db_session: Session) -> None:
    a_visible = _make_note(db_session, title="visible-A")
    b_deleted = _make_note(db_session, title="orphan-B", review_status="DELETED")

    cand = NoteDuplicateCandidate(
        note_a_id=a_visible.id,
        note_b_id=b_deleted.id,
        similarity=0.9,
        status="pending",
    )
    db_session.add(cand)
    db_session.commit()

    resp = client.get("/api/v1/duplicates", headers=_auth())
    assert resp.status_code == 200
    ids = {row["id"] for row in resp.json()["data"]["items"]}
    assert cand.id not in ids


def test_pending_list_keeps_visible_pair(client, db_session: Session) -> None:
    a = _make_note(db_session, title="keep-A")
    b = _make_note(db_session, title="keep-B")
    cand = NoteDuplicateCandidate(
        note_a_id=a.id,
        note_b_id=b.id,
        similarity=0.7,
        status="pending",
    )
    db_session.add(cand)
    db_session.commit()

    resp = client.get("/api/v1/duplicates", headers=_auth())
    assert resp.status_code == 200
    ids = {row["id"] for row in resp.json()["data"]["items"]}
    assert cand.id in ids


def test_resolved_candidates_still_excluded(client, db_session: Session) -> None:
    a = _make_note(db_session, title="resolved-A")
    b = _make_note(db_session, title="resolved-B")
    cand = NoteDuplicateCandidate(
        note_a_id=a.id,
        note_b_id=b.id,
        similarity=0.6,
        status="merged",
    )
    db_session.add(cand)
    db_session.commit()

    resp = client.get("/api/v1/duplicates", headers=_auth())
    assert resp.status_code == 200
    assert all(row["id"] != cand.id for row in resp.json()["data"]["items"])