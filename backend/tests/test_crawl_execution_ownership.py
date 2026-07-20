from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.security import create_access_token
from app.models.config import City, Keyword
from app.models.note import Note
from app.models.task import CrawlTask
from app.core.config import Settings
from app.tasks import crawl_task


def _auth() -> dict[str, str]:
    token = create_access_token({"sub": "admin", "role": "admin"})
    return {"Authorization": f"Bearer {token}"}


def _configured_city(db: Session) -> None:
    db.add(City(name="宁波", code="nb", enabled=True))
    db.add(Keyword(word="活动", city_code="nb", enabled=True))
    db.commit()


def test_crawl_dispatches_task_with_persisted_run_token(
    client: TestClient,
    db_session: Session,
    celery_dispatches: list[tuple],
) -> None:
    _configured_city(db_session)

    response = client.post(
        "/api/v1/tasks/crawl",
        json={"city": "nb", "keywords": ["活动"], "blogger_ids": []},
        headers=_auth(),
    )

    assert response.status_code == 202
    task = db_session.get(CrawlTask, response.json()["data"]["id"])
    assert task.run_token
    assert celery_dispatches == [(task.id, task.run_token, {})]


def test_restart_rotates_run_token(
    client: TestClient,
    db_session: Session,
    celery_dispatches: list[tuple],
) -> None:
    _configured_city(db_session)
    task = CrawlTask(
        type="mixed",
        status="STOPPED",
        run_token="old-token",
        params={"city": "nb", "keywords": ["活动"], "blogger_ids": []},
    )
    db_session.add(task)
    db_session.commit()
    task_id = task.id

    response = client.post(f"/api/v1/tasks/{task.id}/restart", headers=_auth())

    assert response.status_code == 202
    db_session.refresh(task)
    assert task.run_token != "old-token"
    assert celery_dispatches == [(task.id, task.run_token, {})]


def test_stale_run_token_cannot_execute_task(db_session: Session, monkeypatch) -> None:
    task = CrawlTask(
        type="mixed",
        status="PENDING",
        run_token="current-token",
        params={"city": "nb", "keywords": ["活动"], "blogger_ids": []},
    )
    db_session.add(task)
    db_session.commit()
    task_id = task.id
    adapter_created = []

    monkeypatch.setattr(crawl_task, "SessionLocal", lambda: db_session)
    monkeypatch.setattr(crawl_task, "OpenCLIAdapter", lambda _settings: adapter_created.append(True))

    crawl_task.run_crawl.run(task_id, "stale-token")

    task = db_session.get(CrawlTask, task_id)
    assert task.status == "PENDING"
    assert adapter_created == []


def test_completed_task_cannot_be_reclaimed(db_session: Session, monkeypatch) -> None:
    task = CrawlTask(
        type="mixed",
        status="COMPLETED",
        run_token="completed-token",
        params={"city": "nb", "keywords": ["活动"], "blogger_ids": []},
    )
    db_session.add(task)
    db_session.commit()
    task_id = task.id
    run_token = task.run_token
    adapter_created = []

    monkeypatch.setattr(crawl_task, "SessionLocal", lambda: db_session)
    monkeypatch.setattr(crawl_task, "OpenCLIAdapter", lambda _settings: adapter_created.append(True))

    crawl_task.run_crawl.run(task_id, run_token)

    task = db_session.get(CrawlTask, task_id)
    assert task.status == "COMPLETED"
    assert adapter_created == []


def test_stop_requested_after_note_detail_prevents_download_and_note_write(
    db_session: Session,
    monkeypatch,
    tmp_path,
) -> None:
    _configured_city(db_session)
    task = CrawlTask(
        type="mixed",
        status="PENDING",
        run_token="stop-token",
        params={"city": "nb", "keywords": ["活动"], "blogger_ids": []},
    )
    db_session.add(task)
    db_session.commit()
    task_id = task.id
    download_calls = []

    class FakeAdapter:
        def __init__(self, _settings):
            pass

        def bind_task(self, *_args):
            pass

        def search_recent(self, *_args):
            return [{"title": "宁波活动", "url": "https://www.xiaohongshu.com/explore/note-1"}]

        def note(self, _url):
            current = db_session.get(CrawlTask, task_id)
            current.status = "STOP_REQUESTED"
            db_session.commit()
            return {"content": "正文"}

        def download(self, *_args):
            download_calls.append(True)
            return []

    settings = Settings(
        DATA_DIR=tmp_path / "data",
        IMAGE_DIR=tmp_path / "images",
        EXPORT_DIR=tmp_path / "exports",
        ARCHIVE_DIR=tmp_path / "archive",
        CELERY_FOLDER=tmp_path / "celery",
        ocr_enabled=False,
        minimax_api_key="",
    )
    monkeypatch.setattr(crawl_task, "SessionLocal", lambda: db_session)
    monkeypatch.setattr(crawl_task, "OpenCLIAdapter", FakeAdapter)
    monkeypatch.setattr(crawl_task, "get_settings", lambda: settings)

    crawl_task.run_crawl.run(task_id, "stop-token")

    task = db_session.get(CrawlTask, task_id)
    assert task.status == "STOPPED"
    assert download_calls == []
    assert db_session.query(Note).count() == 0
