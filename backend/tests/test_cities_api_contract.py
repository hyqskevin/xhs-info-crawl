"""城市 CRUD API 契约测试。"""
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.security import create_access_token
from app.models.config import City


def _auth() -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token({'sub': 'admin', 'role': 'admin'})}"}


def test_list_cities_empty(client: TestClient) -> None:
    resp = client.get("/api/v1/settings/cities", headers=_auth())
    assert resp.status_code == 200
    assert resp.json()["data"] == []


def test_create_city(client: TestClient, db_session: Session) -> None:
    resp = client.post(
        "/api/v1/settings/cities",
        json={
            "name": "杭州",
            "recent_filter": "一周内",
            "enabled": True,
        },
        headers=_auth(),
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()["data"]
    assert body["name"] == "杭州"
    assert "code" in body

    # DB 确认城市已写入
    city = db_session.query(City).filter_by(name="杭州").one()
    assert city.code == body["code"]


def test_update_city(client: TestClient) -> None:
    create = client.post(
        "/api/v1/settings/cities",
        json={"name": "深圳"},
        headers=_auth(),
    )
    city_id = create.json()["data"]["id"]

    upd = client.put(
        f"/api/v1/settings/cities/{city_id}",
        json={"name": "深圳", "recent_filter": "半年内"},
        headers=_auth(),
    )
    assert upd.status_code == 200, upd.text
    data = upd.json()["data"]
    assert data["recent_filter"] == "半年内"


def test_update_city_rejects_unknown_id(client: TestClient) -> None:
    resp = client.put(
        "/api/v1/settings/cities/9999",
        json={"name": "南京"},
        headers=_auth(),
    )
    assert resp.status_code == 404


def test_opencli_config_endpoint(client: TestClient) -> None:
    resp = client.get("/api/v1/settings/opencli/config", headers=_auth())
    assert resp.status_code == 200
    body = resp.json()["data"]
    assert {"endpoint", "target_count", "scroll_rounds"} <= body.keys()
