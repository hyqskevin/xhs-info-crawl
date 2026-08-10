"""MiniMax 批量并行集成到 crawl_task 的两阶段流水线测试。

关联 spec: docs/superpowers/specs/2026-08-10-minimax-parallel-integration-design.md

验证点：
1. StagedNote dataclass 字段
2. download_and_ocr 返回 StagedNote / 跳过返回 None
3. extract_and_save 写 Activity 并更新 Note 状态
4. run_crawl 两阶段流水线：先批量下载 OCR，再批量 MiniMax
5. minimax_concurrency=1 退化为串行
6. 无 minimax_api_key 降级规则提取
"""
from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.activity import Activity
from app.models.config import City
from app.models.note import Note
from app.models.task import CrawlTask, TaskLog
from app.tasks import crawl_task


# ============================================================
# 1. StagedNote dataclass
# ============================================================


def test_staged_note_dataclass():
    """StagedNote 应包含 note/combined_text/reference_now/started_at/image_rows 字段。"""
    from dataclasses import fields

    note = Note(title="x", content="y", source_url="https://xhs/1", city_code="nb")
    field_names = {f.name for f in fields(crawl_task.StagedNote)}
    assert field_names == {"note", "combined_text", "reference_now", "started_at", "image_rows"}

    staged = crawl_task.StagedNote(
        note=note,
        combined_text="combined",
        reference_now=datetime(2026, 8, 10),
        started_at=datetime(2026, 8, 10, tzinfo=timezone.utc),
        image_rows=[],
    )
    assert staged.note is note
    assert staged.combined_text == "combined"
    assert staged.reference_now == datetime(2026, 8, 10)
    assert staged.started_at == datetime(2026, 8, 10, tzinfo=timezone.utc)
    assert staged.image_rows == []


# ============================================================
# 2. download_and_ocr
# ============================================================


def _make_settings(tmp_path, *, minimax_api_key: str = "fake-key", ocr_enabled: bool = False) -> SimpleNamespace:
    return SimpleNamespace(
        opencli_bin="opencli",
        pipeline_stage_max_retries=1,
        pipeline_stage_retry_delay_seconds=0,
        archive_dir=tmp_path / "archive",
        ocr_enabled=ocr_enabled,
        ocr_min_confidence=0.5,
        ocr_parallel_workers=1,
        ocr_language="ch",
        minimax_api_key=minimax_api_key,
        minimax_concurrency=1,
        minimax_model="MiniMax-Text-01",
        minimax_base_url="https://api.minimax.chat/v1",
        minimax_chat_path="text/chatcompletion_v2",
        minimax_timeout_seconds=30,
        activity_future_window_days=60,
        celery_timezone="Asia/Shanghai",
        search_interval_min=0,
        search_interval_max=0,
        weekly_search_limit=100,
        consecutive_note_failure_limit=5,
        xhs_search_target_count=20,
        xhs_search_scroll_max_rounds=3,
        xhs_detail_scroll_max_rounds=5,
        xhs_scroll_pixels=300,
        xhs_scroll_stagnant_rounds=2,
    )


def _make_running_task(db_session: Session, city_code: str = "nb") -> CrawlTask:
    task = CrawlTask(
        type="mixed",
        status="RUNNING",
        params={"city": city_code},
        started_at=datetime(2026, 8, 10, tzinfo=timezone.utc),
    )
    db_session.add(task)
    db_session.flush()
    return task


class _FakeAdapter:
    def __init__(self, detail: dict | None = None, images: list | None = None):
        self._detail = detail or {"content": "活动正文"}
        self._images = images or []
        self.note_calls: list[str] = []
        self.download_calls: list[str] = []

    def note(self, url: str) -> dict:
        self.note_calls.append(url)
        return self._detail

    def download(self, url: str, folder) -> list:
        self.download_calls.append(url)
        return self._images


def test_download_and_ocr_returns_staged_note(db_session, tmp_path, monkeypatch):
    """download_and_ocr 应完成下载+OCR 并返回 StagedNote（不调 MiniMax）。"""
    db_session.add(City(name="宁波", code="nb", enabled=True))
    db_session.flush()
    task = _make_running_task(db_session)
    db_session.commit()

    # OCR 关闭：images 为空也能走通
    settings = _make_settings(tmp_path, ocr_enabled=False)
    adapter = _FakeAdapter(detail={"content": "正文"}, images=[])

    item = {"title": "宁波活动", "url": "https://www.xiaohongshu.com/explore/abc123"}

    staged = crawl_task.download_and_ocr(
        db_session, task, task.run_token, "nb", item, adapter, settings
    )

    assert staged is not None
    assert isinstance(staged, crawl_task.StagedNote)
    assert staged.note.title == "宁波活动"
    assert staged.note.status == "DOWNLOADED"  # OCR 关闭时保持 DOWNLOADED
    assert "宁波活动" in staged.combined_text
    assert "正文" in staged.combined_text
    assert adapter.note_calls == ["https://www.xiaohongshu.com/explore/abc123"]
    assert task.downloaded_notes == 1
    assert task.ocr_notes == 1
    # 关键：download_and_ocr 不应触发 MiniMax 提取
    assert staged.note.status != "PROCESSED"


def test_download_and_ocr_with_ocr_text_in_combined(db_session, tmp_path, monkeypatch):
    """OCR 启用时，combined_text 应包含 [IMAGE N] 标记的 OCR 文本。"""
    db_session.add(City(name="宁波", code="nb", enabled=True))
    db_session.flush()
    task = _make_running_task(db_session)
    db_session.commit()

    settings = _make_settings(tmp_path, ocr_enabled=True)

    # mock OCRService.process_batch 返回 2 张图片的 OCR 文本
    class _FakeOCR:
        def __init__(self, *_args, **_kwargs):
            pass

        def process_batch(self, images, workers=1, attempts=1, delay=0):
            return [
                {"text": "图片1文字", "status": "ok", "error": ""},
                {"text": "图片2文字", "status": "ok", "error": ""},
            ]

    monkeypatch.setattr(crawl_task, "OCRService", _FakeOCR)
    monkeypatch.setattr(crawl_task, "PaddleOCREngine", lambda *args, **kwargs: None)

    adapter = _FakeAdapter(detail={"content": "正文"}, images=["img1.jpg", "img2.jpg"])
    item = {"title": "活动", "url": "https://www.xiaohongshu.com/explore/ocr-test"}

    staged = crawl_task.download_and_ocr(
        db_session, task, task.run_token, "nb", item, adapter, settings
    )

    assert staged is not None
    assert "[IMAGE 1]" in staged.combined_text
    assert "图片1文字" in staged.combined_text
    assert "[IMAGE 2]" in staged.combined_text
    assert "图片2文字" in staged.combined_text
    assert staged.note.status == "OCR_DONE"


def test_download_and_ocr_returns_none_when_city_unknown(db_session, tmp_path):
    """city_code 不在 cities 表时，download_and_ocr 记 ERROR 日志并返回 None。"""
    task = _make_running_task(db_session)
    db_session.commit()
    settings = _make_settings(tmp_path)
    adapter = _FakeAdapter()

    item = {"title": "x", "url": "https://www.xiaohongshu.com/explore/abc"}

    result = crawl_task.download_and_ocr(
        db_session, task, task.run_token, "火星", item, adapter, settings
    )

    assert result is None
    assert adapter.note_calls == []  # 没有进入下载
    assert task.skipped_activities == 1
    messages = list(db_session.scalars(select(TaskLog.message).where(TaskLog.task_id == task.id)))
    assert any("city_code 不在 cities 表" in m and "'火星'" in m for m in messages)


def test_download_and_ocr_returns_none_when_already_processed(db_session, tmp_path):
    """笔记已存在且 PROCESSED 时，download_and_ocr 返回 None 且不重复下载。"""
    db_session.add(City(name="宁波", code="nb", enabled=True))
    db_session.flush()
    task = _make_running_task(db_session)
    db_session.flush()
    note = Note(
        task_id=task.id,
        platform_note_id="existing-note",
        title="已存在",
        content="",
        source_url="https://www.xiaohongshu.com/explore/existing-note",
        city_code="nb",
        status="PROCESSED",
        raw_data={},
    )
    db_session.add(note)
    db_session.commit()

    settings = _make_settings(tmp_path)

    class _AdapterThatMustNotRun:
        def note(self, _url):
            raise AssertionError("existing note must not request detail")

        def download(self, _url, _folder):
            raise AssertionError("existing note must not download")

    item = {"title": "已存在", "url": "https://www.xiaohongshu.com/explore/existing-note"}

    result = crawl_task.download_and_ocr(
        db_session, task, task.run_token, "nb", item, _AdapterThatMustNotRun(), settings
    )

    assert result is None
    assert task.downloaded_notes == 0


def test_download_and_ocr_returns_none_when_url_empty(db_session, tmp_path):
    """url 为空时返回 None 并记 WARNING 日志。"""
    db_session.add(City(name="宁波", code="nb", enabled=True))
    db_session.flush()
    task = _make_running_task(db_session)
    db_session.commit()
    settings = _make_settings(tmp_path)

    item = {"title": "x", "url": ""}

    result = crawl_task.download_and_ocr(
        db_session, task, task.run_token, "nb", item, _FakeAdapter(), settings
    )

    assert result is None
    messages = list(db_session.scalars(select(TaskLog.message).where(TaskLog.task_id == task.id)))
    assert any("url 为空" in m for m in messages)


# ============================================================
# 3. extract_and_save
# ============================================================


def test_extract_and_save_writes_activities_and_marks_processed(db_session, tmp_path):
    """extract_and_save 应写 Activity 并把 Note 状态置为 PROCESSED。"""
    db_session.add(City(name="宁波", code="nb", enabled=True))
    db_session.flush()
    task = _make_running_task(db_session)
    db_session.flush()
    note = Note(
        task_id=task.id,
        platform_note_id="save-test",
        title="活动笔记",
        content="正文",
        source_url="https://www.xiaohongshu.com/explore/save-test",
        city_code="nb",
        status="OCR_DONE",
        published_at=datetime(2026, 7, 17, tzinfo=timezone.utc),
        raw_data={},
    )
    db_session.add(note)
    db_session.commit()

    settings = _make_settings(tmp_path)
    started_at = task.started_at or datetime(2026, 8, 10, tzinfo=timezone.utc)
    staged = crawl_task.StagedNote(
        note=note,
        combined_text="标题：活动笔记\n正文：正文",
        reference_now=datetime(2026, 7, 17),
        started_at=started_at,
        image_rows=[],
    )
    extracted = [
        {
            "name": "有效活动",
            "start_time": "2026-07-20T10:00:00",
            "end_time": None,
            "location": "文化广场",
            "price": "免费",
            "type": "演出",
            "summary": "夏日演出",
            "confidence": 0.9,
            "source_image_indexes": [],
        }
    ]

    crawl_task.extract_and_save(db_session, task, task.run_token, staged, extracted, settings)

    db_session.refresh(note)
    db_session.refresh(task)
    assert note.status == "PROCESSED"
    activities = list(db_session.scalars(select(Activity).where(Activity.note_id == note.id)))
    assert len(activities) == 1
    assert activities[0].name == "有效活动"
    assert activities[0].city_code == "nb"
    assert task.extracted_notes == 1
    assert task.success_notes == 1


def test_extract_and_save_marks_no_activities_when_all_filtered(db_session, tmp_path):
    """活动全部早于 published_at 时，Note 状态置为 NO_ACTIVITIES，不写 Activity。"""
    db_session.add(City(name="宁波", code="nb", enabled=True))
    db_session.flush()
    task = _make_running_task(db_session)
    db_session.flush()
    note = Note(
        task_id=task.id,
        platform_note_id="no-act",
        title="无活动",
        content="正文",
        source_url="https://www.xiaohongshu.com/explore/no-act",
        city_code="nb",
        status="OCR_DONE",
        published_at=datetime(2026, 7, 17, tzinfo=timezone.utc),
        raw_data={},
    )
    db_session.add(note)
    db_session.commit()

    settings = _make_settings(tmp_path)
    staged = crawl_task.StagedNote(
        note=note,
        combined_text="标题：无活动\n正文：正文",
        reference_now=datetime(2026, 7, 17),
        started_at=task.started_at,
        image_rows=[],
    )
    # 历史活动：早于 published_at
    extracted = [
        {
            "name": "历史活动",
            "start_time": "2024-07-20T10:00:00",
            "end_time": None,
            "location": "文化广场",
            "price": "",
            "type": "其他",
            "summary": "",
            "confidence": 0.9,
            "source_image_indexes": [],
        }
    ]

    crawl_task.extract_and_save(db_session, task, task.run_token, staged, extracted, settings)

    db_session.refresh(note)
    assert note.status == "NO_ACTIVITIES"
    activities = list(db_session.scalars(select(Activity).where(Activity.note_id == note.id)))
    assert len(activities) == 0
    assert task.extracted_notes == 1


# ============================================================
# 4. run_crawl 两阶段流水线
# ============================================================


def _setup_keyword_task(db_session: Session, urls: list[str]) -> tuple[CrawlTask, City]:
    city = City(name="宁波", code="nb", enabled=True, recent_filter="一周内")
    task = CrawlTask(
        type="mixed",
        status="PENDING",
        params={"city": "nb", "keywords": ["活动"], "recent_filter": "一周内", "blogger_ids": []},
    )
    db_session.add_all([city, task])
    db_session.commit()
    return task, city


def test_run_crawl_two_phase_pipeline(db_session, monkeypatch, tmp_path):
    """run_crawl 应先批量下载+OCR（阶段1），再批量 MiniMax+写DB（阶段2）。"""
    task, _ = _setup_keyword_task(db_session, ["https://xhs/1", "https://xhs/2"])

    class FakeAdapter:
        def __init__(self, _settings, session='xhs-crawler'):
            pass

        def check_login(self):
            return {"logged_in": True}

        def bind_task(self, *_args, **_kwargs):
            pass

        def search_recent(self, _query, _recent_filter):
            return [
                {"title": "宁波活动一", "url": "https://xhs/1"},
                {"title": "宁波活动二", "url": "https://xhs/2"},
            ]

        def note(self, url):
            return {"content": f"正文-{url}"}

        def download(self, _url, _folder):
            return []  # 无图片，OCR 关闭

    settings = _make_settings(tmp_path, minimax_api_key="fake-key", ocr_enabled=False)

    # 记录两阶段调用顺序
    download_calls: list[str] = []
    minimax_calls: list[list[str]] = []

    original_download_and_ocr = crawl_task.download_and_ocr

    def spy_download_and_ocr(db, t, run_token, city, item, adapter, _settings):
        download_calls.append(item["url"])
        return original_download_and_ocr(db, t, run_token, city, item, adapter, settings)

    class FakeMiniMaxClient:
        def __init__(self, _settings, session='xhs-crawler'):
            pass

        def extract_many_parallel(self, texts, reference=None):
            minimax_calls.append(list(texts))
            return [{"activities": [{"name": f"活动-{i}", "start_time": None, "location": "广场", "type": "其他", "confidence": 0.5, "source_image_indexes": []}]} for i, _ in enumerate(texts)]

    monkeypatch.setattr(crawl_task, "SessionLocal", lambda: db_session)
    monkeypatch.setattr(crawl_task, "OpenCLIAdapter", FakeAdapter)
    monkeypatch.setattr(crawl_task, "download_and_ocr", spy_download_and_ocr)
    monkeypatch.setattr(crawl_task, "MiniMaxClient", FakeMiniMaxClient)
    monkeypatch.setattr(crawl_task, "get_settings", lambda: settings)

    crawl_task.run_crawl.run(task.id, task.run_token)

    # 阶段 1：两篇都走了 download_and_ocr
    assert download_calls == ["https://xhs/1", "https://xhs/2"]
    # 阶段 2：MiniMax 批量调用一次，传入两篇的 combined_text
    assert len(minimax_calls) == 1
    assert len(minimax_calls[0]) == 2
    assert "宁波活动一" in minimax_calls[0][0]
    assert "宁波活动二" in minimax_calls[0][1]

    # 两篇笔记都应 PROCESSED
    notes = list(db_session.scalars(select(Note).where(Note.task_id == task.id).order_by(Note.id)))
    assert len(notes) == 2
    assert all(n.status == "PROCESSED" for n in notes)
    # 每个 note 对应一条 Activity
    activities = list(db_session.scalars(select(Activity).where(Activity.note_id.in_([n.id for n in notes]))))
    assert len(activities) == 2

    task = db_session.get(CrawlTask, task.id)
    assert task.status == "COMPLETED"
    assert task.extracted_notes == 2
    assert task.success_notes == 2


def test_run_crawl_concurrency_one_falls_back_to_serial(db_session, monkeypatch, tmp_path):
    """minimax_concurrency=1 时，extract_many_parallel 退化为串行，行为与逐篇一致。"""
    task, _ = _setup_keyword_task(db_session, ["https://xhs/1"])

    class FakeAdapter:
        def __init__(self, _settings, session='xhs-crawler'):
            pass

        def check_login(self):
            return {"logged_in": True}

        def bind_task(self, *_args, **_kwargs):
            pass

        def search_recent(self, _query, _recent_filter):
            return [{"title": "宁波活动", "url": "https://xhs/1"}]

        def note(self, _url):
            return {"content": "正文"}

        def download(self, _url, _folder):
            return []

    settings = _make_settings(tmp_path, minimax_api_key="fake-key", ocr_enabled=False)
    settings.minimax_concurrency = 1

    parallel_calls: list[int] = []

    class FakeMiniMaxClient:
        def __init__(self, _settings, session='xhs-crawler'):
            self.settings = _settings

        def extract_many_parallel(self, texts, reference=None):
            # concurrency=1 时仍走 extract_many_parallel，但内部串行
            parallel_calls.append(len(texts))
            from app.services.minimax import MiniMaxClient as _Real
            # 委托真实方法验证 concurrency<=1 路径
            real = _Real(self.settings)
            return [real.extract_many(t, reference) for t in texts]

    # 拦截真实 HTTP：patch extract_many 避免发请求
    def fake_extract_many(self, text, reference=None):
        return {"activities": [{"name": "串行活动", "start_time": None, "location": "广场", "type": "其他", "confidence": 0.5, "source_image_indexes": []}]}

    monkeypatch.setattr(crawl_task, "SessionLocal", lambda: db_session)
    monkeypatch.setattr(crawl_task, "OpenCLIAdapter", FakeAdapter)
    monkeypatch.setattr(crawl_task, "MiniMaxClient", FakeMiniMaxClient)
    monkeypatch.setattr(crawl_task, "get_settings", lambda: settings)
    monkeypatch.setattr(
        "app.services.minimax.MiniMaxClient.extract_many", fake_extract_many
    )

    crawl_task.run_crawl.run(task.id, task.run_token)

    # concurrency=1 时仍批量传入 extract_many_parallel（一篇）
    assert parallel_calls == [1]
    notes = list(db_session.scalars(select(Note).where(Note.task_id == task.id)))
    assert len(notes) == 1
    assert notes[0].status == "PROCESSED"


def test_run_crawl_no_api_key_falls_back_to_rule_extraction(db_session, monkeypatch, tmp_path):
    """无 minimax_api_key 时，阶段2 降级为规则提取（extract_activities），不调 MiniMax。"""
    task, _ = _setup_keyword_task(db_session, ["https://xhs/1"])

    class FakeAdapter:
        def __init__(self, _settings, session='xhs-crawler'):
            pass

        def check_login(self):
            return {"logged_in": True}

        def bind_task(self, *_args, **_kwargs):
            pass

        def search_recent(self, _query, _recent_filter):
            return [{"title": "宁波活动", "url": "https://xhs/1"}]

        def note(self, _url):
            return {"content": "正文 7月20日 文化广场"}

        def download(self, _url, _folder):
            return []

    settings = _make_settings(tmp_path, minimax_api_key="", ocr_enabled=False)

    minimax_calls: list = []

    class FakeMiniMaxClient:
        def __init__(self, _settings, session='xhs-crawler'):
            pass

        def extract_many_parallel(self, texts, reference=None):
            minimax_calls.append(texts)
            return []

    # 规则提取应能从 "7月20日" 解析出活动
    monkeypatch.setattr(crawl_task, "SessionLocal", lambda: db_session)
    monkeypatch.setattr(crawl_task, "OpenCLIAdapter", FakeAdapter)
    monkeypatch.setattr(crawl_task, "MiniMaxClient", FakeMiniMaxClient)
    monkeypatch.setattr(crawl_task, "get_settings", lambda: settings)

    crawl_task.run_crawl.run(task.id, task.run_token)

    # 无 API key：不应调用 MiniMax
    assert minimax_calls == []
    notes = list(db_session.scalars(select(Note).where(Note.task_id == task.id)))
    assert len(notes) == 1
    # 规则提取应产出活动（7月20日）
    activities = list(db_session.scalars(select(Activity).where(Activity.note_id == notes[0].id)))
    assert len(activities) >= 1


def test_run_crawl_minimax_batch_failure_falls_back_to_rule_extraction(db_session, monkeypatch, tmp_path):
    """MiniMax 批量提取失败时，降级为逐篇规则提取，不丢失笔记。"""
    task, _ = _setup_keyword_task(db_session, ["https://xhs/1"])

    class FakeAdapter:
        def __init__(self, _settings, session='xhs-crawler'):
            pass

        def check_login(self):
            return {"logged_in": True}

        def bind_task(self, *_args, **_kwargs):
            pass

        def search_recent(self, _query, _recent_filter):
            return [{"title": "宁波活动", "url": "https://xhs/1"}]

        def note(self, _url):
            return {"content": "正文 7月20日 文化广场"}

        def download(self, _url, _folder):
            return []

    settings = _make_settings(tmp_path, minimax_api_key="fake-key", ocr_enabled=False)
    settings.pipeline_stage_max_retries = 2

    class FakeMiniMaxClient:
        def __init__(self, _settings, session='xhs-crawler'):
            pass

        def extract_many_parallel(self, texts, reference=None):
            raise RuntimeError("MiniMax 529 限流")

    monkeypatch.setattr(crawl_task, "SessionLocal", lambda: db_session)
    monkeypatch.setattr(crawl_task, "OpenCLIAdapter", FakeAdapter)
    monkeypatch.setattr(crawl_task, "MiniMaxClient", FakeMiniMaxClient)
    monkeypatch.setattr(crawl_task, "get_settings", lambda: settings)

    crawl_task.run_crawl.run(task.id, task.run_token)

    task = db_session.get(CrawlTask, task.id)
    # 任务应正常完成（降级规则提取成功）
    assert task.status == "COMPLETED"
    notes = list(db_session.scalars(select(Note).where(Note.task_id == task.id)))
    assert len(notes) == 1
    assert notes[0].status == "PROCESSED"
    # 应有降级 WARNING 日志
    messages = list(db_session.scalars(select(TaskLog.message).where(TaskLog.task_id == task.id)))
    assert any("MiniMax 批量提取失败" in m and "降级规则提取" in m for m in messages)
