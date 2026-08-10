"""多小红书账号配置 + 抓取失效自动切换（spec: 2026-08-10-multi-xhs-account-design.md）。

测试覆盖：
- API 层：XhsAccount CRUD + check-login 端点（mock OpenCLIAdapter）
- 任务层：run_crawl 启动选账号、笔记级切换、全部失效 PAUSED、无账号回退默认 session
"""
from types import SimpleNamespace

import pytest

from app.core.security import create_access_token
from app.models.blogger_city import BloggerCity
from app.models.config import Blogger, City
from app.models.task import CrawlTask, TaskLog
from app.models.xhs_account import XhsAccount
from app.services.crawler import AuthenticationRequired, VerificationRequired
from app.tasks import crawl_task


# ── 公共辅助 ───────────────────────────────────────────────────────────────


def _auth() -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token({'sub': 'admin', 'role': 'admin'})}"}


def _configured_blogger(db_session, note_count=1):
    """创建一个城市 + 博主，blogger_notes 返回 note_count 篇笔记。"""
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


def _make_fake_adapter_class(note_count=1):
    """构造 FakeAdapter，记录所有实例及其 session 名，便于断言切换行为。"""
    instances: list = []

    class FakeAdapter:
        def __init__(self, settings, session="xhs-crawler"):
            self.settings = settings
            self.session = session
            instances.append(self)

        def bind_task(self, *_args, **_kwargs):
            pass

        def check_login(self):
            return {"logged_in": True}

        def blogger_notes(self, _username, _profile_url):
            return [
                {"title": f"活动{i}", "url": f"https://www.xiaohongshu.com/explore/note{i}?xsec_token=t"}
                for i in range(note_count)
            ]

    return FakeAdapter, instances


def _run_crawl_with_fake_adapter(db_session, monkeypatch, task, fake_adapter_class, download_and_ocr_fn, opened=None):
    """统一封装 run_crawl 的 monkeypatch：SessionLocal / OpenCLIAdapter / download_and_ocr / open_xhs_login。"""
    monkeypatch.setattr(crawl_task, "SessionLocal", lambda: db_session)
    monkeypatch.setattr(crawl_task, "OpenCLIAdapter", fake_adapter_class)
    monkeypatch.setattr(crawl_task, "download_and_ocr", download_and_ocr_fn)
    if opened is not None:
        monkeypatch.setattr(crawl_task, "open_xhs_login", lambda settings: opened.append(settings.xhs_login_url))
    crawl_task.run_crawl.run(task.id, task.run_token)


# ── 1. API CRUD ────────────────────────────────────────────────────────────


def test_create_xhs_account(client, db_session):
    resp = client.post(
        "/api/v1/xhs-accounts",
        json={
            "name": "主账号",
            "remark": "主力",
            "session_name": "xhs-main",
            "enabled": True,
            "priority": 0,
        },
        headers=_auth(),
    )
    assert resp.status_code == 201, resp.text
    data = resp.json()["data"]
    assert data["name"] == "主账号"
    assert data["session_name"] == "xhs-main"
    assert data["enabled"] is True
    assert data["priority"] == 0
    assert data["login_status"] == "unknown"
    # 落库
    row = db_session.query(XhsAccount).filter_by(session_name="xhs-main").one()
    assert row.name == "主账号"


def test_list_xhs_accounts_sorted_by_priority(client, db_session):
    db_session.add(XhsAccount(name="B", session_name="xhs-b", priority=10, enabled=True))
    db_session.add(XhsAccount(name="A", session_name="xhs-a", priority=1, enabled=True))
    db_session.add(XhsAccount(name="C", session_name="xhs-c", priority=5, enabled=True))
    db_session.commit()

    resp = client.get("/api/v1/xhs-accounts", headers=_auth())
    assert resp.status_code == 200
    # data 直接是数组（与 /settings/{kind} 口径一致）
    items = resp.json()["data"]
    # 按 priority 升序：A(1) < C(5) < B(10)
    assert [item["session_name"] for item in items] == ["xhs-a", "xhs-c", "xhs-b"]


def test_update_xhs_account(client, db_session):
    account = XhsAccount(name="旧名", session_name="xhs-old", priority=0, enabled=True)
    db_session.add(account)
    db_session.commit()

    resp = client.put(
        f"/api/v1/xhs-accounts/{account.id}",
        json={"name": "新名", "remark": "更新备注", "enabled": False, "priority": 99},
        headers=_auth(),
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["name"] == "新名"
    assert data["remark"] == "更新备注"
    assert data["enabled"] is False
    assert data["priority"] == 99


def test_delete_xhs_account(client, db_session):
    account = XhsAccount(name="待删", session_name="xhs-del", priority=0, enabled=True)
    db_session.add(account)
    db_session.commit()
    aid = account.id

    resp = client.delete(f"/api/v1/xhs-accounts/{aid}", headers=_auth())
    assert resp.status_code == 200
    assert db_session.query(XhsAccount).filter_by(id=aid).count() == 0


# ── 2. check-login 端点 ────────────────────────────────────────────────────


def test_check_login_returns_logged_in(client, db_session, monkeypatch):
    account = XhsAccount(name="主账号", session_name="xhs-main", priority=0, enabled=True)
    db_session.add(account)
    db_session.commit()

    captured = {}

    class FakeAdapter:
        def __init__(self, settings, session="xhs-crawler"):
            captured["session"] = session

        def check_login(self):
            return {"username": "tester", "logged_in": True}

    monkeypatch.setattr("app.api.v1.xhs_accounts.OpenCLIAdapter", FakeAdapter)

    resp = client.post(f"/api/v1/xhs-accounts/{account.id}/check-login", headers=_auth())
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["logged_in"] is True
    # 用对应 session 调 adapter
    assert captured["session"] == "xhs-main"
    # 落库 login_status 更新为 logged_in
    db_session.refresh(account)
    assert account.login_status == "logged_in"


def test_check_login_returns_logged_out(client, db_session, monkeypatch):
    account = XhsAccount(name="主账号", session_name="xhs-main", priority=0, enabled=True)
    db_session.add(account)
    db_session.commit()

    class FakeAdapter:
        def __init__(self, settings, session="xhs-crawler"):
            pass

        def check_login(self):
            raise AuthenticationRequired("未登录或扫码超时")

    monkeypatch.setattr("app.api.v1.xhs_accounts.OpenCLIAdapter", FakeAdapter)

    resp = client.post(f"/api/v1/xhs-accounts/{account.id}/check-login", headers=_auth())
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["logged_in"] is False
    assert "未登录" in data["error"]
    # 落库 login_status 更新为 logged_out
    db_session.refresh(account)
    assert account.login_status == "logged_out"


# ── 3. run_crawl 多账号切换 ────────────────────────────────────────────────


def test_run_crawl_uses_first_account_by_priority(db_session, monkeypatch):
    """启动时用 priority 最小的账号 session 初始化 adapter。"""
    blogger = _configured_blogger(db_session)
    task = _pending_task(db_session, blogger, "prio-token")
    db_session.add(XhsAccount(name="低优", session_name="xhs-low", priority=10, enabled=True))
    db_session.add(XhsAccount(name="高优", session_name="xhs-high", priority=1, enabled=True))
    db_session.commit()

    FakeAdapter, instances = _make_fake_adapter_class(note_count=1)

    def fake_download_and_ocr(db, current_task, _run_token, _city, item, adapter, _settings):
        current_task.extracted_notes += 1
        current_task.success_notes += 1
        db.commit()
        return None

    _run_crawl_with_fake_adapter(db_session, monkeypatch, task, FakeAdapter, fake_download_and_ocr)

    # 第一个被实例化的 adapter 必须用 priority=1 的 session
    assert instances[0].session == "xhs-high"
    current = db_session.get(CrawlTask, task.id)
    assert current.status in ("COMPLETED", "COMPLETED_WITH_ERRORS")


def test_run_crawl_switches_account_on_auth_required(db_session, monkeypatch):
    """第一篇笔记 AuthenticationRequired 时切换到第二个账号，重试成功。"""
    blogger = _configured_blogger(db_session, note_count=1)
    task = _pending_task(db_session, blogger, "switch-token")
    db_session.add(XhsAccount(name="主账号", session_name="xhs-main", priority=0, enabled=True))
    db_session.add(XhsAccount(name="备账号", session_name="xhs-backup", priority=10, enabled=True))
    db_session.commit()

    FakeAdapter, instances = _make_fake_adapter_class(note_count=1)

    def fake_download_and_ocr(db, current_task, _run_token, _city, item, adapter, _settings):
        if adapter.session == "xhs-main":
            raise AuthenticationRequired("主账号未登录")
        # 备账号成功
        current_task.extracted_notes += 1
        current_task.success_notes += 1
        db.commit()
        return None

    _run_crawl_with_fake_adapter(db_session, monkeypatch, task, FakeAdapter, fake_download_and_ocr)

    # 第一个 adapter 是主账号，切换后第二个 adapter 是备账号
    assert instances[0].session == "xhs-main"
    assert len(instances) >= 2
    assert instances[1].session == "xhs-backup"
    # 任务正常完成
    current = db_session.get(CrawlTask, task.id)
    assert current.status in ("COMPLETED", "COMPLETED_WITH_ERRORS")
    # 切换日志
    messages = [row.message for row in db_session.query(TaskLog).filter(TaskLog.task_id == task.id)]
    assert any("主账号" in m and "备账号" in m and "切换" in m for m in messages)


def test_run_crawl_all_accounts_failed_enters_paused(db_session, monkeypatch):
    """所有账号都失效时进入 PAUSED。"""
    blogger = _configured_blogger(db_session, note_count=2)
    task = _pending_task(db_session, blogger, "all-failed-token")
    db_session.add(XhsAccount(name="主账号", session_name="xhs-main", priority=0, enabled=True))
    db_session.add(XhsAccount(name="备账号", session_name="xhs-backup", priority=10, enabled=True))
    db_session.commit()

    FakeAdapter, _instances = _make_fake_adapter_class(note_count=2)
    opened = []

    def fake_download_and_ocr(db, current_task, _run_token, _city, item, adapter, _settings):
        # 任何账号都失效
        raise AuthenticationRequired(f"未登录 session={adapter.session}")

    _run_crawl_with_fake_adapter(db_session, monkeypatch, task, FakeAdapter, fake_download_and_ocr, opened=opened)

    current = db_session.get(CrawlTask, task.id)
    assert current.status == "PAUSED"
    assert "所有账号均已失效" in (current.error_message or "")
    # 自动打开登录页
    assert len(opened) == 1


def test_run_crawl_no_accounts_falls_back_to_default_session(db_session, monkeypatch):
    """无账号配置时用默认 session 'xhs-crawler'。"""
    blogger = _configured_blogger(db_session, note_count=1)
    task = _pending_task(db_session, blogger, "default-token")
    # 不创建任何 XhsAccount

    FakeAdapter, instances = _make_fake_adapter_class(note_count=1)

    def fake_download_and_ocr(db, current_task, _run_token, _city, item, adapter, _settings):
        assert adapter.session == "xhs-crawler"
        current_task.extracted_notes += 1
        current_task.success_notes += 1
        db.commit()
        return None

    _run_crawl_with_fake_adapter(db_session, monkeypatch, task, FakeAdapter, fake_download_and_ocr)

    assert instances[0].session == "xhs-crawler"
    current = db_session.get(CrawlTask, task.id)
    assert current.status in ("COMPLETED", "COMPLETED_WITH_ERRORS")


def test_run_crawl_default_session_auth_required_pauses(db_session, monkeypatch):
    """无账号配置 + 默认 session 失效 → 直接 PAUSED（无切换机会）。"""
    blogger = _configured_blogger(db_session, note_count=1)
    task = _pending_task(db_session, blogger, "default-auth-token")

    FakeAdapter, _instances = _make_fake_adapter_class(note_count=1)
    opened = []

    def fake_download_and_ocr(db, current_task, _run_token, _city, item, adapter, _settings):
        raise AuthenticationRequired("默认 session 未登录")

    _run_crawl_with_fake_adapter(db_session, monkeypatch, task, FakeAdapter, fake_download_and_ocr, opened=opened)

    current = db_session.get(CrawlTask, task.id)
    assert current.status == "PAUSED"
    assert "所有账号均已失效" in (current.error_message or "")
    assert len(opened) == 1
