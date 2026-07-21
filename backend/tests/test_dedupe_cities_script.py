"""城市去重脚本：`scripts/dedupe_cities.py` 单元测试。

启动脚本不依赖实际进程：直接 import 函数并调。
"""
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import engine
from app.models.blogger_city import BloggerCity
from app.models.config import Blogger, City, Keyword
from app.models.note import Note
from app.models.task import CrawlTask
from app.scripts.dedupe_cities import dedupe_cities


def _make_city(db: Session, name: str, code: str, enabled: bool = True) -> City:
    city = City(name=name, code=code, enabled=enabled)
    db.add(city)
    db.commit()
    db.refresh(city)
    return city


def _make_note(db: Session, city_code: str, platform_note_id: str) -> Note:
    note = Note(
        task_id=0,
        platform_note_id=platform_note_id,
        title="t",
        content="c",
        source_url=f"https://xhs.demo/{platform_note_id}",
        city_code=city_code,
        status="PROCESSED",
        review_status="PENDING",
        raw_data={},
    )
    db.add(note)
    db.commit()
    return note


def test_dedupe_keeps_oldest_enabled_city(db_session: Session) -> None:
    older = _make_city(db_session, "宁波", "nb", enabled=True)
    newer = _make_city(db_session, "宁波", "nbo", enabled=True)

    summary = dedupe_cities(db_session)

    remaining = db_session.scalars(db_session.query(City).statement).all()
    names = [city.name for city in remaining]
    assert "宁波" in names
    assert summary["groups_merged"] == 1
    # 保留更早 (id 最小)
    kept = next(c for c in remaining if c.name == "宁波")
    assert kept.id == older.id
    # 另一个删除
    assert newer.id not in [c.id for c in remaining]


def test_dedupe_prefers_enabled_over_older_disabled(db_session: Session) -> None:
    older_disabled = _make_city(db_session, "宁波", "nb-old", enabled=False)
    newer_enabled = _make_city(db_session, "宁波", "nb-new", enabled=True)

    dedupe_cities(db_session)

    remaining = db_session.scalars(db_session.query(City).statement).all()
    kept = next(c for c in remaining if c.name == "宁波")
    assert kept.id == newer_enabled.id
    assert older_disabled.id not in [c.id for c in remaining]


def test_dedupe_migrates_notes_and_blogger_city(db_session: Session) -> None:
    canonical = _make_city(db_session, "上海", "sh", enabled=True)
    dup = _make_city(db_session, "上海", "sh-dup", enabled=True)
    note_a = _make_note(db_session, city_code=dup.code, platform_note_id="note-aaa")
    note_b = _make_note(db_session, city_code=dup.code, platform_note_id="note-bbb")
    blogger = Blogger(username="博主甲", profile_url="https://xhs.demo/u", enabled=True, city_code=None)
    db_session.add(blogger)
    db_session.commit()
    db_session.refresh(blogger)
    # dup 上挂一个 blogger_city
    db_session.add(BloggerCity(blogger_id=blogger.id, city_code=dup.code, enabled=True))
    db_session.commit()

    dedupe_cities(db_session)

    for note in (note_a, note_b):
        db_session.refresh(note)
        assert note.city_code == canonical.code
    # dup 上的 BloggerCity 应被迁到 canonical
    bc_rows = db_session.scalars(db_session.query(BloggerCity).statement).all()
    assert all(bc.city_code == canonical.code for bc in bc_rows)


def test_dedupe_rewrites_crawl_task_json_params(db_session: Session) -> None:
    canonical = _make_city(db_session, "深圳", "sz", enabled=True)
    dup = _make_city(db_session, "深圳", "sz-dup", enabled=True)
    task = CrawlTask(type="mixed", status="STOPPED", params={"city": dup.code, "keywords": [], "blogger_ids": []})
    db_session.add(task)
    db_session.commit()

    dedupe_cities(db_session)

    db_session.refresh(task)
    assert task.params["city"] == canonical.code


def test_dedupe_is_idempotent(db_session: Session) -> None:
    _make_city(db_session, "杭州", "hz", enabled=True)
    _make_city(db_session, "杭州", "hz-dup", enabled=True)

    first = dedupe_cities(db_session)
    second = dedupe_cities(db_session)

    assert first["groups_merged"] == 1
    assert second["groups_merged"] == 0


def test_dedupe_no_op_when_all_unique(db_session: Session) -> None:
    _make_city(db_session, "宁波", "nb", enabled=True)
    _make_city(db_session, "上海", "sh", enabled=True)

    summary = dedupe_cities(db_session)

    assert summary["groups_merged"] == 0
    remaining = db_session.scalars(db_session.query(City).statement).all()
    assert len(remaining) == 2


def test_dedupe_does_not_touch_distinct_names(db_session: Session) -> None:
    _make_city(db_session, "宁波", "nb", enabled=True)
    _make_city(db_session, "上海", "sh", enabled=True)
    _make_city(db_session, "深圳", "sz", enabled=True)
    _make_city(db_session, "杭州", "hz", enabled=True)

    dedupe_cities(db_session)

    names = sorted(c.name for c in db_session.scalars(db_session.query(City).statement).all())
    assert names == ["上海", "宁波", "杭州", "深圳"]
