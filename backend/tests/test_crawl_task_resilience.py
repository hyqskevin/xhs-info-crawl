from app.services.crawler import AuthenticationRequired
from app.services.pipeline import deduplicate_results, process_with_isolation, run_stage, title_matches_keywords
from app.models.activity import Activity
from app.models.blogger_city import BloggerCity
from app.models.config import Blogger, City, Keyword
from app.models.note import Note
from app.models.task import CrawlTask, TaskLog
from app.tasks.crawl_task import prepare_existing_note
from app.tasks import crawl_task
from datetime import datetime, timezone
from types import SimpleNamespace
from sqlalchemy import select


def _configured_bloggers(db_session, usernames: list[str]):
    city = City(name="宁波", code="nb", enabled=True, recent_filter="一周内")
    db_session.add(city)
    db_session.flush()
    bloggers = []
    for index, username in enumerate(usernames, 1):
        blogger = Blogger(
            platform_user_id=f"user-{index}",
            username=username,
            profile_url=f"https://www.xiaohongshu.com/user/profile/user-{index}",
            city_code="nb",
            enabled=True,
        )
        db_session.add(blogger)
        db_session.flush()
        db_session.add(BloggerCity(blogger_id=blogger.id, city_code="nb", enabled=True))
        bloggers.append(blogger)
    db_session.commit()
    return bloggers


def test_one_blogger_discovery_failure_does_not_discard_other_results(db_session, monkeypatch):
    broken, good = _configured_bloggers(db_session, ["坏账号", "正常账号"])
    task = CrawlTask(
        type="mixed",
        status="PENDING",
        run_token="blogger-token",
        params={
            "city": "nb",
            "keywords": [],
            "recent_filter": "一周内",
            "blogger_ids": [broken.id, good.id],
        },
    )
    db_session.add(task)
    db_session.commit()
    calls = []
    processed = []

    class FakeAdapter:
        def __init__(self, _settings):
            pass

        def bind_task(self, *_args, **_kwargs):
            pass

        def blogger_notes(self, username, _profile_url):
            calls.append(username)
            if username == "坏账号":
                raise RuntimeError("user store was not found")
            return [{
                "title": "宁波活动",
                "url": "https://www.xiaohongshu.com/explore/signed-note?xsec_token=secret",
            }]

    def fake_process(db, current_task, _run_token, _city, item, _adapter, _settings):
        processed.append(item["url"].split("?")[0])
        current_task.extracted_notes += 1
        current_task.success_notes += 1
        db.commit()
        return True

    monkeypatch.setattr(crawl_task, "SessionLocal", lambda: db_session)
    monkeypatch.setattr(crawl_task, "OpenCLIAdapter", FakeAdapter)
    monkeypatch.setattr(crawl_task, "process_note", fake_process)

    crawl_task.run_crawl.run(task.id, "blogger-token")

    task = db_session.get(CrawlTask, task.id)
    assert calls == ["坏账号", "正常账号"]
    assert processed == ["https://www.xiaohongshu.com/explore/signed-note"]
    assert task.status == "COMPLETED_WITH_ERRORS"
    assert "坏账号" in (task.error_message or "")
    messages = list(db_session.scalars(select(TaskLog.message).where(TaskLog.task_id == task.id)))
    assert any("博主 '坏账号' 抓取失败" in message for message in messages)
    assert all("xsec_token=secret" not in message for message in messages)


def test_blogger_authentication_failure_still_pauses_the_batch(db_session, monkeypatch):
    first, second = _configured_bloggers(db_session, ["需登录账号", "不应调用账号"])
    task = CrawlTask(
        type="mixed",
        status="PENDING",
        run_token="auth-token",
        params={
            "city": "nb",
            "keywords": [],
            "recent_filter": "一周内",
            "blogger_ids": [first.id, second.id],
        },
    )
    db_session.add(task)
    db_session.commit()
    calls = []

    class FakeAdapter:
        def __init__(self, _settings):
            pass

        def bind_task(self, *_args, **_kwargs):
            pass

        def blogger_notes(self, username, _profile_url):
            calls.append(username)
            raise AuthenticationRequired("login")

    monkeypatch.setattr(crawl_task, "SessionLocal", lambda: db_session)
    monkeypatch.setattr(crawl_task, "OpenCLIAdapter", FakeAdapter)

    crawl_task.run_crawl.run(task.id, "auth-token")

    task = db_session.get(CrawlTask, task.id)
    assert calls == ["需登录账号"]
    assert task.status == "PAUSED"
    assert task.error_message == "login"


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


def test_existing_note_is_found_by_platform_id_when_access_token_changes(db_session):
    note = Note(
        task_id=1,
        platform_note_id="same-note",
        title="活动",
        content="正文",
        source_url="https://www.xiaohongshu.com/explore/same-note?xsec_token=old",
        city_code="nb",
        status="PROCESSED",
        raw_data={},
    )
    db_session.add(note)
    db_session.commit()

    assert prepare_existing_note(
        db_session,
        "https://www.xiaohongshu.com/discovery/item/same-note?xsec_token=new",
    ) is True
    db_session.refresh(note)
    assert note.source_url.endswith("xsec_token=new")


def test_one_note_keeps_valid_and_unknown_activities_but_skips_window_outliers(db_session, monkeypatch, tmp_path):
    db_session.add(City(name="宁波", code="nb", enabled=True))
    db_session.flush()
    task = CrawlTask(
        type="mixed",
        status="RUNNING",
        params={"city": "nb"},
        started_at=datetime(2026, 7, 17, tzinfo=timezone.utc),
    )
    db_session.add(task)
    db_session.commit()

    class FakeAdapter:
        def note(self, _url):
            return {"content": "活动正文"}

        def download(self, _url, _folder):
            return []

    extracted = [
        {"name": "有效活动", "start_time": "2026-07-20T10:00:00", "end_time": None, "location": "文化广场", "status": "RAW", "confidence": 0.9, "source_image_indexes": []},
        {"name": "历史活动", "start_time": "2024-07-20T10:00:00", "end_time": None, "location": "文化广场", "status": "RAW", "confidence": 0.9, "source_image_indexes": []},
        {"name": "远期活动", "start_time": "2026-10-20T10:00:00", "end_time": None, "location": "文化广场", "status": "RAW", "confidence": 0.9, "source_image_indexes": []},
        {"name": "日期待确认", "start_time": None, "end_time": None, "location": "文化广场", "status": "NEEDS_REVIEW", "confidence": 0.5, "source_image_indexes": []},
    ]
    monkeypatch.setattr(crawl_task, "extract_activities", lambda *_args, **_kwargs: extracted)
    settings = SimpleNamespace(
        pipeline_stage_max_retries=1,
        pipeline_stage_retry_delay_seconds=0,
        archive_dir=tmp_path / "archive",
        ocr_enabled=False,
        minimax_api_key="",
        activity_future_window_days=60,
        celery_timezone="Asia/Shanghai",
    )

    crawl_task.process_note(
        db_session,
        task,
        task.run_token,
        "nb",
        {"title": "宁波活动合集", "url": "https://xhs/window-test"},
        FakeAdapter(),
        settings,
    )

    activities = list(db_session.scalars(select(Activity).order_by(Activity.id)))
    assert [activity.name for activity in activities] == ["有效活动", "日期待确认"]
    assert activities[1].start_time is None
    assert activities[1].status == "NEEDS_REVIEW"
    assert task.skipped_activities == 2
    messages = list(db_session.scalars(select(TaskLog.message).where(TaskLog.task_id == task.id)))
    assert any("历史活动" in message and "past" in message for message in messages)
    assert any("远期活动" in message and "future" in message for message in messages)


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

    def fake_process(db, current_task, _run_token, _city, item, adapter, _settings):
        adapter.note(item["url"])
        adapter.download(item["url"], tmp_path)
        current_task.extracted_notes += 1
        current_task.success_notes += 1
        db.commit()
        return True

    monkeypatch.setattr(crawl_task, "SessionLocal", lambda: db_session)
    monkeypatch.setattr(crawl_task, "OpenCLIAdapter", FakeAdapter)
    monkeypatch.setattr(crawl_task, "process_note", fake_process)

    crawl_task.run_crawl.run(task.id, task.run_token)

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

    def fake_process(db, current_task, _run_token, _city, item, _adapter, _settings):
        processed.append(item["url"])
        current_task.extracted_notes += 1
        current_task.success_notes += 1
        current_task.status = "STOP_REQUESTED"
        db.commit()
        return True

    monkeypatch.setattr(crawl_task, "SessionLocal", lambda: db_session)
    monkeypatch.setattr(crawl_task, "OpenCLIAdapter", FakeAdapter)
    monkeypatch.setattr(crawl_task, "process_note", fake_process)

    crawl_task.run_crawl.run(task.id, task.run_token)

    task = db_session.get(CrawlTask, task.id)
    assert processed == ["https://xhs/1"]
    assert task.status == "STOPPED"
    assert task.extracted_notes == 1
    messages = list(db_session.scalars(select(TaskLog.message).where(TaskLog.task_id == task.id)))
    assert "任务已安全停止" in messages


def test_worker_does_not_restart_a_pending_task_that_was_already_stopped(db_session, monkeypatch):
    task = CrawlTask(type="mixed", status="STOPPED", params={"city": "nb", "keywords": ["活动"], "recent_filter": "一周内", "blogger_ids": []})
    db_session.add(task); db_session.commit()
    searched = []

    class FakeAdapter:
        def __init__(self, _settings):
            pass

        def search_recent(self, *_args):
            searched.append(True)
            return []

    monkeypatch.setattr(crawl_task, "SessionLocal", lambda: db_session)
    monkeypatch.setattr(crawl_task, "OpenCLIAdapter", FakeAdapter)

    crawl_task.run_crawl.run(task.id, task.run_token)

    task = db_session.get(CrawlTask, task.id)
    assert task.status == "STOPPED"
    assert searched == []
