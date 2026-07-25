"""定时任务（/schedules）CRUD API 测试。

关联 spec: docs/superpowers/specs/2026-07-25-scheduled-crawls-and-dashboard-charts-design.md
"""
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.security import create_access_token
from app.models.config import Blogger, City
from app.models.blogger_city import BloggerCity
from app.models.keyword_group import KeywordGroup, KeywordGroupCity, KeywordGroupWord


def _auth() -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token({'sub': 'admin', 'role': 'admin'})}"}


def _seed_scope(db: Session) -> tuple[City, KeywordGroup, int]:
    city = City(name="宁波", code="city-nb01", enabled=True)
    kg = KeywordGroup(name="展览", enabled=True)
    blogger = Blogger(username="博主A", profile_url="https://xhs/u/a", enabled=True)
    db.add_all([city, kg, blogger])
    db.commit()
    for row in (kg, blogger):
        db.refresh(row)
    db.add(KeywordGroupCity(keyword_group_id=kg.id, city_code=city.code, enabled=True))
    db.add(KeywordGroupWord(keyword_group_id=kg.id, word="展览", enabled=True))
    db.add(BloggerCity(blogger_id=blogger.id, city_code=city.code, enabled=True))
    db.commit()
    bg = client_post_blogger_group(db, "白名单组", [blogger.id])
    return city, kg, bg


def client_post_blogger_group(db: Session, name: str, blogger_ids: list[int]) -> int:
    from app.models.blogger_group import BloggerGroup, BloggerGroupMember

    group = BloggerGroup(name=name, enabled=True)
    db.add(group)
    db.commit()
    db.refresh(group)
    for blogger_id in blogger_ids:
        db.add(BloggerGroupMember(group_id=group.id, blogger_id=blogger_id))
    db.commit()
    return group.id


def _payload(city: City, kg: KeywordGroup, bg_id: int, **overrides) -> dict:
    payload = {
        "name": "每周一早上",
        "day_of_week": 1,
        "hour": 2,
        "minute": 30,
        "city_code": city.code,
        "keyword_group_ids": [kg.id],
        "blogger_group_ids": [bg_id],
        "recent_filter": "一周内",
        "enabled": True,
    }
    payload.update(overrides)
    return payload


def test_create_and_list_schedule(client: TestClient, db_session: Session) -> None:
    city, kg, bg = _seed_scope(db_session)
    response = client.post("/api/v1/schedules", json=_payload(city, kg, bg), headers=_auth())
    assert response.status_code == 200, response.text
    body = response.json()["data"]
    assert body["day_of_week"] == 1
    assert body["keyword_group_ids"] == [kg.id]
    assert body["blogger_group_ids"] == [bg]

    listing = client.get("/api/v1/schedules", headers=_auth())
    assert listing.status_code == 200
    items = listing.json()["data"]["items"]
    assert len(items) == 1
    assert items[0]["name"] == "每周一早上"
    assert items[0]["last_task"] is None


def test_schedule_requires_at_least_one_group(client: TestClient, db_session: Session) -> None:
    city, kg, bg = _seed_scope(db_session)
    response = client.post(
        "/api/v1/schedules",
        json=_payload(city, kg, bg, keyword_group_ids=[], blogger_group_ids=[]),
        headers=_auth(),
    )
    assert response.status_code == 422
    assert "关键词组或博主组" in response.text


def test_schedule_validates_time_bounds(client: TestClient, db_session: Session) -> None:
    city, kg, bg = _seed_scope(db_session)
    for field, value in (("day_of_week", 0), ("day_of_week", 8), ("hour", 24), ("minute", 60)):
        response = client.post("/api/v1/schedules", json=_payload(city, kg, bg, **{field: value}), headers=_auth())
        assert response.status_code == 422, f"{field}={value} 应 422"


def test_schedule_validates_city_and_groups(client: TestClient, db_session: Session) -> None:
    city, kg, bg = _seed_scope(db_session)
    bad_city = client.post("/api/v1/schedules", json=_payload(city, kg, bg, city_code="不存在"), headers=_auth())
    assert bad_city.status_code == 422
    bad_kg = client.post("/api/v1/schedules", json=_payload(city, kg, bg, keyword_group_ids=[99999]), headers=_auth())
    assert bad_kg.status_code == 422
    bad_bg = client.post("/api/v1/schedules", json=_payload(city, kg, bg, blogger_group_ids=[99999]), headers=_auth())
    assert bad_bg.status_code == 422


def test_update_and_delete_schedule(client: TestClient, db_session: Session) -> None:
    city, kg, bg = _seed_scope(db_session)
    created = client.post("/api/v1/schedules", json=_payload(city, kg, bg), headers=_auth()).json()["data"]
    updated = client.put(
        f"/api/v1/schedules/{created['id']}",
        json=_payload(city, kg, bg, name="改名", hour=8, enabled=False),
        headers=_auth(),
    )
    assert updated.status_code == 200
    body = updated.json()["data"]
    assert body["name"] == "改名"
    assert body["hour"] == 8
    assert body["enabled"] is False

    deleted = client.delete(f"/api/v1/schedules/{created['id']}", headers=_auth())
    assert deleted.status_code == 200
    listing = client.get("/api/v1/schedules", headers=_auth()).json()["data"]["items"]
    assert listing == []
