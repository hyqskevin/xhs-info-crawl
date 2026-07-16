from pathlib import Path

from app.core.config import Settings
from app.core.database import init_database


def test_init_database_creates_sqlite_file(tmp_path: Path) -> None:
    settings = Settings(project_root=tmp_path)

    init_database(settings)

    assert settings.sqlite_path.is_file()
