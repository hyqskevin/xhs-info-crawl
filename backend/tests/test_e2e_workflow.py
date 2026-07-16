from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.models.user import User


def test_editorial_workflow_from_login_to_dual_report_download(client: TestClient, db_session: Session) -> None:
    db_session.add(User(username="admin", password_hash=hash_password("Admin@123"), role="admin"))
    db_session.commit()

    login = client.post("/api/v1/auth/login", json={"username": "admin", "password": "Admin@123"})
    assert login.status_code == 200
    headers = {"Authorization": f"Bearer {login.json()['data']['access_token']}"}

    created = client.post(
        "/api/v1/activities",
        headers=headers,
        json={
            "name": "夏日音乐节",
            "city_code": "shanghai",
            "start_time": "2025-07-20T18:00:00Z",
            "end_time": "2025-07-20T22:00:00Z",
            "location": "徐汇滨江",
            "price": "免费",
            "type": "演出",
            "source_url": "https://www.xiaohongshu.com/a/1",
            "summary": "户外音乐节",
        },
    )
    assert created.status_code == 201
    activity_id = created.json()["data"]["id"]

    approved = client.put(f"/api/v1/activities/{activity_id}", headers=headers, json={"status": "APPROVED"})
    assert approved.status_code == 200
    assert client.get("/api/v1/activities?status=APPROVED", headers=headers).json()["pagination"]["total"] == 1

    generated = client.post("/api/v1/reports/generate", headers=headers, json={"week": "2025-W29", "cities": ["shanghai"]})
    assert generated.status_code == 200
    report_id = generated.json()["data"]["id"]

    markdown = client.get(f"/api/v1/reports/{report_id}/download?format=md", headers=headers)
    spreadsheet = client.get(f"/api/v1/reports/{report_id}/download?format=xlsx", headers=headers)
    assert "夏日音乐节" in markdown.text
    assert markdown.headers["content-disposition"].endswith('2025-W29.md"')
    assert spreadsheet.content.startswith(b"PK")
    assert spreadsheet.headers["content-disposition"].endswith('2025-W29.xlsx"')
