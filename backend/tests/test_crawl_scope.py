"""抓取范围计算：根据 task_params 与城市 enabled 配置生成最终的
关键词列表与博主列表。

规则：
- task_params 字段不存在 → 取城市 enabled 配置（默认行为）
- task_params 字段是空列表 [] → 视作用户主动禁用该项
- task_params 字段是非空列表 → 用列表里的（覆盖默认）
"""

import pytest
from sqlalchemy.orm import Session

from app.models.blogger_city import BloggerCity
from app.models.config import Blogger, City, Keyword


def _make_city(db_session: Session, code: str = "nb", name: str = "宁波") -> City:
    city = City(name=name, code=code, enabled=True)
    db_session.add(city)
    db_session.flush()
    return city


def _make_keyword(db_session: Session, city: City, word: str) -> Keyword:
    kw = Keyword(word=word, city_code=city.code, enabled=True)
    db_session.add(kw)
    return kw


def _make_blogger(db_session: Session, city: City, username: str, profile_url: str = "https://xhs/u/x") -> Blogger:
    b = Blogger(
        username=username,
        profile_url=profile_url,
        city_code=city.code,
        enabled=True,
        platform_user_id=f"xhs_{username}",
    )
    db_session.add(b)
    db_session.flush()
    db_session.add(BloggerCity(blogger_id=b.id, city_code=city.code, enabled=True))
    db_session.commit()
    return b


# ===== 关键词 =====

def test_resolve_effective_keywords_uses_city_config_when_task_param_missing(db_session: Session):
    city = _make_city(db_session)
    _make_keyword(db_session, city, "A")
    _make_keyword(db_session, city, "B")
    db_session.flush()

    from app.services.crawl_scope import resolve_effective_keywords
    assert resolve_effective_keywords(db_session, city, {}) == ["A", "B"]


def test_resolve_effective_keywords_overrides_city_config_when_task_param_set(db_session: Session):
    city = _make_city(db_session)
    _make_keyword(db_session, city, "A")
    _make_keyword(db_session, city, "B")
    db_session.flush()

    from app.services.crawl_scope import resolve_effective_keywords
    assert resolve_effective_keywords(db_session, city, {"keywords": ["A"]}) == ["A"]


def test_resolve_effective_keywords_returns_empty_when_task_param_disables(db_session: Session):
    city = _make_city(db_session)
    _make_keyword(db_session, city, "A")
    db_session.flush()

    from app.services.crawl_scope import resolve_effective_keywords
    assert resolve_effective_keywords(db_session, city, {"keywords": []}) == []


# ===== 博主 =====

def test_resolve_effective_bloggers_uses_city_config_when_task_param_missing(db_session: Session):
    city = _make_city(db_session)
    _make_blogger(db_session, city, "b1")
    _make_blogger(db_session, city, "b2")
    db_session.flush()

    from app.services.crawl_scope import resolve_effective_bloggers
    result = resolve_effective_bloggers(db_session, city, {})
    assert [b.username for b in result] == ["b1", "b2"]


def test_resolve_effective_bloggers_filters_by_ids_when_overridden(db_session: Session):
    city = _make_city(db_session)
    b1 = _make_blogger(db_session, city, "b1")
    b2 = _make_blogger(db_session, city, "b2")
    db_session.flush()

    from app.services.crawl_scope import resolve_effective_bloggers
    result = resolve_effective_bloggers(db_session, city, {"blogger_ids": [b2.id]})
    assert [b.username for b in result] == ["b2"]


def test_resolve_effective_bloggers_returns_empty_when_task_param_disables(db_session: Session):
    city = _make_city(db_session)
    _make_blogger(db_session, city, "b1")
    db_session.flush()

    from app.services.crawl_scope import resolve_effective_bloggers
    assert resolve_effective_bloggers(db_session, city, {"blogger_ids": []}) == []


def test_blogger_bound_to_other_city_not_returned(db_session: Session):
    """博主只绑定到 A 城市，B 城市的抓取任务不应命中。"""
    city_a = _make_city(db_session, code="a_code", name="城市A")
    city_b = _make_city(db_session, code="b_code", name="城市B")
    b1 = _make_blogger(db_session, city_a, "b1")

    from app.services.crawl_scope import resolve_effective_bloggers
    result_a = resolve_effective_bloggers(db_session, city_a, {})
    result_b = resolve_effective_bloggers(db_session, city_b, {})
    assert [b.id for b in result_a] == [b1.id]
    assert result_b == []


def test_blogger_bound_to_two_cities_returned_for_both(db_session: Session):
    """同一博主绑定到 A 与 B，两城抓取都能命中。"""
    city_a = _make_city(db_session, code="a_code2", name="城市A")
    city_b = _make_city(db_session, code="b_code2", name="城市B")
    b1 = _make_blogger(db_session, city_a, "b1")
    db_session.add(BloggerCity(blogger_id=b1.id, city_code=city_b.code, enabled=True))
    db_session.flush()

    from app.services.crawl_scope import resolve_effective_bloggers
    result_a = resolve_effective_bloggers(db_session, city_a, {})
    result_b = resolve_effective_bloggers(db_session, city_b, {})
    assert [b.id for b in result_a] == [b1.id]
    assert [b.id for b in result_b] == [b1.id]


# ===== 综合 =====

def test_resolve_crawl_scope_combines_both(db_session: Session):
    city = _make_city(db_session)
    _make_keyword(db_session, city, "A")
    b1 = _make_blogger(db_session, city, "b1")
    db_session.flush()

    from app.services.crawl_scope import resolve_crawl_scope
    scope = resolve_crawl_scope(db_session, city, {})
    assert scope.keywords == ["A"]
    assert [b.username for b in scope.bloggers] == ["b1"]
