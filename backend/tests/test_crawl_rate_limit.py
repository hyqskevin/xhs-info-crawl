"""run_crawl 搜索频率与周配额集成测试。

关联 spec: docs/superpowers/specs/2026-07-25-crawl-rate-limit-design.md

- 关键词搜索之间 sleep（首次不等），sleep 可注入；
- 周配额超限：WARNING + 跳过剩余搜索，任务不失败；
- 配额跨任务累计；conftest autouse 已把 rate_limit_sleep 置为 no-op，
  需要断言 sleep 的用例显式重 patch。
"""
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.config import City
from app.models.search_usage import SearchUsage
from app.models.task import CrawlTask, TaskLog
from app.services.search_rate_limit import iso_week_key
from app.tasks import crawl_task as crawl_task_module
from app.tasks.crawl_task import run_crawl


def _seed_city(db: Session) -> None:
    if db.scalar(select(City).where(City.code == "nb")) is None:
        db.add(City(name="宁波", code="nb", enabled=True, recent_filter="一周内"))
        db.commit()


def _seed_task(db: Session, keywords: list[str], token: str) -> CrawlTask:
    _seed_city(db)
    task = CrawlTask(
        type="keyword",
        status="PENDING",
        run_token=token,
        params={"city": "nb", "keywords": keywords, "recent_filter": "一周内", "blogger_ids": []},
    )
    db.add(task)
    db.commit()
    db.refresh(task)
    return task


def _install_fakes(db_session: Session, monkeypatch, queries: list[str]) -> None:
    class FakeAdapter:
        def __init__(self, _settings):
            pass

        def check_login(self):
            return {"logged_in": True}

        def search_recent(self, query, _recent_filter):
            queries.append(query)
            return []

    monkeypatch.setattr(crawl_task_module, "SessionLocal", lambda: db_session)
    monkeypatch.setattr(crawl_task_module, "OpenCLIAdapter", FakeAdapter)


def _usage_count(db: Session) -> int:
    usage = db.scalar(select(SearchUsage).where(SearchUsage.week_key == iso_week_key()))
    return usage.count if usage else 0


def test_sleeps_between_keyword_searches_but_not_before_first(db_session: Session, monkeypatch) -> None:
    task = _seed_task(db_session, ["活动", "展览", "亲子"], "rate-token")
    queries: list[str] = []
    _install_fakes(db_session, monkeypatch, queries)
    sleeps: list[float] = []
    monkeypatch.setattr(crawl_task_module, "rate_limit_sleep", lambda seconds, guard=None: sleeps.append(seconds))
    monkeypatch.setattr("app.services.search_rate_limit.random.uniform", lambda low, high: 12.0)

    run_crawl.run(task.id, "rate-token")

    assert queries == ["宁波 活动", "宁波 展览", "宁波 亲子"]
    # 3 次搜索之间 sleep 2 次（首次不等）
    assert sleeps == [12.0, 12.0]
    # 每次成功搜索配额 +1
    assert _usage_count(db_session) == 3
    assert db_session.get(CrawlTask, task.id).status == "COMPLETED"


def test_skips_search_when_weekly_limit_reached(db_session: Session, monkeypatch) -> None:
    db_session.add(SearchUsage(week_key=iso_week_key(), count=500))
    db_session.commit()
    task = _seed_task(db_session, ["活动", "展览"], "quota-token")
    queries: list[str] = []
    _install_fakes(db_session, monkeypatch, queries)

    run_crawl.run(task.id, "quota-token")

    assert queries == []  # 超限后不再调用搜索
    current = db_session.get(CrawlTask, task.id)
    assert current.status == "COMPLETED"  # 超限不算失败
    messages = list(db_session.scalars(select(TaskLog.message).where(TaskLog.task_id == task.id)))
    assert any("上限" in message for message in messages)


def test_weekly_quota_accumulates_across_tasks(db_session: Session, monkeypatch) -> None:
    first = _seed_task(db_session, ["活动", "展览"], "first-token")
    queries: list[str] = []
    _install_fakes(db_session, monkeypatch, queries)
    sleeps: list[float] = []
    monkeypatch.setattr(crawl_task_module, "rate_limit_sleep", lambda seconds, guard=None: sleeps.append(seconds))

    run_crawl.run(first.id, "first-token")

    second = _seed_task(db_session, ["亲子"], "second-token")
    run_crawl.run(second.id, "second-token")

    assert queries == ["宁波 活动", "宁波 展览", "宁波 亲子"]
    # 每个任务内第一次搜索都不等：任务1 两次搜索 sleep 1 次；任务2 一次搜索不 sleep
    assert len(sleeps) == 1
    assert _usage_count(db_session) == 3
