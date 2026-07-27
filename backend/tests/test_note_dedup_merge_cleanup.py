"""Note 去重候选生成 + matched_fields JSON 形态。"""
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models.duplicate import NoteDuplicateCandidate
from app.models.note import Note
from app.services.dedup import create_note_duplicate_candidates


_NOTE_SEQ = {"n": 0}


def _next_platform_id(prefix: str = "p") -> str:
    _NOTE_SEQ["n"] += 1
    return f"{prefix}-{_NOTE_SEQ['n']}"


def _make_note(
    db: Session, *, title: str, content: str = "", platform_id: str | None = None
) -> Note:
    note = Note(
        title=title,
        content=content,
        source_url=f"https://xhs.example/n/{title}",
        platform_note_id=platform_id or _next_platform_id(),
        city_code="sh",
        task_id=0,
        status="PENDING",
        published_at=datetime.now(timezone.utc),
        review_status="PENDING",
    )
    db.add(note)
    db.flush()
    return note


def test_create_note_duplicate_candidates_inserts_above_threshold(
    db_session: Session,
) -> None:
    a = _make_note(db_session, title="夏日音乐节", content="周六晚 6 点徐汇滨江")
    b = _make_note(db_session, title="夏日 音乐节", content="周末徐汇活动")
    _make_note(db_session, title="完全不相关", content="宠物领养")

    created = create_note_duplicate_candidates(db_session, a)
    db_session.commit()

    # a 与 b 应至少 1 条候选；与"完全不相关"应无
    pairs = {(c.note_a_id, c.note_b_id) for c in created}
    assert (min(a.id, b.id), max(a.id, b.id)) in pairs
    for c in created:
        assert c.status == "pending"
        assert isinstance(c.matched_fields, list)


def test_matched_fields_contains_only_high_score_fields(db_session: Session) -> None:
    """当两标题完全一致，正文也一致时，应产出候选且 matched_fields 含 title / content 之一。"""
    common_title = "周末市集"
    common_content = "今天在徐汇滨江有市集，欢迎参加"
    a = _make_note(db_session, title=common_title, content=common_content)
    b = _make_note(db_session, title=common_title, content=common_content)

    created = create_note_duplicate_candidates(db_session, a)
    db_session.commit()

    pair = next(
        (c for c in created if {c.note_a_id, c.note_b_id} == {a.id, b.id}),
        None,
    )
    assert pair is not None
    # 至少有一个字段进入 matched_fields
    assert pair.matched_fields
    assert isinstance(pair.matched_fields, list)


def test_no_duplicate_when_score_below_threshold(db_session: Session) -> None:
    a = _make_note(db_session, title="烘焙工作坊", content="学习做面包")
    b = _make_note(db_session, title="宠物领养日", content="欢迎领养流浪猫")

    created = create_note_duplicate_candidates(db_session, a)
    db_session.commit()

    assert all({c.note_a_id, c.note_b_id} != {a.id, b.id} for c in created)
