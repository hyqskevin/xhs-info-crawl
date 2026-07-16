from pathlib import Path

from app.core.config import Settings


def test_runtime_paths_are_derived_from_project_root(tmp_path: Path) -> None:
    settings = Settings(project_root=tmp_path)

    assert settings.sqlite_path == tmp_path / "data" / "app.db"
    assert settings.image_dir == tmp_path / "data" / "images"
    assert settings.export_dir == tmp_path / "data" / "exports"
    assert settings.celery_folder == tmp_path / "data" / "celery"


def test_ensure_runtime_directories_creates_required_folders(tmp_path: Path) -> None:
    settings = Settings(project_root=tmp_path)

    settings.ensure_runtime_directories()

    assert settings.sqlite_path.parent.is_dir()
    assert settings.image_dir.is_dir()
    assert settings.export_dir.is_dir()
    assert (settings.celery_folder / "in").is_dir()
    assert (settings.celery_folder / "out").is_dir()
    assert (settings.celery_folder / "processed").is_dir()
