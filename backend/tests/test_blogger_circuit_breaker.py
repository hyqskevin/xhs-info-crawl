"""博主层连续失败熔断（spec: 2026-07-30-blogger-circuit-breaker-design.md）。

根因：博主抓取出现 stale page identity / OpenCLIError 时只 `continue`，
不计入 consecutive_failures，导致系统性问题下整批跑空。
设计：博主抓取异常（非认证/停止）也计入熔断阈值；成功也清零计数。
"""
import pytest

from app.core.config import get_settings
from app.models.blogger_city import BloggerCity
from app.models.config import Blogger, City
from app.models.task import CrawlTask
from app.services.crawler import AuthenticationRequired
from app.tasks import crawl_task


def _configured_bloggers(db_session, n: int) -> list[Blogger]:
    city = City(name="宁波", code="nb", enabled=True, recent_filter="一周内")
    db_session.add(city)
    db_session.flush()
    bloggers = []
    for i in range(n):
        blogger = Blogger(
            platform_user_id=f"user-{i}",
            username=f"博主{i}",
            profile_url=f"https://www.xiaohongshu.com/user/profile/user-{i}",
            enabled=True,
        )
        db_session.add(blogger)
        db_session.flush()
        db_session.add(BloggerCity(blogger_id=blogger.id, city_code="nb", enabled=True))
        bloggers.append(blogger)
    db_session.commit()
    return bloggers


def _pending_task(db_session, token: str, blogger_ids: list[int]) -> CrawlTask:
    task = CrawlTask(
        type="mixed",
        status="PENDING",
        run_token=token,
        params={
            "city": "nb",
            "keywords": [],
            "recent_filter": "一周内",
            "blogger_ids": blogger_ids,
        },
    )
    db_session.add(task)
    db_session.commit()
    return task


def _adapter_with_blogger_results(results_by_username: dict):
    """results_by_username[username] = list[dict] OR Exception instance."""

    class FakeAdapter:
        def __init__(self, _settings, session='xhs-crawler'):
            pass

        def bind_task(self, *_args, **_kwargs):
            pass

        def check_login(self):
            return {"logged_in": True}

        def blogger_notes(self, username, _profile_url):
            value = results_by_username.get(username)
            if isinstance(value, Exception):
                raise value
            return value or []

    return FakeAdapter


def _run(db_session, monkeypatch, task, adapter_factory):
    monkeypatch.setattr(crawl_task, "SessionLocal", lambda: db_session)
    monkeypatch.setattr(crawl_task, "OpenCLIAdapter", adapter_factory)
    # 拦截 download_and_ocr 避免真实下载；返回 None 模拟处理完成（不进阶段2）
    monkeypatch.setattr(crawl_task, "download_and_ocr", lambda *args, **kwargs: None)
    monkeypatch.setattr(crawl_task, "open_xhs_login", lambda *_args, **_kwargs: None)

    crawl_task.run_crawl.run(task.id, task.run_token)


def test_blogger_consecutive_failures_halt_to_paused(db_session, monkeypatch):
    bloggers = _configured_bloggers(db_session, n=4)
    task = _pending_task(db_session, token="halt-blogger-1", blogger_ids=[b.id for b in bloggers])

    # 4 个博主连续抛 stale page identity → 应熔断
    results = {b.username: RuntimeError("Page not found: ABC — stale page identity") for b in bloggers}
    _run(db_session, monkeypatch, task, _adapter_with_blogger_results(results))

    current = db_session.get(CrawlTask, task.id)
    assert current.status == "PAUSED"
    assert "已连续" in (current.error_message or "")
    assert "CDP session" in (current.error_message or "")
    assert "博主" in (current.error_message or "")


def test_blogger_success_resets_failure_counter(db_session, monkeypatch):
    bloggers = _configured_bloggers(db_session, n=5)
    task = _pending_task(db_session, token="halt-blogger-2", blogger_ids=[b.id for b in bloggers])

    # 失败 2 → 成功 → 失败 2：任何时刻连续失败都不到 3，不熔断
    results = {
        bloggers[0].username: RuntimeError("stale"),
        bloggers[1].username: RuntimeError("stale"),
        bloggers[2].username: [{"title": "ok", "url": "https://xhs.example/n/2?xsec_token=t"}],
        bloggers[3].username: RuntimeError("stale"),
        bloggers[4].username: RuntimeError("stale"),
    }
    _run(db_session, monkeypatch, task, _adapter_with_blogger_results(results))

    current = db_session.get(CrawlTask, task.id)
    # 不应熔断；最后进入完成态（哪怕有 failed_notes）
    assert current.status in ("COMPLETED", "COMPLETED_WITH_ERRORS")
    assert "已连续" not in (current.error_message or "")


def test_authentication_required_does_not_count_as_failure(db_session, monkeypatch):
    bloggers = _configured_bloggers(db_session, n=3)
    task = _pending_task(db_session, token="halt-blogger-3", blogger_ids=[b.id for b in bloggers])

    results = {b.username: AuthenticationRequired("请在 Chrome 登录小红书") for b in bloggers}
    _run(db_session, monkeypatch, task, _adapter_with_blogger_results(results))

    current = db_session.get(CrawlTask, task.id)
    # AuthenticationRequired 不应计入熔断 → 走 AuthenticationRequired 异常分支 → PAUSED
    assert current.status == "PAUSED"
    assert "请在 Chrome 登录小红书" in (current.error_message or "")


def test_blogger_halt_threshold_uses_settings(db_session, monkeypatch):
    bloggers = _configured_bloggers(db_session, n=2)
    task = _pending_task(db_session, token="halt-blogger-4", blogger_ids=[b.id for b in bloggers])
    monkeypatch.setattr(get_settings(), "consecutive_note_failure_limit", 2)

    results = {b.username: RuntimeError("stale page identity") for b in bloggers}
    _run(db_session, monkeypatch, task, _adapter_with_blogger_results(results))

    current = db_session.get(CrawlTask, task.id)
    assert current.status == "PAUSED"
    assert "已连续 2" in (current.error_message or "")