from collections.abc import Generator
import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

# Settings and Celery read environment values while app modules are imported.
# Keep pytest isolated from the developer's JWT secret and filesystem broker.
os.environ["SECRET_KEY"] = "pytest-only-jwt-secret-at-least-32-bytes"
os.environ["CELERY_BROKER_URL"] = "memory://"

from app.core.database import Base, get_db
from app.main import app


@pytest.fixture(autouse=True)
def forbid_undeclared_celery_dispatch(monkeypatch: pytest.MonkeyPatch) -> None:
    """Every test that expects a crawl dispatch must declare and assert it."""
    from app.tasks.crawl_task import run_crawl

    def fail(task_id: int, *args, **kwargs) -> None:
        raise AssertionError(
            f"undeclared Celery dispatch for task_id={task_id}; "
            "patch run_crawl.delay explicitly in this test"
        )

    monkeypatch.setattr(run_crawl, "delay", fail)


@pytest.fixture
def celery_dispatches(monkeypatch: pytest.MonkeyPatch) -> list[tuple]:
    """Opt a test into crawl dispatch and expose the exact queued arguments."""
    from app.tasks.crawl_task import run_crawl

    queued: list[tuple] = []
    monkeypatch.setattr(run_crawl, "delay", lambda *args, **kwargs: queued.append((*args, kwargs)))
    return queued


@pytest.fixture
def db_session(tmp_path: Path) -> Generator[Session, None, None]:
    engine = create_engine(
        f"sqlite:///{tmp_path / 'test.db'}",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    session = factory()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(engine)
        engine.dispose()


@pytest.fixture
def client(db_session: Session) -> Generator[TestClient, None, None]:
    def override_get_db() -> Generator[Session, None, None]:
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
