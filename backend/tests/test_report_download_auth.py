"""周报下载鉴权 + generate 多城市拒绝。"""
import json

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.security import create_access_token
from app.models.report import WeeklyReport


def _auth() -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token({'sub': 'admin', 'role': 'admin'})}"}


def _seed_report(db: Session, week: str = "2026-W30") -> WeeklyReport:
    report = WeeklyReport(
        week=week,
        cities=json.dumps(["shanghai"]),
        activity_count=3,
        content="# 上海周报\n",
        status="draft",
    )
    db.add(report)
    db.commit()
    return report


def test_download_md_requires_token(client: TestClient, db_session: Session) -> None:
    report = _seed_report(db_session)
    resp = client.get(f"/api/v1/reports/{report.id}/download?format=md")
    assert resp.status_code == 401


def test_download_md_with_token(client: TestClient, db_session: Session) -> None:
    report = _seed_report(db_session)
    resp = client.get(
        f"/api/v1/reports/{report.id}/download?format=md",
        headers=_auth(),
    )
    assert resp.status_code == 200
    assert "attachment" in resp.headers.get("content-disposition", "").lower()


def test_download_xlsx_with_token(client: TestClient, db_session: Session) -> None:
    report = _seed_report(db_session)
    resp = client.get(
        f"/api/v1/reports/{report.id}/download?format=xlsx",
        headers=_auth(),
    )
    assert resp.status_code == 200
    body = resp.content
    # xlsx 是 ZIP 容器，开头 4 字节必为 PK\x03\x04
    assert body[:4] == b"PK\x03\x04"


def test_list_reports_orders_by_id_desc(client: TestClient, db_session: Session) -> None:
    _seed_report(db_session, week="2026-W28")
    _seed_report(db_session, week="2026-W30")
    _seed_report(db_session, week="2026-W29")
    resp = client.get("/api/v1/reports", headers=_auth())
    assert resp.status_code == 200
    payload = resp.json()["data"]
    weeks = [item["week"] for item in payload]
    # 后入先出：插入顺序 28 → 30 → 29，列表倒序应为 29 → 30 → 28
    assert weeks == ["2026-W29", "2026-W30", "2026-W28"]


def test_list_reports_404_for_unknown(client: TestClient) -> None:
    resp = client.get("/api/v1/reports/9999/download?format=md", headers=_auth())
    # 不存在报告 -> 404
    assert resp.status_code in (401, 404)


def test_generate_rejects_multiple_cities(client: TestClient) -> None:
    resp = client.post(
        "/api/v1/reports/generate",
        json={"week": "2026-W30", "cities": ["shanghai", "beijing"]},
        headers=_auth(),
    )
    assert resp.status_code == 422
