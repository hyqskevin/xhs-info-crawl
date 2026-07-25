from pathlib import Path

from celery.schedules import crontab

from app.core.config import Settings
from app.tasks.celery_app import create_celery_app


def test_celery_uses_filesystem_transport_and_local_folders(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("CELERY_BROKER_URL", raising=False)
    settings = Settings(project_root=tmp_path, celery_broker_url="filesystem://")

    celery_app = create_celery_app(settings)

    assert celery_app.conf.broker_url == "filesystem://"
    options = celery_app.conf.broker_transport_options
    assert Path(options["data_folder_in"]) == settings.celery_folder / "queue"
    assert Path(options["data_folder_out"]) == settings.celery_folder / "queue"
    assert Path(options["data_folder_processed"]) == settings.celery_folder / "processed"


def test_scheduled_dispatch_runs_every_minute(tmp_path: Path) -> None:
    celery_app = create_celery_app(Settings(project_root=tmp_path))

    entry = celery_app.conf.beat_schedule["scheduled-crawl-dispatch"]

    assert entry["task"] == "app.tasks.crawl_task.scheduled_dispatch"
    assert entry["schedule"] == crontab(minute="*")
    assert celery_app.conf.timezone == "Asia/Shanghai"
