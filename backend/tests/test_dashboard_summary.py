"""仪表盘 `/api/v1/dashboard/summary` 接口测试。"""
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.security import create_access_token
from app.models.activity import Activity
from app.models.task import CrawlTask


def _auth() -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token({'sub': 'admin', 'role': 'admin'})}"}


def test_dashboard_summary_when_no_tasks(client: TestClient) -> None:
    resp = client.get("/api/v1/dashboard/summary", headers=_auth())
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["weekly_notes_count"] == 0
    assert data["weekly_activities_count"] == 0
    assert data["last_task"] is None


def test_dashboard_summary_reports_latest_task(
    client: TestClient, db_session: Session
) -> None:
    task = CrawlTask(
        type="keyword",
        status="COMPLETED",
        params={"city": "sh", "keywords": ["测试"]},
        total_notes=10,
        downloaded_notes=10,
        ocr_notes=10,
        extracted_notes=8,
        success_notes=7,
        failed_notes=1,
        skipped_notes=2,
    )
    db_session.add(task)
    db_session.commit()

    resp = client.get("/api/v1/dashboard/summary", headers=_auth())
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["last_task"] is not None
    assert data["last_task"]["status"] == "COMPLETED"
    assert data["last_task"]["total_notes"] == 10
    assert data["last_task"]["progress_percent"] is not None


def test_dashboard_summary_counts_activities(
    client: TestClient, db_session: Session
) -> None:
    activity = Activity(
        note_id=None,
        name="示例活动",
        city_code="sh",
        type="演出",
        source_url="https://xhs.example/n/1",
    )
    db_session.add(activity)
    db_session.commit()

    resp = client.get("/api/v1/dashboard/summary", headers=_auth())
    assert resp.status_code == 200
    assert resp.json()["data"]["weekly_activities_count"] >= 1


def test_dashboard_requires_auth(client: TestClient) -> None:
    resp = client.get("/api/v1/dashboard/summary")
    assert resp.status_code == 401
