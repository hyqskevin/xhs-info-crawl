"""0013_keyword_groups 数据迁移测试。"""
from sqlalchemy.orm import Session

from app.core.database import Base
from app.models.config import City, Keyword
from app.models.keyword_group import KeywordGroup, KeywordGroupCity, KeywordGroupWord


def _seed_city(db: Session, name: str, code: str, enabled: bool = True) -> City:
    city = City(name=name, code=code, enabled=enabled)
    db.add(city)
    db.commit()
    db.refresh(city)
    return city


def test_keyword_group_unique_name(db_session: Session) -> None:
    g1 = KeywordGroup(name="展览")
    g2 = KeywordGroup(name="亲子")
    db_session.add_all([g1, g2])
    db_session.commit()
    assert g1.id != g2.id

    dupe = KeywordGroup(name="展览")
    db_session.add(dupe)
    try:
        db_session.commit()
        assert False, "应该 unique 约束失败"
    except Exception:
        db_session.rollback()


def test_keyword_group_city_many_to_many(db_session: Session) -> None:
    _seed_city(db_session, "宁波", "nb")
    _seed_city(db_session, "上海", "sh")
    g = KeywordGroup(name="展览")
    db_session.add(g)
    db_session.commit()
    db_session.refresh(g)
    db_session.add_all([
        KeywordGroupCity(keyword_group_id=g.id, city_code="nb"),
        KeywordGroupCity(keyword_group_id=g.id, city_code="sh"),
    ])
    db_session.commit()
    cities = db_session.scalars(
        db_session.query(KeywordGroupCity).statement
    ).all()
    assert len(cities) == 2
    codes = {c.city_code for c in cities}
    assert codes == {"nb", "sh"}


def test_keyword_group_word_unique_per_group(db_session: Session) -> None:
    g = KeywordGroup(name="咖啡")
    db_session.add(g)
    db_session.commit()
    db_session.refresh(g)
    db_session.add(KeywordGroupWord(keyword_group_id=g.id, word="咖啡"))
    db_session.commit()
    dupe = KeywordGroupWord(keyword_group_id=g.id, word="咖啡")
    db_session.add(dupe)
    try:
        db_session.commit()
        assert False, "应该 unique 失败"
    except Exception:
        db_session.rollback()


def test_city_name_unique_constraint(db_session: Session) -> None:
    _seed_city(db_session, "宁波", "nb1")
    try:
        _seed_city(db_session, "宁波", "nb2")
        assert False, "应该 unique 失败"
    except Exception:
        db_session.rollback()


def test_keyword_group_inherits_keywords_after_migration_simulation(db_session: Session) -> None:
    """模拟 0013 数据迁移步骤：从 keywords (city_code, word) → (default keyword group per city) + words."""
    nb = _seed_city(db_session, "宁波", "nb")
    db_session.add_all([
        Keyword(word="活动", city_code="nb", enabled=True),
        Keyword(word="展览", city_code="nb", enabled=True),
        Keyword(word="活动", city_code="nb", enabled=True),  # dupe
    ])
    db_session.commit()

    # 模拟 migration 行为
    g = KeywordGroup(name=f"{nb.name}-默认", description="由 0013 migration 从 keywords 历史生成")
    db_session.add(g)
    db_session.commit()
    db_session.refresh(g)
    db_session.add(KeywordGroupCity(keyword_group_id=g.id, city_code="nb"))

    seen = set()
    keywords = db_session.scalars(db_session.query(Keyword).statement).all()
    for k in keywords:
        if k.city_code == "nb" and k.enabled and k.word not in seen:
            seen.add(k.word)
            db_session.add(KeywordGroupWord(keyword_group_id=g.id, word=k.word))
    db_session.commit()

    words = db_session.scalars(
        db_session.query(KeywordGroupWord).statement
    ).all()
    assert {w.word for w in words} == {"活动", "展览"}
