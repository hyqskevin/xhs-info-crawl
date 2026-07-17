from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.security import create_access_token
from app.models.activity import Activity


@pytest.fixture
def headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token({'sub': 'admin', 'role': 'admin'})}"}


def make_activity(index: int, city: str = "shanghai", kind: str = "演出", status: str = "APPROVED") -> Activity:
    return Activity(name=f"活动{index}", city_code=city, start_time=datetime(2025, 7, 20, 18, tzinfo=timezone.utc), end_time=datetime(2025, 7, 20, 22, tzinfo=timezone.utc), location="徐汇滨江", price="免费", type=kind, source_url=f"https://example.com/{index}", summary="活动简介", status=status, confidence=0.85)


def test_get_activities_default_pagination(client: TestClient, db_session: Session, headers: dict[str, str]) -> None:
    db_session.add_all([make_activity(i) for i in range(25)])
    db_session.commit()
    response = client.get("/api/v1/activities", headers=headers)
    assert response.status_code == 200
    assert len(response.json()["data"]["items"]) == 20
    assert response.json()["pagination"] == {"page": 1, "page_size": 20, "total": 25}


def test_get_activities_filters_by_city_and_multiple_fields(client: TestClient, db_session: Session, headers: dict[str, str]) -> None:
    db_session.add_all([make_activity(1), make_activity(2, "beijing"), make_activity(3, kind="展览")])
    db_session.commit()
    assert client.get("/api/v1/activities?city=shanghai", headers=headers).json()["pagination"]["total"] == 2
    response = client.get("/api/v1/activities?city=shanghai&type=演出&status=APPROVED", headers=headers)
    assert response.json()["pagination"]["total"] == 1


def test_get_activities_date_range_and_invalid_date(client: TestClient, db_session: Session, headers: dict[str, str]) -> None:
    db_session.add_all([
        make_activity(1),
        Activity(name="次日活动", city_code="shanghai", start_time=datetime(2025, 7, 21, 10, tzinfo=timezone.utc), location="静安", type="展览", status="RAW"),
    ])
    db_session.commit()
    assert client.get("/api/v1/activities?start_date=2025-07-20&end_date=2025-07-27", headers=headers).json()["pagination"]["total"] == 2
    response = client.get("/api/v1/activities?start_date=2025-07-21&end_date=2025-07-21&page=1&page_size=10", headers=headers)
    assert response.json()["pagination"] == {"page": 1, "page_size": 10, "total": 1}
    assert response.json()["data"]["items"][0]["name"] == "次日活动"
    assert client.get("/api/v1/activities?start_date=not-a-date", headers=headers).status_code == 422


def test_get_activity_detail_and_not_found(client: TestClient, db_session: Session, headers: dict[str, str]) -> None:
    activity = make_activity(1)
    db_session.add(activity)
    db_session.commit()
    assert client.get(f"/api/v1/activities/{activity.id}", headers=headers).json()["data"]["name"] == "活动1"
    assert client.get("/api/v1/activities/99999", headers=headers).status_code == 404


def test_update_activity_and_reject_invalid_status_transition(client: TestClient, db_session: Session, headers: dict[str, str]) -> None:
    activity = make_activity(1)
    db_session.add(activity)
    db_session.commit()
    response = client.put(f"/api/v1/activities/{activity.id}", json={"name": "夏日音乐节2025", "price": "50元"}, headers=headers)
    assert response.json()["data"]["name"] == "夏日音乐节2025"
    activity.status = "PUBLISHED"
    db_session.commit()
    assert client.put(f"/api/v1/activities/{activity.id}", json={"status": "RAW"}, headers=headers).status_code == 422


def test_delete_activity_is_soft_delete(client: TestClient, db_session: Session, headers: dict[str, str]) -> None:
    activity = make_activity(1)
    db_session.add(activity)
    db_session.commit()
    assert client.delete(f"/api/v1/activities/{activity.id}", headers=headers).status_code == 200
    assert client.get(f"/api/v1/activities/{activity.id}", headers=headers).status_code == 404


def test_batch_delete_activities_is_atomic_soft_delete(client: TestClient, db_session: Session, headers: dict[str, str]) -> None:
    first, second = make_activity(31), make_activity(32)
    db_session.add_all([first, second]); db_session.commit()

    response = client.request("DELETE", "/api/v1/activities/batch", json={"ids": [first.id, first.id, second.id]}, headers=headers)

    assert response.status_code == 200
    assert response.json()["data"]["deleted_count"] == 2
    db_session.refresh(first); db_session.refresh(second)
    assert first.status == second.status == "DELETED"
    assert client.request("DELETE", "/api/v1/activities/batch", json={"ids": [first.id]}, headers=headers).status_code == 404
    assert client.request("DELETE", "/api/v1/activities/batch", json={"ids": []}, headers=headers).status_code == 422


def test_create_activity_manual_is_not_available(client: TestClient, headers: dict[str, str]) -> None:
    response = client.post("/api/v1/activities", json={"name": "新活动", "city_code": "shanghai", "start_time": "2025-08-01T10:00:00Z", "end_time": "2025-08-01T18:00:00Z", "location": "上海中心", "price": "免费", "type": "展览", "source_url": "https://manual.example.com", "summary": "手动录入的活动"}, headers=headers)
    assert response.status_code == 405
