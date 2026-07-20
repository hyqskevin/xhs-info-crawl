"""一次性迁移脚本：把 Blogger.city_code 拆分到 BloggerCity 多对多表。

脚本同时负责：
1. 创建 blogger_cities 表（如果不存在）
2. 把现有 Blogger.city_code 不为空的数据搬到 blogger_cities
"""

from sqlalchemy.orm import Session

from app.models.blogger_city import BloggerCity
from app.models.config import Blogger, City


def test_migrate_creates_blogger_cities_from_existing_bloggers(db_session: Session):
    city = City(name="宁波", code="nb", enabled=True)
    db_session.add(city)
    blogger = Blogger(
        username="nb_blogger",
        profile_url="https://xhs/u/nb",
        city_code="nb",
        enabled=True,
        platform_user_id="nb_id",
    )
    db_session.add(blogger)
    db_session.commit()

    from scripts.migrations.split_blogger_cities import run_migration
    run_migration(db_session)

    rows = db_session.query(BloggerCity).all()
    assert len(rows) == 1
    assert rows[0].blogger_id == blogger.id
    assert rows[0].city_code == "nb"
    assert rows[0].enabled is True


def test_migrate_skips_bloggers_with_empty_city_code(db_session: Session):
    db_session.add(Blogger(
        username="orphan",
        profile_url="https://xhs/u/orphan",
        city_code="",
        enabled=True,
        platform_user_id="orphan_id",
    ))
    db_session.commit()

    from scripts.migrations.split_blogger_cities import run_migration
    run_migration(db_session)

    assert db_session.query(BloggerCity).count() == 0


def test_migration_is_idempotent(db_session: Session):
    db_session.add(City(name="宁波", code="nb", enabled=True))
    blogger = Blogger(
        username="nb2",
        profile_url="https://xhs/u/nb2",
        city_code="nb",
        enabled=True,
        platform_user_id="nb2_id",
    )
    db_session.add(blogger)
    db_session.commit()

    from scripts.migrations.split_blogger_cities import run_migration
    run_migration(db_session)
    run_migration(db_session)  # 第二次应不重复创建

    assert db_session.query(BloggerCity).count() == 1