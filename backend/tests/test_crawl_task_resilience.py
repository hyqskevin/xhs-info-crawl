from app.services.crawler import AuthenticationRequired
from app.services.pipeline import deduplicate_results, process_with_isolation, run_stage
from app.models.activity import Activity
from app.models.note import Note
from app.tasks.crawl_task import prepare_existing_note
from datetime import datetime, timezone


def test_run_stage_retries_a_temporary_failure():
    attempts = []
    def operation():
        attempts.append(1)
        if len(attempts) == 1:
            raise RuntimeError("temporary")
        return "ok"

    assert run_stage(operation, attempts=2, delay_seconds=0) == "ok"
    assert len(attempts) == 2


def test_search_results_are_deduplicated_by_source_url():
    rows = [("nb", {"title": "A", "url": "https://xhs/1"}), ("nb", {"title": "A2", "url": "https://xhs/1"}), ("nb", {"title": "B", "url": "https://xhs/2"})]
    assert [item[1]["url"] for item in deduplicate_results(rows)] == ["https://xhs/1", "https://xhs/2"]


def test_one_item_failure_does_not_stop_the_remaining_items():
    completed = []
    failed = []
    def processor(item):
        if item == "broken":
            raise ValueError("bad note")
        completed.append(item)

    process_with_isolation(["broken", "good"], processor, lambda item, exc: failed.append((item, str(exc))))

    assert completed == ["good"]
    assert failed == [("broken", "bad note")]


def test_authentication_failure_still_stops_the_batch():
    def processor(_):
        raise AuthenticationRequired("login")

    try:
        process_with_isolation(["note"], processor, lambda *_: None)
    except AuthenticationRequired as exc:
        assert str(exc) == "login"
    else:
        raise AssertionError("AuthenticationRequired must escape item isolation")


def test_existing_legacy_note_with_activity_is_treated_as_complete(db_session):
    note = Note(
        task_id=4,
        platform_note_id="legacy-note",
        title="旧任务笔记",
        content="",
        source_url="https://www.xiaohongshu.com/explore/legacy-note",
        city_code="nb",
        status="OCR_DONE",
        raw_data={},
    )
    db_session.add(note)
    db_session.flush()
    db_session.add(Activity(
        note_id=note.id,
        name="已提取活动",
        city_code="nb",
        start_time=datetime.now(timezone.utc),
        location="文化广场",
        type="其他",
        status="RAW",
    ))
    db_session.commit()

    assert prepare_existing_note(db_session, note.source_url) is True
    assert db_session.get(Note, note.id).status == "PROCESSED"


def test_existing_incomplete_note_is_removed_before_retry(db_session):
    note = Note(
        task_id=4,
        platform_note_id="partial-note",
        title="残缺笔记",
        content="",
        source_url="https://www.xiaohongshu.com/explore/partial-note",
        city_code="nb",
        status="OCR_DONE",
        raw_data={},
    )
    db_session.add(note)
    db_session.commit()

    assert prepare_existing_note(db_session, note.source_url) is False
    assert db_session.get(Note, note.id) is None
