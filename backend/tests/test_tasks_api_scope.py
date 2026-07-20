"""任务入口校验：effective 抓取范围（关键词 ∪ 博主）不能同时为空。"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.security import create_access_token
from app.models.config import City, Keyword


def _auth() -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token({'sub': 'admin', 'role': 'admin'})}"}


def test_crawl_rejects_when_no_keywords_and_no_bloggers(client: TestClient, db_session: Session):
    db_session.add(City(name="上海", code="city-99f1e469", enabled=True))
    db_session.commit()

    response = client.post(
        "/api/v1/tasks/crawl",
        json={"city": "city-99f1e469", "keywords": [], "blogger_ids": []},
        headers=_auth(),
    )
    assert response.status_code == 422
    assert "请至少启用一个关键词或博主" in response.text


def test_crawl_rejects_when_only_blogger_ids_empty(client: TestClient, db_session: Session, celery_dispatches: list[tuple]):
    db_session.add(City(name="上海", code="city-99f1e469", enabled=True))
    db_session.add(Keyword(word="A", city_code="city-99f1e469", enabled=True))
    db_session.commit()

    response = client.post(
        "/api/v1/tasks/crawl",
        json={"city": "city-99f1e469", "keywords": ["A"], "blogger_ids": []},
        headers=_auth(),
    )
    # blogger_ids=[] 显式禁用博主；keywords=["A"] 非空 → 通过（effective 范围非空）
    assert response.status_code == 202, response.text
    data = response.json()["data"]
    assert celery_dispatches == [(data["id"], data["run_token"], {})]
