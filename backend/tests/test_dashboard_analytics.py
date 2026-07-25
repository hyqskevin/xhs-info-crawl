"""仪表盘 `/api/v1/dashboard/analytics` 接口测试。

关联 spec: docs/superpowers/specs/2026-07-25-scheduled-crawls-and-dashboard-charts-design.md

- recent_tasks：最近 20 次任务，按 id 倒取再正序；source 由 params 判定；
- status_counts：最近 50 次任务状态分布（饼图）；
- schedules：所有定时任务及其最近一次抓取（按 params.schedule_id 匹配）。
"""
from datetime import datetime, timezone

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import create_access_token
from app.models.config import City
from app.models.schedule import ScheduledCrawl
from app.models.task import CrawlTask


def _auth() -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token({'sub': 'admin', 'role': 'admin'})}"}


def _add_task(db: Session, **overrides) -> CrawlTask:
    task = CrawlTask(type="manual", status="COMPLETED", params={"city": "city-nb01"})
    for key, value in overrides.items():
        setattr(task, key, value)
    db.add(task)
    db.commit()
    db.refresh(task)
    return task


def _add_schedule(db: Session, **overrides) -> ScheduledCrawl:
    city = db.scalar(select(City).where(City.code == "city-nb01"))
    if city is None:
        city = City(name="宁波", code="city-nb01", enabled=True)
        db.add(city)
        db.commit()
    schedule = ScheduledCrawl(
        name="每周一上午",
        day_of_week=1,
        hour=9,
        minute=30,
        city_code=city.code,
        keyword_group_ids=[],
        blogger_group_ids=[],
        enabled=True,
    )
    for key, value in overrides.items():
        setattr(schedule, key, value)
    db.add(schedule)
    db.commit()
    db.refresh(schedule)
    return schedule


def test_analytics_empty(client: TestClient) -> None:
    resp = client.get("/api/v1/dashboard/analytics", headers=_auth())
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["recent_tasks"] == []
    assert data["status_counts"] == {}
    assert data["schedules"] == []


def test_analytics_requires_auth(client: TestClient) -> None:
    resp = client.get("/api/v1/dashboard/analytics")
    assert resp.status_code == 401


def test_analytics_recent_tasks_order_and_source(client: TestClient, db_session: Session) -> None:
    schedule = _add_schedule(db_session)
    t1 = _add_task(db_session, status="COMPLETED", total_notes=10, success_notes=9, failed_notes=1)
    t2 = _add_task(
        db_session,
        type="scheduled",
        status="FAILED",
        total_notes=5,
        failed_notes=5,
        params={
            "city": "city-nb01",
            "type": "scheduled",
            "schedule_id": schedule.id,
            "schedule_name": schedule.name,
        },
        started_at=datetime(2026, 7, 20, 9, 30, tzinfo=timezone.utc),
    )
    t3 = _add_task(db_session, status="STOPPED")

    resp = client.get("/api/v1/dashboard/analytics", headers=_auth())
    assert resp.status_code == 200
    recent = resp.json()["data"]["recent_tasks"]
    # 倒取正排：按 id 升序（时间正序），便于折线图直接渲染
    assert [row["id"] for row in recent] == [t1.id, t2.id, t3.id]
    assert recent[0]["source"] == "manual"
    assert recent[0]["schedule_name"] is None
    assert recent[1]["source"] == "scheduled"
    assert recent[1]["schedule_name"] == schedule.name
    assert recent[1]["total_notes"] == 5
    assert recent[1]["success_notes"] == 0
    assert recent[1]["failed_notes"] == 5
    assert recent[1]["started_at"] is not None


def test_analytics_recent_tasks_limit_20(client: TestClient, db_session: Session) -> None:
    tasks = [_add_task(db_session) for _ in range(25)]

    resp = client.get("/api/v1/dashboard/analytics", headers=_auth())
    recent = resp.json()["data"]["recent_tasks"]
    assert len(recent) == 20
    # 只保留最新 20 条，且按时间正序
    assert [row["id"] for row in recent] == [t.id for t in tasks[5:]]


def test_analytics_status_counts_recent_50(client: TestClient, db_session: Session) -> None:
    _add_task(db_session, status="COMPLETED")
    _add_task(db_session, status="COMPLETED")
    _add_task(db_session, status="COMPLETED_WITH_ERRORS")
    _add_task(db_session, status="FAILED")
    _add_task(db_session, status="STOPPED")
    _add_task(db_session, status="RUNNING")

    resp = client.get("/api/v1/dashboard/analytics", headers=_auth())
    counts = resp.json()["data"]["status_counts"]
    assert counts == {
        "COMPLETED": 2,
        "COMPLETED_WITH_ERRORS": 1,
        "FAILED": 1,
        "STOPPED": 1,
        "OTHER": 1,
    }


def test_analytics_schedule_last_task(client: TestClient, db_session: Session) -> None:
    schedule = _add_schedule(db_session)
    other = _add_schedule(db_session, name="每周三")
    # 手动任务不匹配任何 schedule
    _add_task(db_session, params={"city": "city-nb01"})
    first = _add_task(
        db_session,
        type="scheduled",
        status="COMPLETED",
        params={"city": "city-nb01", "schedule_id": schedule.id},
        started_at=datetime(2026, 7, 13, 9, 30, tzinfo=timezone.utc),
    )
    latest = _add_task(
        db_session,
        type="scheduled",
        status="FAILED",
        params={"city": "city-nb01", "schedule_id": schedule.id},
        started_at=datetime(2026, 7, 20, 9, 30, tzinfo=timezone.utc),
    )
    _add_task(
        db_session,
        type="scheduled",
        status="COMPLETED",
        params={"city": "city-nb01", "schedule_id": other.id},
        started_at=datetime(2026, 7, 22, 9, 30, tzinfo=timezone.utc),
    )

    resp = client.get("/api/v1/dashboard/analytics", headers=_auth())
    schedules = resp.json()["data"]["schedules"]
    assert len(schedules) == 2
    by_name = {row["name"]: row for row in schedules}
    assert by_name["每周一上午"]["last_task"]["id"] == latest.id
    assert by_name["每周一上午"]["last_task"]["status"] == "FAILED"
    assert by_name["每周一上午"]["last_task"]["id"] != first.id
    assert by_name["每周三"]["last_task"]["status"] == "COMPLETED"
    assert by_name["每周一上午"]["day_of_week"] == 1
    assert by_name["每周一上午"]["hour"] == 9
    assert by_name["每周一上午"]["minute"] == 30
    assert by_name["每周一上午"]["enabled"] is True


def test_analytics_schedule_without_tasks(client: TestClient, db_session: Session) -> None:
    _add_schedule(db_session)

    resp = client.get("/api/v1/dashboard/analytics", headers=_auth())
    schedules = resp.json()["data"]["schedules"]
    assert len(schedules) == 1
    assert schedules[0]["last_task"] is None
