"""博主分组（白名单组）CRUD API 测试。

关联 spec: docs/superpowers/specs/2026-07-25-scheduled-crawls-and-dashboard-charts-design.md
"""
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.security import create_access_token
from app.models.config import Blogger


def _auth() -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token({'sub': 'admin', 'role': 'admin'})}"}


def _seed_bloggers(db: Session) -> list[Blogger]:
    bloggers = [
        Blogger(username="博主A", profile_url="https://xhs/u/a", enabled=True),
        Blogger(username="博主B", profile_url="https://xhs/u/b", enabled=True),
        Blogger(username="博主C", profile_url="https://xhs/u/c", enabled=True),
    ]
    db.add_all(bloggers)
    db.commit()
    for b in bloggers:
        db.refresh(b)
    return bloggers


def test_list_blogger_groups_empty(client: TestClient) -> None:
    response = client.get("/api/v1/settings/blogger-groups", headers=_auth())
    assert response.status_code == 200
    assert response.json()["data"]["items"] == []


def test_create_blogger_group_with_members(client: TestClient, db_session: Session) -> None:
    bloggers = _seed_bloggers(db_session)
    response = client.post(
        "/api/v1/settings/blogger-groups",
        json={"name": "本地活动号", "description": "重点", "blogger_ids": [bloggers[0].id, bloggers[1].id]},
        headers=_auth(),
    )
    assert response.status_code == 200, response.text
    body = response.json()["data"]
    assert body["name"] == "本地活动号"
    assert sorted(body["blogger_ids"]) == sorted([bloggers[0].id, bloggers[1].id])
    assert body["enabled"] is True


def test_create_blogger_group_duplicate_name_409(client: TestClient, db_session: Session) -> None:
    _seed_bloggers(db_session)
    client.post("/api/v1/settings/blogger-groups", json={"name": "组一", "blogger_ids": []}, headers=_auth())
    response = client.post("/api/v1/settings/blogger-groups", json={"name": "组一", "blogger_ids": []}, headers=_auth())
    assert response.status_code == 409


def test_replace_blogger_group_members(client: TestClient, db_session: Session) -> None:
    bloggers = _seed_bloggers(db_session)
    created = client.post(
        "/api/v1/settings/blogger-groups",
        json={"name": "组一", "blogger_ids": [bloggers[0].id]},
        headers=_auth(),
    ).json()["data"]
    response = client.put(
        f"/api/v1/settings/blogger-groups/{created['id']}/members",
        json={"blogger_ids": [bloggers[1].id, bloggers[2].id]},
        headers=_auth(),
    )
    assert response.status_code == 200
    assert sorted(response.json()["data"]["blogger_ids"]) == sorted([bloggers[1].id, bloggers[2].id])
    detail = client.get(f"/api/v1/settings/blogger-groups/{created['id']}", headers=_auth()).json()["data"]
    assert bloggers[0].id not in detail["blogger_ids"]


def test_delete_blogger_group_cascades_members(client: TestClient, db_session: Session) -> None:
    from app.models.blogger_group import BloggerGroupMember

    bloggers = _seed_bloggers(db_session)
    created = client.post(
        "/api/v1/settings/blogger-groups",
        json={"name": "组一", "blogger_ids": [bloggers[0].id, bloggers[1].id]},
        headers=_auth(),
    ).json()["data"]
    response = client.delete(f"/api/v1/settings/blogger-groups/{created['id']}", headers=_auth())
    assert response.status_code == 200
    remaining = db_session.query(BloggerGroupMember).filter_by(group_id=created["id"]).count()
    assert remaining == 0
