from fastapi.testclient import TestClient

from app.main import app


def test_health_endpoint_reports_sqlite_backend() -> None:
    with TestClient(app) as client:
        response = client.get("/api/v1/health")

    assert response.status_code == 200
    assert response.json() == {
        "code": 200,
        "message": "success",
        "data": {"status": "ok", "database": "sqlite"},
    }
