"""配置与迁移盲区（spec: 2026-07-27-config-and-migration-blindspots-design.md）。

- init_database 裸跑（不经 app.main）必须建全表；
- .env.example 必须覆盖 INITIAL_ADMIN_PASSWORD 与 MINIMAX_VISION_MODEL；
- alembic upgrade head 对空库建全表（回归验证）。
"""
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
PROJECT_ROOT = BACKEND_DIR.parent

EXPECTED_TABLES = {
    "activities",
    "blogger_cities",
    "blogger_group_members",
    "blogger_groups",
    "bloggers",
    "cities",
    "crawl_tasks",
    "duplicate_candidates",
    "keyword_group_cities",
    "keyword_group_words",
    "keyword_groups",
    "keywords",
    "note_duplicate_candidates",
    "note_images",
    "notes",
    "poster_tasks",
    "poster_templates",
    "scheduled_crawls",
    "search_usage",
    "task_logs",
    "users",
    "weekly_reports",
}


def _run_backend_python(code: str, env_extra: dict | None = None) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env["SECRET_KEY"] = "pytest-only-jwt-secret-at-least-32-bytes"
    env["CELERY_BROKER_URL"] = "memory://"
    if env_extra:
        env.update(env_extra)
    return subprocess.run(
        [sys.executable, "-c", code],
        cwd=BACKEND_DIR,
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )


def _tables(db_path: Path) -> set[str]:
    conn = sqlite3.connect(db_path)
    try:
        return {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    finally:
        conn.close()


def test_init_database_bare_process_creates_all_tables(tmp_path: Path) -> None:
    """只 import init_database（不经过 app.main 路由链）也必须建出全表。"""
    code = (
        "from pathlib import Path;"
        "from app.core.config import Settings;"
        "from app.core.database import init_database;"
        f"init_database(Settings(project_root=Path(r'{tmp_path}')))"
    )
    result = _run_backend_python(code)
    assert result.returncode == 0, result.stderr
    db_path = tmp_path / "data" / "app.db"
    missing = EXPECTED_TABLES - _tables(db_path)
    assert not missing, f"init_database 缺表: {sorted(missing)}"


def test_env_example_covers_seed_admin_and_vision_model() -> None:
    text = (PROJECT_ROOT / ".env.example").read_text(encoding="utf-8")
    assert "INITIAL_ADMIN_PASSWORD" in text
    assert "MINIMAX_VISION_MODEL" in text


def test_alembic_upgrade_head_builds_all_tables(tmp_path: Path) -> None:
    """空库仅按 alembic upgrade head 即可完整建库（回归验证）。"""
    db_path = tmp_path / "alembic-test.db"
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=BACKEND_DIR,
        env={
            **dict(os.environ),
            "SECRET_KEY": "pytest-only-jwt-secret-at-least-32-bytes",
            "DATABASE_URL": f"sqlite:///{db_path}",
        },
        capture_output=True,
        text=True,
        timeout=180,
    )
    assert result.returncode == 0, result.stderr
    missing = EXPECTED_TABLES - _tables(db_path)
    assert not missing, f"alembic upgrade head 缺表: {sorted(missing)}"
