from datetime import datetime, timezone
import pytest
from sqlalchemy.orm import Session

from app.models.activity import Activity
from app.models.config import City


def make_activity(city_code: str) -> Activity:
    return Activity(
        name=f"活动-{city_code}",
        city_code=city_code,
        start_time=datetime(2026, 7, 20, 18, tzinfo=timezone.utc),
        location="某地",
        price="免费",
        type="演出",
        source_url=f"https://example.com/{city_code}",
        summary="简介",
    )


def test_migrate_updates_chinese_name_to_city_code(db_session: Session):
    """脏数据：city_code 存了中文 '上海'，应改为 cities.code 'city-99f1e469'"""
    shanghai = City(name="上海", code="city-99f1e469", enabled=True)
    db_session.add(shanghai)
    db_session.flush()
    activity = make_activity("上海")
    db_session.add(activity)
    db_session.commit()

    from scripts.migrations.fix_activity_city_code import run_migration
    fixed = run_migration(db_session)

    db_session.refresh(activity)
    assert activity.city_code == "city-99f1e469"
    assert fixed == 1


def test_migrate_leaves_valid_code_unchanged(db_session: Session):
    """已经是 code 的活动不应被改动"""
    nb = City(name="宁波", code="nb", enabled=True)
    db_session.add(nb)
    db_session.flush()
    activity = make_activity("nb")
    db_session.add(activity)
    db_session.commit()

    from scripts.migrations.fix_activity_city_code import run_migration
    fixed = run_migration(db_session)

    db_session.refresh(activity)
    assert activity.city_code == "nb"
    assert fixed == 0


def test_migration_is_idempotent(db_session: Session):
    """重复跑不应重复修正"""
    shanghai = City(name="上海", code="city-99f1e469", enabled=True)
    db_session.add(shanghai)
    db_session.flush()
    activity = make_activity("上海")
    db_session.add(activity)
    db_session.commit()

    from scripts.migrations.fix_activity_city_code import run_migration
    first = run_migration(db_session)
    second = run_migration(db_session)

    db_session.refresh(activity)
    assert activity.city_code == "city-99f1e469"
    assert first == 1
    assert second == 0