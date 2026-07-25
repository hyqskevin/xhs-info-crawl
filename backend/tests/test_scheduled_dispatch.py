"""定时任务 dispatcher（scheduled_dispatch）测试。

关联 spec: docs/superpowers/specs/2026-07-25-scheduled-crawls-and-dashboard-charts-design.md

语义：
- 每分钟 tick，按 Asia/Shanghai 当前时间匹配 day_of_week/hour/minute；
- slot 幂等：同一 slot 不重复触发；
- 已有任务在跑（PENDING/RUNNING/STOP_REQUESTED）→ 跳过；
- 博主组展开为「组内 enabled 博主 ∩ 当前城市 enabled 博主」的 blogger_ids；
- 关键词组 id 直接入 params（resolve_effective_keywords 已支持）。
"""
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy.orm import Session

from app.tasks import crawl_task as crawl_task_module

from app.models.blogger_group import BloggerGroup, BloggerGroupMember
from app.models.config import Blogger, City
from app.models.blogger_city import BloggerCity
from app.models.keyword_group import KeywordGroup, KeywordGroupCity, KeywordGroupWord
from app.models.schedule import ScheduledCrawl
from app.models.task import CrawlTask
from app.tasks.crawl_task import scheduled_dispatch

_TZ = ZoneInfo("Asia/Shanghai")


@pytest.fixture(autouse=True)
def _use_test_session(monkeypatch: pytest.MonkeyPatch, db_session: Session) -> None:
    """dispatcher 自建 SessionLocal，测试里替换为测试库 session。"""
    monkeypatch.setattr(crawl_task_module, "SessionLocal", lambda: db_session)


def _seed(db: Session) -> tuple[City, KeywordGroup, BloggerGroup, Blogger]:
    city = City(name="宁波", code="city-nb01", enabled=True)
    kg = KeywordGroup(name="展览", enabled=True)
    bg = BloggerGroup(name="白名单组", enabled=True)
    blogger = Blogger(username="博主A", profile_url="https://xhs/u/a", enabled=True)
    outsider = Blogger(username="外地博主", profile_url="https://xhs/u/x", enabled=True)
    db.add_all([city, kg, bg, blogger, outsider])
    db.commit()
    for row in (kg, bg, blogger, outsider):
        db.refresh(row)
    db.add(KeywordGroupCity(keyword_group_id=kg.id, city_code=city.code, enabled=True))
    db.add(KeywordGroupWord(keyword_group_id=kg.id, word="展览", enabled=True))
    db.add(BloggerCity(blogger_id=blogger.id, city_code=city.code, enabled=True))
    # outsider 不属于该城市
    db.add(BloggerGroupMember(group_id=bg.id, blogger_id=blogger.id))
    db.add(BloggerGroupMember(group_id=bg.id, blogger_id=outsider.id))
    db.commit()
    return city, kg, bg, blogger


def _make_schedule(db: Session, city: City, kg: KeywordGroup, bg: BloggerGroup, **overrides) -> ScheduledCrawl:
    schedule = ScheduledCrawl(
        name="每周一",
        day_of_week=1,
        hour=9,
        minute=30,
        city_code=city.code,
        keyword_group_ids=[kg.id],
        blogger_group_ids=[bg.id],
        recent_filter="一周内",
        enabled=True,
    )
    for key, value in overrides.items():
        setattr(schedule, key, value)
    db.add(schedule)
    db.commit()
    db.refresh(schedule)
    return schedule


def test_dispatch_creates_task_at_matching_slot(db_session: Session, celery_dispatches: list[tuple]) -> None:
    city, kg, bg, blogger = _seed(db_session)
    schedule = _make_schedule(db_session, city, kg, bg)
    now = datetime(2026, 7, 27, 9, 30, tzinfo=_TZ)  # 2026-07-27 是周一

    scheduled_dispatch(now=now)

    tasks = db_session.query(CrawlTask).all()
    assert len(tasks) == 1
    task = tasks[0]
    assert task.status == "PENDING"
    assert task.type == "scheduled"
    assert task.params["schedule_id"] == schedule.id
    assert task.params["fired_slot"] == "2026-07-27T09:30"
    assert task.params["city"] == city.code
    assert task.params["keyword_group_ids"] == [kg.id]
    # 博主组展开：只有属于该城市的 blogger 入 params
    assert task.params["blogger_ids"] == [blogger.id]
    assert task.params["recent_filter"] == "一周内"
    assert celery_dispatches == [(task.id, task.run_token, {})]
    # dispatcher 结束会 close 共享 session，重新查询验证 slot 已落库
    assert db_session.get(ScheduledCrawl, schedule.id).last_fired_slot == "2026-07-27T09:30"


def test_dispatch_idempotent_same_slot(db_session: Session, celery_dispatches: list[tuple]) -> None:
    city, kg, bg, _ = _seed(db_session)
    _make_schedule(db_session, city, kg, bg)
    now = datetime(2026, 7, 27, 9, 30, tzinfo=_TZ)

    scheduled_dispatch(now=now)
    scheduled_dispatch(now=now)  # beat 重复 tick / 重启重发

    assert db_session.query(CrawlTask).count() == 1
    assert len(celery_dispatches) == 1


def test_dispatch_skips_when_not_due(db_session: Session, celery_dispatches: list[tuple]) -> None:
    city, kg, bg, _ = _seed(db_session)
    _make_schedule(db_session, city, kg, bg)
    wrong_time = datetime(2026, 7, 27, 10, 0, tzinfo=_TZ)
    wrong_day = datetime(2026, 7, 28, 9, 30, tzinfo=_TZ)  # 周二

    scheduled_dispatch(now=wrong_time)
    scheduled_dispatch(now=wrong_day)

    assert db_session.query(CrawlTask).count() == 0
    assert celery_dispatches == []


def test_dispatch_skips_when_task_in_progress(db_session: Session, celery_dispatches: list[tuple]) -> None:
    city, kg, bg, _ = _seed(db_session)
    _make_schedule(db_session, city, kg, bg)
    running = CrawlTask(type="manual", status="RUNNING", params={"city": city.code})
    db_session.add(running)
    db_session.commit()
    now = datetime(2026, 7, 27, 9, 30, tzinfo=_TZ)

    scheduled_dispatch(now=now)

    assert db_session.query(CrawlTask).filter(CrawlTask.type == "scheduled").count() == 0
    assert celery_dispatches == []


def test_dispatch_disabled_schedule_ignored(db_session: Session, celery_dispatches: list[tuple]) -> None:
    city, kg, bg, _ = _seed(db_session)
    _make_schedule(db_session, city, kg, bg, enabled=False)
    now = datetime(2026, 7, 27, 9, 30, tzinfo=_TZ)

    scheduled_dispatch(now=now)

    assert db_session.query(CrawlTask).count() == 0


def test_dispatch_falls_back_to_city_recent_filter(db_session: Session, celery_dispatches: list[tuple]) -> None:
    city, kg, bg, blogger = _seed(db_session)
    city.recent_filter = "一天内"
    db_session.commit()
    schedule = _make_schedule(db_session, city, kg, bg, recent_filter=None)
    now = datetime(2026, 7, 27, 9, 30, tzinfo=_TZ)

    scheduled_dispatch(now=now)

    task = db_session.query(CrawlTask).one()
    # params 不显式写 recent_filter，run_crawl 会回退到 city.recent_filter
    assert task.params.get("recent_filter") is None
    assert celery_dispatches == [(task.id, task.run_token, {})]
    assert db_session.get(ScheduledCrawl, schedule.id).last_fired_slot == "2026-07-27T09:30"
