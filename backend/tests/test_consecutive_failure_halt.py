"""笔记连续失败熔断（spec: 2026-07-28-log-timezone-and-consecutive-failure-halt-design.md）。

根因：on_failure 对每篇失败仅 failed_notes+1 并继续，系统性问题（登录态掉线
未被 whoami 识别、风控、opencli 异常）导致整批笔记逐篇失败，用户无决策入口。
设计要求：连续失败达到阈值（默认 3，可配）→ 抛 CrawlHalted → 任务 PAUSED，
error_message 指引用户「检测登录并继续」或「结束抓取」，并自动打开登录页。
"""
import pytest

from app.core.config import get_settings
from app.core.security import create_access_token
from app.models.blogger_city import BloggerCity
from app.models.config import Blogger, City
from app.models.task import CrawlTask, TaskLog
from app.tasks import crawl_task


def _configured_blogger(db_session):
    city = City(name="宁波", code="nb", enabled=True, recent_filter="一周内")
    db_session.add(city)
    db_session.flush()
    blogger = Blogger(
        platform_user_id="user-1",
        username="宁波文旅",
        profile_url="https://www.xiaohongshu.com/user/profile/user-1",
        city_code="nb",
        enabled=True,
    )
    db_session.add(blogger)
    db_session.flush()
    db_session.add(BloggerCity(blogger_id=blogger.id, city_code="nb", enabled=True))
    db_session.commit()
    return blogger


def _pending_task(db_session, blogger, token):
    task = CrawlTask(
        type="mixed",
        status="PENDING",
        run_token=token,
        params={
            "city": "nb",
            "keywords": [],
            "recent_filter": "一周内",
            "blogger_ids": [blogger.id],
        },
    )
    db_session.add(task)
    db_session.commit()
    return task


def _fake_adapter_class(note_count):
    class FakeAdapter:
        def __init__(self, _settings):
            pass

        def bind_task(self, *_args, **_kwargs):
            pass

        def check_login(self):
            return {"logged_in": True}

        def blogger_notes(self, _username, _profile_url):
            return [
                {"title": f"活动{i}", "url": f"https://www.xiaohongshu.com/explore/note{i}?xsec_token=t"}
                for i in range(note_count)
            ]

    return FakeAdapter


def _run(db_session, monkeypatch, task, note_count, process_behaviors, opened=None):
    """process_behaviors: list[bool]，True=处理成功，False=抛异常。"""
    calls = []

    def fake_process(db, current_task, _run_token, _city, item, _adapter, _settings):
        index = len(calls)
        calls.append(item["url"])
        if process_behaviors[index]:
            current_task.extracted_notes += 1
            current_task.success_notes += 1
            db.commit()
            return True
        raise RuntimeError(f"opencli note 失败 #{index}")

    monkeypatch.setattr(crawl_task, "SessionLocal", lambda: db_session)
    monkeypatch.setattr(crawl_task, "OpenCLIAdapter", _fake_adapter_class(note_count))
    monkeypatch.setattr(crawl_task, "process_note", fake_process)
    if opened is not None:
        monkeypatch.setattr(crawl_task, "open_xhs_login", lambda settings: opened.append(settings.xhs_login_url))

    crawl_task.run_crawl.run(task.id, task.run_token)
    return calls


def test_consecutive_failures_halt_to_paused(db_session, monkeypatch):
    blogger = _configured_blogger(db_session)
    task = _pending_task(db_session, blogger, "halt-token-1")
    opened = []

    calls = _run(db_session, monkeypatch, task, note_count=5, process_behaviors=[False] * 5, opened=opened)

    current = db_session.get(CrawlTask, task.id)
    assert current.status == "PAUSED"
    assert "已连续 3 篇" in (current.error_message or "")
    assert "检测登录并继续" in (current.error_message or "")
    # 第 3 篇失败后熔断，第 4/5 篇不再处理
    assert len(calls) == 3
    assert current.failed_notes == 3
    messages = [row.message for row in db_session.query(TaskLog).filter(TaskLog.task_id == task.id)]
    assert any("已连续 3 篇" in m for m in messages)
    # 复用未登录 PAUSED 的自动打开登录页逻辑
    assert len(opened) == 1


def test_success_resets_consecutive_counter(db_session, monkeypatch):
    blogger = _configured_blogger(db_session)
    task = _pending_task(db_session, blogger, "halt-token-2")

    # 失败2 → 成功 → 失败2：任何时刻连续失败都不到 3，不熔断
    calls = _run(
        db_session, monkeypatch, task,
        note_count=5,
        process_behaviors=[False, False, True, False, False],
    )

    current = db_session.get(CrawlTask, task.id)
    assert len(calls) == 5
    assert current.status == "COMPLETED_WITH_ERRORS"
    assert current.failed_notes == 4


def test_halt_threshold_is_configurable(db_session, monkeypatch):
    blogger = _configured_blogger(db_session)
    task = _pending_task(db_session, blogger, "halt-token-3")
    monkeypatch.setattr(get_settings(), "consecutive_note_failure_limit", 2)

    calls = _run(db_session, monkeypatch, task, note_count=4, process_behaviors=[False] * 4)

    current = db_session.get(CrawlTask, task.id)
    assert current.status == "PAUSED"
    assert "已连续 2 篇" in (current.error_message or "")
    assert len(calls) == 2


def test_halted_task_can_be_stopped(db_session, monkeypatch, client):
    blogger = _configured_blogger(db_session)
    task = _pending_task(db_session, blogger, "halt-token-4")

    _run(db_session, monkeypatch, task, note_count=5, process_behaviors=[False] * 5)
    assert db_session.get(CrawlTask, task.id).status == "PAUSED"

    response = client.post(
        f"/api/v1/tasks/{task.id}/stop",
        headers={"Authorization": f"Bearer {create_access_token({'sub': 'admin', 'role': 'admin'})}"},
    )
    assert response.status_code in (200, 202)
    assert db_session.get(CrawlTask, task.id).status == "STOPPED"
