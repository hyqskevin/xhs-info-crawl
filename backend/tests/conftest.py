from collections.abc import Generator
import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

# settings and Celery read environment values while app modules are imported.
# Keep pytest isolated from the developer's JWT secret and filesystem broker.
os.environ["SECRET_KEY"] = "pytest-only-jwt-secret-at-least-32-bytes"
os.environ["CELERY_BROKER_URL"] = "memory://"

from app.core.config import Settings, get_settings
from app.core.database import Base, get_db
from app.main import app


# Build the list of env var names that pydantic_settings may read from
# os.environ, so the autouse fixture below can clear them. Order does not
# matter; missing keys are skipped.
_SETTINGS_ENV_KEYS: list[str] = [
    "APP_NAME",
    "APP_ENV",
    "API_V1_PREFIX",
    "API_HOST",
    "API_PORT",
    "WEB_HOST",
    "WEB_PORT",
    "CORS_ORIGINS",
    "SECRET_KEY",  # back-filled below to keep JWT secret isolated
    "JWT_EXPIRE_HOURS",
    "DATABASE_URL",
    "CELERY_BROKER_URL",  # back-filled below to keep Celery in memory
    "CELERY_TIMEZONE",
    "CELERY_WORKER_POOL",
    "CELERY_WORKER_CONCURRENCY",
    "CELERY_LOG_LEVEL",
    "WEEKLY_CRAWL_DAY_OF_WEEK",
    "WEEKLY_CRAWL_HOUR",
    "WEEKLY_CRAWL_MINUTE",
    "OPENCLI_CDP_ENDPOINT",
    "OPENCLI_BIN",
    "OPENCLI_BROWSER_COMMAND_TIMEOUT",
    "XHS_LOGIN_URL",
    "XHS_LOGIN_BROWSER",
    "SEARCH_INTERVAL_MIN",
    "SEARCH_INTERVAL_MAX",
    "SEARCH_LIMIT",
    "WEEKLY_SEARCH_LIMIT",
    "CONSECUTIVE_NOTE_FAILURE_LIMIT",
    "MINIMAX_API_KEY",
    "MINIMAX_BASE_URL",
    "MINIMAX_MODEL",
    "MINIMAX_VISION_MODEL",
    "MINIMAX_CHAT_PATH",
    "MINIMAX_TIMEOUT_SECONDS",
    "OCR_ENABLED",
    "OCR_LANGUAGE",
    "OCR_MIN_CONFIDENCE",
    "OCR_USE_DOC_ORIENTATION_CLASSIFY",
    "OCR_USE_DOC_UNWARPING",
    "OCR_USE_TEXTLINE_ORIENTATION",
    "PADDLE_PDX_CACHE_HOME",
    "HF_HOME",
    "XHS_SEARCH_TARGET_COUNT",
    "XHS_SEARCH_SCROLL_MAX_ROUNDS",
    "XHS_DETAIL_SCROLL_MAX_ROUNDS",
    "XHS_SCROLL_PIXELS",
    "XHS_SCROLL_STAGNANT_ROUNDS",
    "PIPELINE_STAGE_MAX_RETRIES",
    "PIPELINE_STAGE_RETRY_DELAY_SECONDS",
    "ACTIVITY_FUTURE_WINDOW_DAYS",
    "DATA_DIR",
    "IMAGE_DIR",
    "EXPORT_DIR",
    "ARCHIVE_DIR",
    "CELERY_FOLDER",
    "INITIAL_ADMIN_PASSWORD",
]


@pytest.fixture(autouse=True)
def isolate_settings_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Clear all Settings-env vars from os.environ so tests see the code defaults.

    Without this fixture, an outer shell that runs `set -a && source .env` pollutes
    os.environ with values like OPENCLI_BIN or OPENCLI_BROWSER_COMMAND_TIMEOUT.
    pydantic_settings then reads them instead of the .env file or the code defaults,
    breaking tests that assert default behaviour (e.g. opencli_bin == 'opencli').
    """
    for key in _SETTINGS_ENV_KEYS:
        monkeypatch.delenv(key, raising=False)
    # Reactivate the keys conftest pinned at import time so other fixtures stay green.
    monkeypatch.setenv("SECRET_KEY", "pytest-only-jwt-secret-at-least-32-bytes")
    monkeypatch.setenv("CELERY_BROKER_URL", "memory://")
    # Drop any cached Settings instance so the next get_settings() picks up the
    # cleaned environment.
    get_settings.cache_clear()


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


@pytest.fixture(autouse=True)
def fast_rate_limit_sleep(monkeypatch: pytest.MonkeyPatch) -> None:
    """频率控制的真实 sleep 不进测试；断言 sleep 行为的用例需显式重 patch。"""
    from app.tasks import crawl_task

    monkeypatch.setattr(crawl_task, "rate_limit_sleep", lambda *args, **kwargs: None)


@pytest.fixture(autouse=True)
def fake_opencli_resolution(monkeypatch: pytest.MonkeyPatch) -> None:
    """run_crawl 的 opencli 预检默认通过；失败用例需显式重 patch find_opencli。"""
    from app.tasks import crawl_task

    monkeypatch.setattr(crawl_task, "find_opencli", lambda bin_name: f"/fake/{bin_name}")


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
