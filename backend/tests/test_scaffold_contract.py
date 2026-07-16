import os
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_required_local_scripts_exist_and_are_executable() -> None:
    for name in ("init.sh", "dev-api.sh", "dev-worker.sh", "dev-beat.sh", "dev-web.sh", "test-opencli.sh"):
        script = PROJECT_ROOT / "scripts" / name
        assert script.is_file(), f"missing {script}"
        assert os.access(script, os.X_OK), f"not executable: {script}"


def test_environment_example_contains_phase_one_settings() -> None:
    content = (PROJECT_ROOT / ".env.example").read_text(encoding="utf-8")

    for key in (
        "APP_NAME=",
        "API_V1_PREFIX=/api/v1",
        "API_HOST=127.0.0.1",
        "API_PORT=8000",
        "WEB_HOST=127.0.0.1",
        "WEB_PORT=5173",
        "CORS_ORIGINS=",
        "DATABASE_URL=sqlite:///./data/app.db",
        "CELERY_BROKER_URL=filesystem://",
        "CELERY_TIMEZONE=Asia/Shanghai",
        "CELERY_WORKER_POOL=solo",
        "CELERY_WORKER_CONCURRENCY=1",
        "CELERY_LOG_LEVEL=INFO",
        "WEEKLY_CRAWL_DAY_OF_WEEK=1",
        "WEEKLY_CRAWL_HOUR=2",
        "WEEKLY_CRAWL_MINUTE=0",
        "DATA_DIR=./data",
        "IMAGE_DIR=./data/images",
        "EXPORT_DIR=./data/exports",
        "CELERY_FOLDER=./data/celery",
        "OPENCLI_CDP_ENDPOINT=http://localhost:9222",
        "VITE_API_BASE_URL=/api/v1",
        "VITE_API_TIMEOUT_MS=10000",
        "MINIMAX_BASE_URL=https://api.minimaxi.com/v1",
        "MINIMAX_MODEL=MiniMax-M2.7",
        "MINIMAX_CHAT_PATH=/text/chatcompletion_v2",
        "OCR_ENABLED=false",
        "OCR_LANGUAGE=ch",
        "OCR_MIN_CONFIDENCE=0.5",
        "PADDLEOCR_MODEL_DIR=./data/models/paddleocr",
    ):
        assert key in content


def test_runtime_scripts_load_root_environment_file() -> None:
    for name in ("dev-api.sh", "dev-worker.sh", "dev-beat.sh", "dev-web.sh"):
        content = (PROJECT_ROOT / "scripts" / name).read_text(encoding="utf-8")
        assert "set -a" in content
        assert 'source "$ROOT_DIR/.env"' in content


def test_init_script_merges_new_example_variables_without_overwriting_env() -> None:
    content = (PROJECT_ROOT / "scripts" / "init.sh").read_text(encoding="utf-8")

    assert 'done < .env.example' in content
    assert 'if ! grep -q "^${key}=" .env' in content


def test_opencli_script_checks_login_before_search() -> None:
    content = (PROJECT_ROOT / "scripts" / "test-opencli.sh").read_text(encoding="utf-8")
    assert content.index("opencli xiaohongshu whoami") < content.index("opencli xiaohongshu search")
    assert "exit 77" in content


def test_scaffold_contains_frontend_backend_and_runtime_placeholder() -> None:
    assert (PROJECT_ROOT / "frontend" / "package.json").is_file()
    assert (PROJECT_ROOT / "backend" / "pyproject.toml").is_file()
    assert (PROJECT_ROOT / "data" / ".gitkeep").is_file()
