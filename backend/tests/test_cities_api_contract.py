"""城市 CRUD API 契约测试。"""
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.security import create_access_token
from app.models.config import City, Keyword


def _auth() -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token({'sub': 'admin', 'role': 'admin'})}"}


def test_list_cities_empty(client: TestClient) -> None:
    resp = client.get("/api/v1/settings/cities", headers=_auth())
    assert resp.status_code == 200
    assert resp.json()["data"] == []


def test_create_city_with_keywords(client: TestClient, db_session: Session) -> None:
    resp = client.post(
        "/api/v1/settings/cities",
        json={
            "name": "杭州",
            "keywords": ["周末", "展览"],
            "recent_filter": "一周内",
            "enabled": True,
        },
        headers=_auth(),
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()["data"]
    assert body["name"] == "杭州"
    assert "code" in body
    assert sorted(body["keywords"]) == ["周末", "展览"]

    # DB 也确认关键词已写入
    city = db_session.query(City).filter_by(name="杭州").one()
    words = {row.word for row in db_session.query(Keyword).filter_by(city_code=city.code).all()}
    assert words == {"周末", "展览"}


def test_update_city_replaces_keywords(client: TestClient) -> None:
    create = client.post(
        "/api/v1/settings/cities",
        json={"name": "深圳", "keywords": ["旧词"]},
        headers=_auth(),
    )
    city_id = create.json()["data"]["id"]

    upd = client.put(
        f"/api/v1/settings/cities/{city_id}",
        json={"name": "深圳", "keywords": ["新词A", "新词B"], "recent_filter": "半年内"},
        headers=_auth(),
    )
    assert upd.status_code == 200, upd.text
    data = upd.json()["data"]
    assert data["recent_filter"] == "半年内"
    assert sorted(data["keywords"]) == ["新词A", "新词B"]


def test_update_city_rejects_unknown_id(client: TestClient) -> None:
    resp = client.put(
        "/api/v1/settings/cities/9999",
        json={"name": "南京"},
        headers=_auth(),
    )
    assert resp.status_code == 404


def test_delete_city_cascades_keywords(client: TestClient, db_session: Session) -> None:
    create = client.post(
        "/api/v1/settings/cities",
        json={"name": "成都", "keywords": ["k1", "k2"]},
        headers=_auth(),
    )
    city_id = create.json()["data"]["id"]
    city_code = create.json()["data"]["code"]

    delete = client.delete(f"/api/v1/settings/cities/{city_id}", headers=_auth())
    assert delete.status_code == 200

    # 关键词表被级联清掉
    remaining = db_session.query(Keyword).filter_by(city_code=city_code).count()
    assert remaining == 0


def test_opencli_config_endpoint(client: TestClient) -> None:
    resp = client.get("/api/v1/settings/opencli/config", headers=_auth())
    assert resp.status_code == 200
    body = resp.json()["data"]
    assert {"endpoint", "target_count", "scroll_rounds"} <= body.keys()
