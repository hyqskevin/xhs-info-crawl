from app.services.crawler import AuthenticationRequired
from app.services.pipeline import deduplicate_results, process_with_isolation, run_stage, title_matches_keywords
from app.models.activity import Activity
from app.models.config import City, Keyword
from app.models.note import Note
from app.models.task import CrawlTask, TaskLog
from app.tasks.crawl_task import prepare_existing_note
from app.tasks import crawl_task
from datetime import datetime, timezone
from sqlalchemy import select


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


def test_title_must_contain_at_least_one_corresponding_keyword():
    assert title_matches_keywords("宁波周末活动合集", ["活动"])
    assert title_matches_keywords("SUMMER EXHIBITION", ["exhibition"])
    assert not title_matches_keywords("宁波发票红包过期", ["活动", "展览"])
    assert title_matches_keywords("宁波展览", ["活动", "展览"])
    assert not title_matches_keywords("", ["活动"])


def test_duplicate_search_results_merge_their_matched_keywords():
    rows = [
        ("nb", {"title": "宁波活动展览", "url": "https://xhs/1", "_matched_keywords": ["活动"]}),
        ("nb", {"title": "宁波活动展览", "url": "https://xhs/1", "_matched_keywords": ["展览", "活动"]}),
    ]

    result = deduplicate_results(rows)

    assert result[0][1]["_matched_keywords"] == ["活动", "展览"]


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


def test_keyword_search_skips_titles_without_the_corresponding_keyword(db_session, monkeypatch, tmp_path):
    city = City(name="宁波", code="nb", enabled=True, recent_filter="一周内")
    keyword = Keyword(city_code="nb", word="活动", enabled=True)
    task = CrawlTask(type="mixed", status="PENDING", params={"city": "nb", "keywords": ["活动"], "recent_filter": "一周内", "blogger_ids": []})
    db_session.add_all([city, keyword, task])
    db_session.commit()
    calls = {"note": [], "download": []}

    class FakeAdapter:
        def __init__(self, _settings):
            pass

        def search_recent(self, _query, _recent_filter):
            return [
                {"title": "宁波周末活动合集", "url": "https://xhs/matched"},
                {"title": "宁波发票红包过期", "url": "https://xhs/unrelated"},
            ]

        def note(self, url):
            calls["note"].append(url)
            return {"content": ""}

        def download(self, url, _folder):
            calls["download"].append(url)
            return []

    def fake_process(db, current_task, _city, item, adapter, _settings):
        adapter.note(item["url"])
        adapter.download(item["url"], tmp_path)
        current_task.extracted_notes += 1
        current_task.success_notes += 1
        db.commit()
        return True

    monkeypatch.setattr(crawl_task, "SessionLocal", lambda: db_session)
    monkeypatch.setattr(crawl_task, "OpenCLIAdapter", FakeAdapter)
    monkeypatch.setattr(crawl_task, "process_note", fake_process)

    crawl_task.run_crawl.run(task.id)

    task = db_session.get(CrawlTask, task.id)
    assert calls == {"note": ["https://xhs/matched"], "download": ["https://xhs/matched"]}
    assert task.total_notes == 2
    assert task.skipped_notes == 1
    messages = list(db_session.scalars(select(TaskLog.message).where(TaskLog.task_id == task.id)))
    assert any("标题未包含关键词" in message and "https://xhs/unrelated" in message for message in messages)


def test_worker_finishes_current_note_then_stops_before_the_next(db_session, monkeypatch):
    city = City(name="宁波", code="nb", enabled=True, recent_filter="一周内")
    keyword = Keyword(city_code="nb", word="活动", enabled=True)
    task = CrawlTask(type="mixed", status="PENDING", params={"city": "nb", "keywords": ["活动"], "recent_filter": "一周内", "blogger_ids": []})
    db_session.add_all([city, keyword, task]); db_session.commit()
    processed = []

    class FakeAdapter:
        def __init__(self, _settings):
            pass

        def search_recent(self, _query, _recent_filter):
            return [
                {"title": "宁波活动一", "url": "https://xhs/1"},
                {"title": "宁波活动二", "url": "https://xhs/2"},
            ]

    def fake_process(db, current_task, _city, item, _adapter, _settings):
        processed.append(item["url"])
        current_task.extracted_notes += 1
        current_task.success_notes += 1
        current_task.status = "STOP_REQUESTED"
        db.commit()
        return True

    monkeypatch.setattr(crawl_task, "SessionLocal", lambda: db_session)
    monkeypatch.setattr(crawl_task, "OpenCLIAdapter", FakeAdapter)
    monkeypatch.setattr(crawl_task, "process_note", fake_process)

    crawl_task.run_crawl.run(task.id)

    task = db_session.get(CrawlTask, task.id)
    assert processed == ["https://xhs/1"]
    assert task.status == "STOPPED"
    assert task.extracted_notes == 1
    messages = list(db_session.scalars(select(TaskLog.message).where(TaskLog.task_id == task.id)))
    assert "任务已安全停止" in messages
