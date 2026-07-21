"""crawl_scope 解析 keyword_group_ids 测试。

旧字段 task_params['keywords'] 保留：若存在则用任务参数。
新字段 task_params['keyword_group_ids']：返回所属组并集内的关键词。
"""
from sqlalchemy.orm import Session

from app.models.config import City
from app.models.keyword_group import KeywordGroup, KeywordGroupCity, KeywordGroupWord
from app.services.crawl_scope import resolve_crawl_scope


def _seed_city(db: Session, name: str, code: str) -> City:
    city = City(name=name, code=code, enabled=True)
    db.add(city)
    db.commit()
    db.refresh(city)
    return city


def test_legacy_keywords_param_overrides_groups(db_session: Session) -> None:
    nb = _seed_city(db_session, "宁波", "nb")
    g = KeywordGroup(name="展览")
    db_session.add(g)
    db_session.commit()
    db_session.refresh(g)
    db_session.add(KeywordGroupCity(keyword_group_id=g.id, city_code=nb.code))
    db_session.add_all([
        KeywordGroupWord(keyword_group_id=g.id, word="展览"),
        KeywordGroupWord(keyword_group_id=g.id, word="活动"),
    ])
    db_session.commit()

    scope = resolve_crawl_scope(db_session, nb, {"keywords": ["legacy-keyword"]})
    assert scope.keywords == ["legacy-keyword"]


def test_single_group_expansion(db_session: Session) -> None:
    nb = _seed_city(db_session, "宁波", "nb")
    g = KeywordGroup(name="展览")
    db_session.add(g)
    db_session.commit()
    db_session.refresh(g)
    db_session.add(KeywordGroupCity(keyword_group_id=g.id, city_code=nb.code))
    db_session.add_all([
        KeywordGroupWord(keyword_group_id=g.id, word="展览"),
        KeywordGroupWord(keyword_group_id=g.id, word="活动"),
    ])
    db_session.commit()

    scope = resolve_crawl_scope(db_session, nb, {"keyword_group_ids": [g.id]})
    assert set(scope.keywords) == {"活动", "展览"}


def test_multi_group_union(db_session: Session) -> None:
    nb = _seed_city(db_session, "宁波", "nb")
    g1 = KeywordGroup(name="展览")
    g2 = KeywordGroup(name="咖啡")
    db_session.add_all([g1, g2])
    db_session.commit()
    for g in (g1, g2):
        db_session.refresh(g)
        db_session.add(KeywordGroupCity(keyword_group_id=g.id, city_code=nb.code))
    db_session.add_all([
        KeywordGroupWord(keyword_group_id=g1.id, word="展览"),
        KeywordGroupWord(keyword_group_id=g1.id, word="活动"),
        KeywordGroupWord(keyword_group_id=g2.id, word="咖啡"),
        KeywordGroupWord(keyword_group_id=g2.id, word="活动"),  # 并集去重不应有重复
    ])
    db_session.commit()

    scope = resolve_crawl_scope(db_session, nb, {"keyword_group_ids": [g1.id, g2.id]})
    assert set(scope.keywords) == {"展览", "活动", "咖啡"}
    assert len(scope.keywords) == 3


def test_groups_must_be_under_city(db_session: Session) -> None:
    nb = _seed_city(db_session, "宁波", "nb")
    sh = _seed_city(db_session, "上海", "sh")
    g = KeywordGroup(name="只挂上海")
    db_session.add(g)
    db_session.commit()
    db_session.refresh(g)
    db_session.add(KeywordGroupCity(keyword_group_id=g.id, city_code=sh.code))
    db_session.add(KeywordGroupWord(keyword_group_id=g.id, word="expo"))
    db_session.commit()

    # nb 城市下请求 g.id → 不应命中
    scope = resolve_crawl_scope(db_session, nb, {"keyword_group_ids": [g.id]})
    assert scope.keywords == []
