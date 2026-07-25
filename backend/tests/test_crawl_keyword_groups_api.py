"""关键词组经 /tasks/crawl 端到端链路 + 归档按城市/周分目录测试。

关联 spec: docs/superpowers/specs/2026-07-25-crawl-scope-and-archive-layout-design.md

语义（用户 2026-07-25 确认）：
- 只选城市+关键词组 → 只抓关键词；
- 只选博主 → 只抓博主；
- 都选 → 都抓；
- city 与 recent_filter 必填；
- 归档目录为 archive/{city_code}/{ISO 年-W 周}/task-{id}/。
"""
from datetime import datetime, timezone

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.security import create_access_token
from app.models.config import City
from app.models.keyword_group import KeywordGroup, KeywordGroupCity, KeywordGroupWord
from app.services.archive import archive_task_folder
from app.services.crawl_scope import resolve_effective_keywords


def _auth() -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token({'sub': 'admin', 'role': 'admin'})}"}


def _seed_city_with_group(db: Session) -> tuple[City, KeywordGroup]:
    city = City(name="宁波", code="city-nb01", enabled=True)
    group = KeywordGroup(name="展览", enabled=True)
    db.add_all([city, group])
    db.commit()
    db.refresh(group)
    db.add(KeywordGroupCity(keyword_group_id=group.id, city_code=city.code, enabled=True))
    db.add_all([
        KeywordGroupWord(keyword_group_id=group.id, word="展览", enabled=True),
        KeywordGroupWord(keyword_group_id=group.id, word="活动", enabled=True),
    ])
    db.commit()
    return city, group


def test_crawl_accepts_only_keyword_groups(client: TestClient, db_session: Session, celery_dispatches: list[tuple]) -> None:
    city, group = _seed_city_with_group(db_session)
    response = client.post(
        "/api/v1/tasks/crawl",
        json={"type": "mixed", "city": city.code, "keyword_group_ids": [group.id], "recent_filter": "一周内", "blogger_ids": []},
        headers=_auth(),
    )
    assert response.status_code == 202, response.text
    data = response.json()["data"]
    assert data["params"]["keyword_group_ids"] == [group.id]
    assert celery_dispatches == [(data["id"], data["run_token"], {})]


def test_crawl_group_not_attached_to_city_422(client: TestClient, db_session: Session) -> None:
    city, group = _seed_city_with_group(db_session)
    other = City(name="上海", code="city-sh01", enabled=True)
    db_session.add(other)
    db_session.commit()
    response = client.post(
        "/api/v1/tasks/crawl",
        json={"type": "mixed", "city": other.code, "keyword_group_ids": [group.id], "recent_filter": "一周内", "blogger_ids": []},
        headers=_auth(),
    )
    assert response.status_code == 422
    assert "关键词组" in response.text


def test_crawl_group_missing_or_disabled_422(client: TestClient, db_session: Session) -> None:
    city, group = _seed_city_with_group(db_session)
    missing = client.post(
        "/api/v1/tasks/crawl",
        json={"type": "mixed", "city": city.code, "keyword_group_ids": [99999], "recent_filter": "一周内", "blogger_ids": []},
        headers=_auth(),
    )
    assert missing.status_code == 422
    group.enabled = False
    db_session.commit()
    disabled = client.post(
        "/api/v1/tasks/crawl",
        json={"type": "mixed", "city": city.code, "keyword_group_ids": [group.id], "recent_filter": "一周内", "blogger_ids": []},
        headers=_auth(),
    )
    assert disabled.status_code == 422


def test_crawl_requires_recent_filter(client: TestClient, db_session: Session) -> None:
    city, group = _seed_city_with_group(db_session)
    response = client.post(
        "/api/v1/tasks/crawl",
        json={"type": "mixed", "city": city.code, "keyword_group_ids": [group.id], "blogger_ids": []},
        headers=_auth(),
    )
    assert response.status_code == 422


def test_resolve_keywords_union_of_explicit_and_groups(db_session: Session) -> None:
    city, group = _seed_city_with_group(db_session)
    words = resolve_effective_keywords(db_session, city, {"keywords": ["咖啡"], "keyword_group_ids": [group.id]})
    assert set(words) == {"咖啡", "展览", "活动"}
    assert len(words) == 3


def test_resolve_keywords_groups_only(db_session: Session) -> None:
    city, group = _seed_city_with_group(db_session)
    words = resolve_effective_keywords(db_session, city, {"keywords": [], "keyword_group_ids": [group.id]})
    assert set(words) == {"展览", "活动"}


def test_archive_folder_uses_city_and_iso_week(tmp_path) -> None:
    started = datetime(2026, 7, 20, 12, 0, tzinfo=timezone.utc)  # ISO 2026-W30
    folder = archive_task_folder(tmp_path, started, 9, "shanghai")
    assert folder == tmp_path / "shanghai" / "2026-W30" / "task-9"
    assert (folder / "images").is_dir()


def test_archive_result_writes_city_week_layout_and_storage_key(db_session: Session, tmp_path) -> None:
    from app.models.activity import Activity
    from app.models.note import Note, NoteImage
    from app.services.archive import archive_task_result

    note = Note(task_id=9, platform_note_id="note-1", title="标题", content="正文", source_url="https://x/1", city_code="shanghai", status="DOWNLOADED")
    db_session.add(note)
    db_session.flush()
    image = NoteImage(note_id=note.id, storage_key="", ocr_text="文字", ocr_status="success")
    activity = Activity(note_id=note.id, name="活动A", city_code="shanghai", type="展览", source_url="https://x/1")
    db_session.add_all([image, activity])
    db_session.commit()
    image_file = tmp_path / "src.jpg"
    image_file.write_bytes(b"\xff\xd8\xff")
    started = datetime(2026, 7, 20, 12, 0, tzinfo=timezone.utc)

    folder = archive_task_result(tmp_path / "archive", started, 9, note, [(image_file, image)], [activity], "shanghai")

    assert folder == tmp_path / "archive" / "shanghai" / "2026-W30" / "task-9"
    assert image.storage_key.startswith("archive/shanghai/2026-W30/task-9/images/")
    assert (tmp_path / "archive" / "shanghai" / "2026-W30" / "task-9" / "activities.md").is_file()
