from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import verify_password
from app.models.config import Blogger, City, Keyword
from app.models.duplicate import DuplicateCandidate
from app.models.note import Note, NoteImage
from app.models.task import CrawlTask, TaskLog
from app.models.user import User
from app.services.maintenance import backup_sqlite, cleanup_runtime_files, create_admin


def test_phase_one_models_persist_relationship_data(db_session: Session) -> None:
    city = City(name="上海", code="shanghai")
    db_session.add(city)
    db_session.flush()
    db_session.add_all([Keyword(word="周末活动", city_code=city.code), Blogger(platform_user_id="u1", username="博主", profile_url="https://example.com/u1", city_code=city.code)])
    task = CrawlTask(type="keyword", status="PENDING", params={"city": "shanghai"})
    db_session.add(task)
    db_session.flush()
    note = Note(task_id=task.id, platform_note_id="n1", title="活动", content="正文", source_url="https://example.com/n1", city_code="shanghai", status="DOWNLOADED", raw_data={})
    db_session.add(note)
    db_session.flush()
    db_session.add_all([NoteImage(note_id=note.id, storage_key="n1/1.jpg", ocr_status="pending"), TaskLog(task_id=task.id, level="INFO", message="created")])
    db_session.commit()
    assert db_session.scalar(select(City).where(City.code == "shanghai")) is not None
    assert db_session.scalar(select(NoteImage).where(NoteImage.note_id == note.id)) is not None


def test_create_admin_is_idempotent(db_session: Session) -> None:
    first = create_admin(db_session, "admin", "Admin@123")
    second = create_admin(db_session, "admin", "Changed@123")
    assert first.id == second.id
    assert verify_password("Changed@123", second.password_hash)


def test_backup_and_cleanup_runtime_files(tmp_path: Path) -> None:
    database = tmp_path / "app.db"
    database.write_bytes(b"sqlite")
    backup = backup_sqlite(database, tmp_path / "backups")
    assert backup.read_bytes() == b"sqlite"
    old = tmp_path / "images" / "old.jpg"
    old.parent.mkdir()
    old.write_bytes(b"old")
    removed = cleanup_runtime_files([old.parent], older_than_days=0)
    assert old in removed and not old.exists()
