"""0013_keyword_groups 数据迁移测试。"""
from sqlalchemy.orm import Session

from app.core.database import Base
from app.models.config import City
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
