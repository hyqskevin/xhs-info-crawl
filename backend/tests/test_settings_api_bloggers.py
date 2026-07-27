"""博主 CRUD 路由契约测试（创建 / 列表 / 不必填 xhs_id / 多城市）。"""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.security import create_access_token
from app.models.config import Blogger, City
from app.models.blogger_city import BloggerCity


def _auth() -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token({'sub': 'admin', 'role': 'admin'})}"}


def _seed_city(db: Session, name: str, code: str) -> City:
    city = City(name=name, code=code, enabled=True)
    db.add(city)
    db.commit()
    return city


def test_list_bloggers_empty(client: TestClient) -> None:
    resp = client.get("/api/v1/settings/bloggers", headers=_auth())
    assert resp.status_code == 200
    assert resp.json()["data"] == []


def test_create_blogger_without_xhs_id(client: TestClient, db_session: Session) -> None:
    _seed_city(db_session, "上海", "sh")
    _seed_city(db_session, "北京", "bj")

    resp = client.post(
        "/api/v1/settings/bloggers",
        json={
            "username": "小红",
            "city_codes": ["sh", "bj"],
        },
        headers=_auth(),
    )
    assert resp.status_code == 201, resp.text
    data = resp.json()["data"]
    assert data["username"] == "小红"
    assert data["platform_user_id"] in (None, "")
    assert sorted(data["city_codes"]) == ["bj", "sh"]

    # 实际落库
    blogger = db_session.query(Blogger).filter_by(username="小红").one()
    rows = db_session.query(BloggerCity).filter_by(blogger_id=blogger.id).all()
    assert {r.city_code for r in rows} == {"sh", "bj"}


def test_create_blogger_accepts_blank_username_at_api_level(client: TestClient) -> None:
    """接口层容许 username=''（min_length 不限定），用于校验若干边界可写。"""
    resp = client.post(
        "/api/v1/settings/bloggers",
        json={"username": "", "city_codes": []},
        headers=_auth(),
    )
    # 此项目允许空 username 在接口层；后续以 import 阶段验证
    assert resp.status_code == 201


def test_update_blogger_replaces_cities(client: TestClient, db_session: Session) -> None:
    _seed_city(db_session, "上海", "sh")
    _seed_city(db_session, "杭州", "hz")

    create = client.post(
        "/api/v1/settings/bloggers",
        json={"username": "lala", "city_codes": ["sh"]},
        headers=_auth(),
    )
    blogger_id = create.json()["data"]["id"]

    upd = client.put(
        f"/api/v1/settings/bloggers/{blogger_id}",
        json={"username": "lala", "city_codes": ["sh", "hz"], "platform_user_id": "u-1", "profile_url": "https://xhs/u-1"},
        headers=_auth(),
    )
    assert upd.status_code == 200, upd.text
    data = upd.json()["data"]
    assert sorted(data["city_codes"]) == ["hz", "sh"]
    assert data["platform_user_id"] == "u-1"


def test_update_blogger_404(client: TestClient) -> None:
    resp = client.put(
        "/api/v1/settings/bloggers/9999",
        json={"username": "ghost"},
        headers=_auth(),
    )
    assert resp.status_code == 404


def test_delete_blogger(client: TestClient, db_session: Session) -> None:
    create = client.post(
        "/api/v1/settings/bloggers",
        json={"username": "to-delete"},
        headers=_auth(),
    )
    bid = create.json()["data"]["id"]

    delete = client.delete(f"/api/v1/settings/bloggers/{bid}", headers=_auth())
    assert delete.status_code == 200

    remaining = db_session.query(Blogger).filter_by(id=bid).count()
    assert remaining == 0


@pytest.mark.parametrize("missing", ["platform_user_id", "profile_url"])
def test_create_blogger_omits_optional_field(
    client: TestClient, missing: str
) -> None:
    payload: dict[str, object] = {"username": f"blogger-{missing}"}
    payload[missing] = None

    resp = client.post(
        "/api/v1/settings/bloggers",
        json=payload,
        headers=_auth(),
    )
    # nullable 字段允许为 None/空字符串：API 不会因 null 失败
    assert resp.status_code == 201
