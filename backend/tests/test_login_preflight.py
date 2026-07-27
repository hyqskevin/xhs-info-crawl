"""未登录识别 + 任务启动登录预检（spec: 2026-07-27-login-preflight-auth-pause-design.md）。

根因：未扫码登录时 opencli whoami 在浏览器层阻塞等扫码，Python 层 60s 超时
抛 OpenCLITimeout，被当作普通博主抓取失败记录。设计要求：
1. check_login 把 whoami 超时归类为 AuthenticationRequired（提示扫码登录）。
2. crawl_task 启动做真实登录预检，未登录直接 PAUSED，不进入发现阶段。
3. AuthenticationRequired 的 PAUSED 分支统一自动打开登录页。
"""
from types import SimpleNamespace

import pytest

from app.models.blogger_city import BloggerCity
from app.models.config import Blogger, City
from app.models.note import Note
from app.models.task import CrawlTask, TaskLog
from app.services.crawler import AuthenticationRequired, OpenCLITimeout
from app.services.opencli_adapter import OpenCLIAdapter
from app.tasks import crawl_task


def _settings():
    return SimpleNamespace(opencli_bin="opencli", xhs_login_url="https://www.xiaohongshu.com")


# ── 1/2. 适配器层：whoami 超时归类为未登录 ─────────────────────────────


def test_check_login_timeout_raises_authentication_required(monkeypatch):
    adapter = OpenCLIAdapter(_settings())

    def fake_run(args, **kwargs):
        assert args[:2] == ["xiaohongshu", "whoami"]
        raise OpenCLITimeout("opencli 命令执行超过 60s 被强制终止")

    monkeypatch.setattr(adapter, "run", fake_run)

    with pytest.raises(AuthenticationRequired) as exc_info:
        adapter.check_login()
    assert "登录" in str(exc_info.value)
    assert "扫码" in str(exc_info.value)


def test_check_login_success_passthrough(monkeypatch):
    adapter = OpenCLIAdapter(_settings())
    payload = {"username": "tester", "logged_in": True}
    monkeypatch.setattr(adapter, "run", lambda *a, **k: payload)

    assert adapter.check_login() == payload


# ── 3/4. 任务层：启动预检 ──────────────────────────────────────────────


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


def test_preflight_auth_failure_pauses_before_discovery(db_session, monkeypatch):
    blogger = _configured_blogger(db_session)
    task = _pending_task(db_session, blogger, "preflight-auth-token")
    opened = []
    discovery_calls = []

    class FakeAdapter:
        def __init__(self, _settings):
            pass

        def bind_task(self, *_args, **_kwargs):
            pass

        def check_login(self):
            raise AuthenticationRequired(
                "小红书登录检查超时：可能未登录或登录窗口正在等待扫码，请完成扫码登录后点击「继续抓取」"
            )

        def blogger_notes(self, username, _profile_url):
            discovery_calls.append(username)
            return []

    monkeypatch.setattr(crawl_task, "SessionLocal", lambda: db_session)
    monkeypatch.setattr(crawl_task, "OpenCLIAdapter", FakeAdapter)
    monkeypatch.setattr(crawl_task, "open_xhs_login", lambda settings: opened.append(settings.xhs_login_url))

    crawl_task.run_crawl.run(task.id, "preflight-auth-token")

    current = db_session.get(CrawlTask, task.id)
    assert current.status == "PAUSED"
    assert "登录" in (current.error_message or "")
    # 未进入发现阶段
    assert discovery_calls == []
    assert db_session.query(Note).filter(Note.task_id == task.id).count() == 0
    # 日志提示扫码；自动打开登录页
    messages = [row.message for row in db_session.query(TaskLog).filter(TaskLog.task_id == task.id)]
    assert any("扫码" in m for m in messages)
    assert len(opened) == 1
    assert "xiaohongshu.com" in opened[0]


def test_preflight_success_enters_discovery(db_session, monkeypatch):
    blogger = _configured_blogger(db_session)
    task = _pending_task(db_session, blogger, "preflight-ok-token")
    discovery_calls = []

    class FakeAdapter:
        def __init__(self, _settings):
            pass

        def bind_task(self, *_args, **_kwargs):
            pass

        def check_login(self):
            return {"logged_in": True}

        def blogger_notes(self, username, _profile_url):
            discovery_calls.append(username)
            return [{
                "title": "宁波活动",
                "url": "https://www.xiaohongshu.com/explore/signed-note?xsec_token=secret",
            }]

    def fake_process(db, current_task, _run_token, _city, item, _adapter, _settings):
        current_task.extracted_notes += 1
        current_task.success_notes += 1
        db.commit()
        return True

    monkeypatch.setattr(crawl_task, "SessionLocal", lambda: db_session)
    monkeypatch.setattr(crawl_task, "OpenCLIAdapter", FakeAdapter)
    monkeypatch.setattr(crawl_task, "process_note", fake_process)

    crawl_task.run_crawl.run(task.id, "preflight-ok-token")

    assert discovery_calls == ["宁波文旅"]
    current = db_session.get(CrawlTask, task.id)
    assert current.status in ("COMPLETED", "COMPLETED_WITH_ERRORS")
