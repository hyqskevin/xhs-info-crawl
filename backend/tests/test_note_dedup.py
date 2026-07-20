from app.models.duplicate import NoteDuplicateCandidate
from app.models.note import Note
from app.services.dedup import create_note_duplicate_candidates


def test_note_dedup_compares_posts_not_children_and_is_idempotent(db_session) -> None:
    first = Note(task_id=1, platform_note_id="a", title="宁波周末艺术展活动", content="艺术展览与市集", source_url="https://xhs/a", city_code="nb", status="PROCESSED", raw_data={})
    second = Note(task_id=2, platform_note_id="b", title="宁波周末艺术展活动合集", content="艺术展览与市集", source_url="https://xhs/b", city_code="nb", status="PROCESSED", raw_data={})
    db_session.add_all([first, second]); db_session.commit()

    assert len(create_note_duplicate_candidates(db_session, second)) == 1
    db_session.commit()
    assert create_note_duplicate_candidates(db_session, second) == []
    candidate = db_session.query(NoteDuplicateCandidate).one()
    assert {candidate.note_a_id, candidate.note_b_id} == {first.id, second.id}
