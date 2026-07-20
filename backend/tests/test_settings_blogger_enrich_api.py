"""博主信息补全 API：

POST /api/v1/settings/bloggers/{id}/enrich
- profile_url 已有 → 200 不变
- profile_url 空 + 找到匹配 → 回填 user_id + profile_url，返回 200
- profile_url 空 + 找不到 → 422
- 博主不存在 → 404
"""

from unittest.mock import patch
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.config import Blogger, City
from app.models.blogger_city import BloggerCity


def _make_blogger(db_session: Session, username: str, profile_url: str = "", platform_user_id: str | None = None) -> Blogger:
    city = City(name="测试城市", code="test-city", enabled=True)
    db_session.add(city)
    db_session.flush()
    b = Blogger(
        username=username,
        profile_url=profile_url,
        platform_user_id=platform_user_id,
        enabled=True,
    )
    db_session.add(b)
    db_session.flush()
    db_session.add(BloggerCity(blogger_id=b.id, city_code="test-city", enabled=True))
    db_session.commit()
    return b


def test_enrich_returns_unchanged_when_profile_url_already_set(client: TestClient, db_session: Session):
    b = _make_blogger(
        db_session, "已配置",
        profile_url="https://www.xiaohongshu.com/user/profile/existing",
        platform_user_id="existing_id",
    )

    response = client.post(f"/api/v1/settings/bloggers/{b.id}/enrich", headers=_auth())
    assert response.status_code == 200
    assert response.json()["message"] == "博主信息已完整，无需补充"
    assert response.json()["data"]["profile_url"] == "https://www.xiaohongshu.com/user/profile/existing"


def test_enrich_fills_profile_url_when_missing(client: TestClient, db_session: Session):
    b = _make_blogger(db_session, "从零发现宁波")

    def mock_enrich(db, bloggers, **kwargs):
        bloggers[0].platform_user_id = "619ca5dc0000000010007e92"
        bloggers[0].profile_url = "https://www.xiaohongshu.com/user/profile/619ca5dc0000000010007e92"
        db.commit()
        return [bloggers[0].id]

    with patch("app.services.blogger_enricher.enrich_bloggers", mock_enrich):
        response = client.post(f"/api/v1/settings/bloggers/{b.id}/enrich", headers=_auth())

    assert response.status_code == 200, response.text
    body = response.json()["data"]
    assert body["username"] == "从零发现宁波"
    assert body["profile_url"] == "https://www.xiaohongshu.com/user/profile/619ca5dc0000000010007e92"
    assert body["platform_user_id"] == "619ca5dc0000000010007e92"


def test_enrich_422_when_no_match_in_search(client: TestClient, db_session: Session):
    b = _make_blogger(db_session, "找不到")

    with patch("app.services.opencli_adapter.OpenCLIAdapter") as mock_adapter:
        mock_adapter.return_value.run.return_value = [
            {"author": "别的博主", "author_url": "https://xhs/user/profile/zzz"}
        ]
        response = client.post(f"/api/v1/settings/bloggers/{b.id}/enrich", headers=_auth())

    assert response.status_code == 422
    assert "未找到匹配" in response.json()["message"]


def test_enrich_404_when_blogger_not_found(client: TestClient):
    response = client.post("/api/v1/settings/bloggers/99999/enrich", headers=_auth())
    assert response.status_code == 404


def _auth():
    from app.core.security import create_access_token
    return {"Authorization": f"Bearer {create_access_token({'sub': 'admin', 'role': 'admin'})}"}
