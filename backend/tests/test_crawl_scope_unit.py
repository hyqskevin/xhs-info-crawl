"""`resolve_crawl_scope` 单元测试，覆盖关键词组合并、博主多城市、城市默认回退。"""
from sqlalchemy.orm import Session

from app.models.config import Blogger, City
from app.models.blogger_city import BloggerCity
from app.models.keyword_group import (
    KeywordGroup,
    KeywordGroupCity,
    KeywordGroupWord,
)
from app.services.crawl_scope import (
    resolve_crawl_scope,
    resolve_effective_bloggers,
    resolve_effective_keywords,
)


def _seed_city(db: Session, name: str, code: str) -> City:
    city = City(name=name, code=code, enabled=True)
    db.add(city)
    db.commit()
    return city


def _make_group(
    db: Session, *, name: str, city_codes: list[str], words: list[str], enabled: bool = True
) -> int:
    kg = KeywordGroup(name=name, enabled=enabled)
    db.add(kg)
    db.flush()
    for code in dict.fromkeys(city_codes):
        db.add(KeywordGroupCity(keyword_group_id=kg.id, city_code=code, enabled=True))
    for word in dict.fromkeys(words):
        db.add(KeywordGroupWord(keyword_group_id=kg.id, word=word, enabled=enabled))
    db.commit()
    return kg.id


def test_resolve_keywords_uses_groups_when_ids_provided(db_session: Session) -> None:
    city = _seed_city(db_session, "上海", "sh")
    g1 = _make_group(db_session, name="g1", city_codes=["sh"], words=["展览", "艺术展"])
    g2 = _make_group(db_session, name="g2", city_codes=["sh"], words=["咖啡", "展览"])

    words = resolve_effective_keywords(db_session, city, {"keyword_group_ids": [g1, g2]})
    # 并集去重，保持顺序
    assert words == ["展览", "艺术展", "咖啡"]


def test_resolve_keywords_excludes_disabled_group(db_session: Session) -> None:
    city = _seed_city(db_session, "上海", "sh")
    g_disabled = _make_group(
        db_session, name="g-disabled", city_codes=["sh"], words=["不抓"], enabled=False
    )
    g_enabled = _make_group(
        db_session, name="g-enabled", city_codes=["sh"], words=["要抓"]
    )
    words = resolve_effective_keywords(db_session, city, {"keyword_group_ids": [g_disabled, g_enabled]})
    assert "不抓" not in words
    assert "要抓" in words


def test_resolve_keywords_empty_group_ids_returns_empty(db_session: Session) -> None:
    city = _seed_city(db_session, "上海", "sh")
    words = resolve_effective_keywords(db_session, city, {"keyword_group_ids": []})
    # 显式空组列表 = 不选任何组（与显式空 keywords 一致：键存在即表达意图，不回退）
    assert words == []


def test_resolve_keywords_returns_empty_when_no_task_params(db_session: Session) -> None:
    """legacy keywords 表已废弃，无 task_params 时返回空列表。"""
    city = _seed_city(db_session, "上海", "sh")
    words = resolve_effective_keywords(db_session, city, {})
    assert words == []


def test_resolve_keywords_union_of_explicit_and_groups(db_session: Session) -> None:
    city = _seed_city(db_session, "上海", "sh")
    g = _make_group(db_session, name="g", city_codes=["sh"], words=["组内词"])
    words = resolve_effective_keywords(db_session, city, {"keywords": ["显式词"], "keyword_group_ids": [g]})
    # 2026-07-25 语义：显式 keywords 与组并集（都选都抓）
    assert words == ["显式词", "组内词"]


def test_resolve_bloggers_filters_by_city(db_session: Session) -> None:
    a = Blogger(username="a-sh", enabled=True)
    b = Blogger(username="b-bj", enabled=True)
    db_session.add_all([a, b])
    db_session.flush()
    db_session.add_all([
        BloggerCity(blogger_id=a.id, city_code="sh", enabled=True),
        BloggerCity(blogger_id=b.id, city_code="bj", enabled=True),
    ])
    db_session.commit()
    sh_city = _seed_city(db_session, "上海", "sh")

    out = resolve_effective_bloggers(db_session, sh_city, {})
    assert [x.username for x in out] == ["a-sh"]


def test_resolve_bloggers_by_explicit_ids(db_session: Session) -> None:
    a = Blogger(username="a-sh", enabled=True)
    c = Blogger(username="c-other", enabled=True)
    db_session.add_all([a, c])
    db_session.flush()
    db_session.add_all([
        BloggerCity(blogger_id=a.id, city_code="sh", enabled=True),
        BloggerCity(blogger_id=c.id, city_code="sh", enabled=True),
    ])
    db_session.commit()
    sh_city = _seed_city(db_session, "上海", "sh")

    # 仅选择 a
    out = resolve_effective_bloggers(db_session, sh_city, {"blogger_ids": [a.id]})
    assert [x.username for x in out] == ["a-sh"]


def test_resolve_scope_combines(db_session: Session) -> None:
    city = _seed_city(db_session, "上海", "sh")
    b = Blogger(username="b1", enabled=True)
    db_session.add(b)
    db_session.flush()
    db_session.add(BloggerCity(blogger_id=b.id, city_code="sh", enabled=True))
    db_session.commit()

    scope = resolve_crawl_scope(db_session, city, {})
    assert scope.keywords == []  # 没有 legacy 表，也未传 group_ids
    assert [x.username for x in scope.bloggers] == ["b1"]
