"""关键词组 CRUD API 测试。"""
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.security import create_access_token
from app.models.config import City
from app.models.keyword_group import KeywordGroup, KeywordGroupCity, KeywordGroupWord


def _auth() -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token({'sub': 'admin', 'role': 'admin', 'permissions': ['*']})}"}


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


def test_keyword_group_with_two_cities_returns_cities_field(client: TestClient, db_session: Session) -> None:
    from app.models.config import City
    db_session.add_all([
        City(code="nb", name="宁波", enabled=True),
        City(code="sh", name="上海", enabled=True),
    ])
    db_session.commit()
    payload = {"name": "AI", "city_codes": ["nb", "sh"], "words": ["trae"]}
    r = client.post("/api/v1/settings/keyword-groups", json=payload, headers=_auth())
    assert r.status_code == 200
    kg_id = r.json()["data"]["id"]
    r2 = client.get("/api/v1/settings/keyword-groups", headers=_auth())
    row = next(g for g in r2.json()["data"]["items"] if g["id"] == kg_id)
    assert "cities" in row
    assert sorted(row["cities"], key=lambda c: c["code"]) == [
        {"code": "nb", "name": "宁波"},
        {"code": "sh", "name": "上海"},
    ]
    assert sorted(row["city_codes"]) == ["nb", "sh"]


def test_keyword_group_with_missing_city_returns_code_fallback(client: TestClient, db_session: Session) -> None:
    """脏数据：KeywordGroupCity 含 City 不存在的 code，cities[].name 应兜底为 code。"""
    from app.models.config import City
    from app.models.keyword_group import KeywordGroup, KeywordGroupCity
    db_session.add(City(code="nb", name="宁波", enabled=True))
    db_session.flush()
    kg = KeywordGroup(name="脏数据组", enabled=True)
    db_session.add(kg)
    db_session.flush()
    db_session.add_all([
        KeywordGroupCity(keyword_group_id=kg.id, city_code="nb", enabled=True),
        KeywordGroupCity(keyword_group_id=kg.id, city_code="city-99f1e469", enabled=True),
    ])
    db_session.commit()
    r = client.get("/api/v1/settings/keyword-groups", headers=_auth())
    row = next(g for g in r.json()["data"]["items"] if g["name"] == "脏数据组")
    cities_by_code = {c["code"]: c["name"] for c in row["cities"]}
    assert cities_by_code["nb"] == "宁波"
    assert cities_by_code["city-99f1e469"] == "city-99f1e469"


def test_keyword_group_with_zero_cities_returns_empty_list(client: TestClient) -> None:
    payload = {"name": "无城市组", "city_codes": [], "words": ["x"]}
    r = client.post("/api/v1/settings/keyword-groups", json=payload, headers=_auth())
    kg_id = r.json()["data"]["id"]
    r2 = client.get("/api/v1/settings/keyword-groups", headers=_auth())
    row = next(g for g in r2.json()["data"]["items"] if g["id"] == kg_id)
    assert row["cities"] == []
    assert row["city_codes"] == []


def test_cities_field_has_both_code_and_name_keys(client: TestClient, db_session: Session) -> None:
    from app.models.config import City
    db_session.add(City(code="hz", name="杭州", enabled=True))
    db_session.commit()
    payload = {"name": "键名检查", "city_codes": ["hz"], "words": []}
    r = client.post("/api/v1/settings/keyword-groups", json=payload, headers=_auth())
    kg_id = r.json()["data"]["id"]
    r2 = client.get("/api/v1/settings/keyword-groups", headers=_auth())
    row = next(g for g in r2.json()["data"]["items"] if g["id"] == kg_id)
    assert set(row["cities"][0].keys()) >= {"code", "name"}
