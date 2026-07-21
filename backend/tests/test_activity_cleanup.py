from datetime import datetime, timezone
from types import SimpleNamespace

from sqlalchemy import func, select

from app.models.activity import Activity
from app.models.duplicate import DuplicateCandidate
from app.models.note import Note, NoteImage
from app.models.task import CrawlTask
from app.services.activity_cleanup import cleanup_activity_dates
from app.services.archive import archive_task_folder


def test_cleanup_removes_window_outliers_and_rebuilds_exports_without_deleting_sources(db_session, tmp_path):
    reference = datetime(2026, 7, 17, tzinfo=timezone.utc)
    task = CrawlTask(type="mixed", status="COMPLETED", params={}, started_at=reference)
    db_session.add(task)
    db_session.flush()
    note = Note(task_id=task.id, platform_note_id="note-clean", title="活动合集", content="正文", source_url="https://xhs/note-clean", city_code="nb", status="PROCESSED", raw_data={})
    db_session.add(note)
    db_session.flush()
    valid = Activity(note_id=note.id, name="有效活动", city_code="nb", start_time=datetime(2026, 7, 20), location="广场", type="其他")
    expired = Activity(note_id=note.id, name="历史活动", city_code="nb", start_time=datetime(2024, 7, 20), location="广场", type="其他")
    db_session.add_all([valid, expired])
    db_session.flush()
    db_session.add(DuplicateCandidate(activity_a_id=valid.id, activity_b_id=expired.id, similarity=0.8, matched_fields=["city"]))
    db_session.add(NoteImage(note_id=note.id, storage_key="archive/source.jpg", original_url="https://image", ocr_status="success"))
    db_session.commit()
    settings = SimpleNamespace(archive_dir=tmp_path / "archive", activity_future_window_days=60, celery_timezone="Asia/Shanghai")
    folder = archive_task_folder(settings.archive_dir, reference, task.id)
    (folder / "source.md").write_text("原始来源证据", encoding="utf-8")
    (folder / "activities.md").write_text("历史活动", encoding="utf-8")
    legacy_folder = settings.archive_dir / "2026-07-16" / f"task-{task.id}"
    legacy_folder.mkdir(parents=True)
    (legacy_folder / "source.md").write_text("旧目录来源证据", encoding="utf-8")
    (legacy_folder / "activities.md").write_text("历史活动", encoding="utf-8")

    summary = cleanup_activity_dates(db_session, settings, reference)

    assert summary.scanned == 2
    assert summary.deleted == 1
    assert summary.retained == 1
    assert summary.task_ids == [task.id]
    assert db_session.get(Activity, expired.id) is None
    assert db_session.get(Note, note.id) is not None
    assert db_session.scalar(select(func.count()).select_from(NoteImage)) == 1
    assert db_session.scalar(select(func.count()).select_from(DuplicateCandidate)) == 0
    assert (folder / "source.md").read_text(encoding="utf-8") == "原始来源证据"
    activities_markdown = (folder / "activities.md").read_text(encoding="utf-8")
    assert "有效活动" in activities_markdown
    assert "历史活动" not in activities_markdown
    assert (folder / "activities.xlsx").is_file()
    assert (legacy_folder / "source.md").read_text(encoding="utf-8") == "旧目录来源证据"
    assert "有效活动" in (legacy_folder / "activities.md").read_text(encoding="utf-8")
    assert "历史活动" not in (legacy_folder / "activities.md").read_text(encoding="utf-8")
    assert (legacy_folder / "activities.xlsx").is_file()

    second = cleanup_activity_dates(db_session, settings, reference)
    assert second.deleted == 0
