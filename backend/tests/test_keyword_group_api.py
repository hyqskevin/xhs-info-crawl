"""关键词组 CRUD API 测试。"""
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.security import create_access_token
from app.models.config import City
from app.models.keyword_group import KeywordGroup, KeywordGroupCity, KeywordGroupWord


def _auth() -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token({'sub': 'admin', 'role': 'admin'})}"}


def _seed_city(db: Session, name: str, code: str) -> City:
    city = City(name=name, code=code, enabled=True)
    db.add(city)
    db.commit()
    return city


def test_list_keyword_groups_empty(client: TestClient) -> None:
    response = client.get("/api/v1/settings/keyword-groups", headers=_auth())
    assert response.status_code == 200
    assert response.json()["data"]["items"] == []


def test_create_keyword_group(client: TestClient, db_session: Session) -> None:
    nb = _seed_city(db_session, "宁波", "nb")
    sh = _seed_city(db_session, "上海", "sh")

    response = client.post(
        "/api/v1/settings/keyword-groups",
        json={
            "name": "展览",
            "description": "上海宁波通用",
            "city_codes": ["nb", "sh"],
            "words": ["展览", "活动"],
        },
        headers=_auth(),
    )

    assert response.status_code == 200
    body = response.json()["data"]
    assert body["name"] == "展览"
    assert sorted(body["city_codes"]) == ["nb", "sh"]
    # Python unicode 默认按 code point 排序："展览" < "活动"
    assert body["words"] == sorted(body["words"])
    assert set(body["words"]) == {"活动", "展览"}


def test_create_keyword_group_duplicate_name_422(client: TestClient) -> None:
    response = client.post(
        "/api/v1/settings/keyword-groups",
        json={"name": "展览", "city_codes": [], "words": []},
        headers=_auth(),
    )
    assert response.status_code == 200
    # 第二条同名
    response = client.post(
        "/api/v1/settings/keyword-groups",
        json={"name": "展览", "city_codes": [], "words": []},
        headers=_auth(),
    )
    assert response.status_code in (422, 409)


def test_update_keyword_group_replaces_words(client: TestClient, db_session: Session) -> None:
    _seed_city(db_session, "宁波", "nb")
    create_resp = client.post(
        "/api/v1/settings/keyword-groups",
        json={"name": "咖啡", "city_codes": ["nb"], "words": ["咖啡", "茶"]},
        headers=_auth(),
    )
    kg_id = create_resp.json()["data"]["id"]

    update_resp = client.put(
        f"/api/v1/settings/keyword-groups/{kg_id}/words",
        json={"words": ["咖啡", "拿铁", "奶茶"]},
        headers=_auth(),
    )
    assert update_resp.status_code == 200

    list_resp = client.get(f"/api/v1/settings/keyword-groups/{kg_id}", headers=_auth())
    body = list_resp.json()["data"]
    assert set(body["words"]) == {"咖啡", "拿铁", "奶茶"}
    assert body["words"] == sorted(body["words"])


def test_update_keyword_group_replaces_cities(client: TestClient, db_session: Session) -> None:
    _seed_city(db_session, "宁波", "nb")
    _seed_city(db_session, "上海", "sh")
    create_resp = client.post(
        "/api/v1/settings/keyword-groups",
        json={"name": "亲子", "city_codes": ["nb"], "words": ["亲子"]},
        headers=_auth(),
    )
    kg_id = create_resp.json()["data"]["id"]

    update_resp = client.put(
        f"/api/v1/settings/keyword-groups/{kg_id}/cities",
        json={"city_codes": ["nb", "sh"]},
        headers=_auth(),
    )
    assert update_resp.status_code == 200

    list_resp = client.get(f"/api/v1/settings/keyword-groups/{kg_id}", headers=_auth())
    body = list_resp.json()["data"]
    assert sorted(body["city_codes"]) == ["nb", "sh"]


def test_delete_keyword_group(client: TestClient, db_session: Session) -> None:
    create_resp = client.post(
        "/api/v1/settings/keyword-groups",
        json={"name": "临时", "city_codes": [], "words": []},
        headers=_auth(),
    )
    kg_id = create_resp.json()["data"]["id"]

    del_resp = client.delete(
        f"/api/v1/settings/keyword-groups/{kg_id}", headers=_auth()
    )
    assert del_resp.status_code == 200

    list_resp = client.get("/api/v1/settings/keyword-groups", headers=_auth())
    items = list_resp.json()["data"]["items"]
    assert all(item["id"] != kg_id for item in items)
