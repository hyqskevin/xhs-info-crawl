"""健康检查 API 测试。"""
from fastapi.testclient import TestClient


def test_health_returns_ok(client: TestClient) -> None:
    resp = client.get("/api/v1/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["code"] == 200
    assert body["data"]["status"] == "ok"
    assert body["data"]["database"] in {"sqlite", "postgresql"}


def test_health_no_auth_required(client: TestClient) -> None:
    # 健康检查允许未登录调用，便于外部监控
    resp = client.get("/api/v1/health")
    assert resp.status_code == 200
