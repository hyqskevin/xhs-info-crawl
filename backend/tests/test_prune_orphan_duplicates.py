"""prune_orphan_duplicates 一次性脚本：把指向已不可见 note 的 pending 候选标为 superseded。"""
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models.duplicate import NoteDuplicateCandidate
from app.models.note import Note
from app.services.prune_orphan_duplicates import prune_orphan_duplicates


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


def _make_candidate(db: Session, *, a_id: int, b_id: int) -> NoteDuplicateCandidate:
    cand = NoteDuplicateCandidate(
        note_a_id=a_id, note_b_id=b_id, similarity=0.7, status="pending"
    )
    db.add(cand)
    db.flush()
    return cand


def test_prune_marks_orphan_pair_superseded(db_session: Session) -> None:
    a = _make_note(db_session, title="orphan-A", review_status="MERGED")
    b = _make_note(db_session, title="keep-B")
    cand = _make_candidate(db_session, a_id=a.id, b_id=b.id)
    db_session.commit()

    result = prune_orphan_duplicates(db_session)

    db_session.refresh(cand)
    assert cand.status == "superseded"
    assert cand.resolved_at is not None
    assert result["pruned"] == 1
    assert result["kept"] == 0


def test_prune_keeps_visible_pair_pending(db_session: Session) -> None:
    a = _make_note(db_session, title="ok-A")
    b = _make_note(db_session, title="ok-B")
    cand = _make_candidate(db_session, a_id=a.id, b_id=b.id)
    db_session.commit()

    result = prune_orphan_duplicates(db_session)
    db_session.refresh(cand)
    assert cand.status == "pending"
    assert result["pruned"] == 0
    assert result["kept"] == 1


def test_prune_handles_both_sides_deleted(db_session: Session) -> None:
    a = _make_note(db_session, title="a", review_status="DELETED")
    b = _make_note(db_session, title="b", review_status="MERGED")
    cand = _make_candidate(db_session, a_id=a.id, b_id=b.id)
    db_session.commit()

    result = prune_orphan_duplicates(db_session)
    db_session.refresh(cand)
    assert cand.status == "superseded"
    assert result["pruned"] == 1


def test_prune_is_idempotent(db_session: Session) -> None:
    a = _make_note(db_session, title="a", review_status="MERGED")
    b = _make_note(db_session, title="b")
    cand = _make_candidate(db_session, a_id=a.id, b_id=b.id)
    db_session.commit()

    prune_orphan_duplicates(db_session)
    result = prune_orphan_duplicates(db_session)

    # 第二次跑时该候选已 superseded，跳过
    assert result["pruned"] == 0
    assert result["kept"] == 0


def test_prune_does_not_touch_resolved_candidates(db_session: Session) -> None:
    a = _make_note(db_session, title="merged-A", review_status="MERGED")
    b = _make_note(db_session, title="merged-B")
    cand = NoteDuplicateCandidate(
        note_a_id=a.id, note_b_id=b.id, similarity=0.6, status="merged"
    )
    db_session.add(cand)
    db_session.commit()

    result = prune_orphan_duplicates(db_session)
    db_session.refresh(cand)
    assert cand.status == "merged"  # 已 merged 不受影响
    assert result["pruned"] == 0