"""点击开始抓取时自动停止上一个任务的测试"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.security import create_access_token
from app.models.config import City, Keyword
from app.models.task import CrawlTask, TaskLog


def _auth() -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token({'sub': 'admin', 'role': 'admin'})}"}


def test_crawl_auto_stops_previous_running_task(client: TestClient, db_session: Session, celery_dispatches: list[tuple]):
    db_session.add(City(name="上海", code="city-99f1e469", enabled=True))
    db_session.add(Keyword(word="活动", city_code="city-99f1e469", enabled=True))
    db_session.commit()

    previous = CrawlTask(
        type="mixed",
        status="RUNNING",
        params={"type": "mixed", "city": "city-99f1e469", "keywords": ["活动"], "blogger_ids": []},
    )
    db_session.add(previous)
    db_session.commit()
    previous_id = previous.id

    response = client.post(
        "/api/v1/tasks/crawl",
        json={"city": "city-99f1e469", "keywords": ["活动"], "blogger_ids": []},
        headers=_auth(),
    )

    assert response.status_code == 202, response.text
    data = response.json()["data"]
    assert data["status"] == "PENDING"
    assert celery_dispatches == [(data["id"], data["run_token"], {})]

    db_session.refresh(previous)
    assert previous.status == "STOP_REQUESTED"

    logs = db_session.query(TaskLog).filter(TaskLog.task_id == previous_id).all()
    assert any("被新任务顶替停止" in log.message for log in logs)


def test_crawl_auto_stops_previous_pending_task(client: TestClient, db_session: Session, celery_dispatches: list[tuple]):
    db_session.add(City(name="上海", code="city-99f1e469", enabled=True))
    db_session.add(Keyword(word="活动", city_code="city-99f1e469", enabled=True))
    db_session.commit()

    previous = CrawlTask(
        type="mixed",
        status="PENDING",
        params={"type": "mixed", "city": "city-99f1e469", "keywords": ["活动"], "blogger_ids": []},
    )
    db_session.add(previous)
    db_session.commit()
    previous_id = previous.id

    response = client.post(
        "/api/v1/tasks/crawl",
        json={"city": "city-99f1e469", "keywords": ["活动"], "blogger_ids": []},
        headers=_auth(),
    )

    assert response.status_code == 202, response.text
    data = response.json()["data"]
    assert celery_dispatches == [(data["id"], data["run_token"], {})]

    db_session.refresh(previous)
    assert previous.status == "STOPPED"

    logs = db_session.query(TaskLog).filter(TaskLog.task_id == previous_id).all()
    assert any("被新任务顶替停止" in log.message for log in logs)


def test_crawl_creates_new_task_after_stopping_previous(client: TestClient, db_session: Session, celery_dispatches: list[tuple]):
    db_session.add(City(name="上海", code="city-99f1e469", enabled=True))
    db_session.add(Keyword(word="活动", city_code="city-99f1e469", enabled=True))
    db_session.commit()

    previous = CrawlTask(
        type="mixed",
        status="RUNNING",
        params={"type": "mixed", "city": "city-99f1e469", "keywords": ["活动"], "blogger_ids": []},
    )
    db_session.add(previous)
    db_session.commit()
    previous_id = previous.id

    response = client.post(
        "/api/v1/tasks/crawl",
        json={"city": "city-99f1e469", "keywords": ["活动"], "blogger_ids": []},
        headers=_auth(),
    )

    assert response.status_code == 202, response.text
    data = response.json()["data"]
    new_task_id = data["id"]
    assert celery_dispatches == [(new_task_id, data["run_token"], {})]

    assert new_task_id != previous_id

    new_task = db_session.get(CrawlTask, new_task_id)
    assert new_task is not None
    assert new_task.status == "PENDING"


def test_crawl_returns_success_when_no_previous_task(client: TestClient, db_session: Session, celery_dispatches: list[tuple]):
    db_session.add(City(name="上海", code="city-99f1e469", enabled=True))
    db_session.add(Keyword(word="活动", city_code="city-99f1e469", enabled=True))
    db_session.commit()

    response = client.post(
        "/api/v1/tasks/crawl",
        json={"city": "city-99f1e469", "keywords": ["活动"], "blogger_ids": []},
        headers=_auth(),
    )

    assert response.status_code == 202, response.text
    data = response.json()["data"]
    assert data["status"] == "PENDING"
    assert celery_dispatches == [(data["id"], data["run_token"], {})]
