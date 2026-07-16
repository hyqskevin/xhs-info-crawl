import os
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_required_local_scripts_exist_and_are_executable() -> None:
    for name in ("init.sh", "dev-api.sh", "dev-worker.sh", "dev-beat.sh", "dev-web.sh"):
        script = PROJECT_ROOT / "scripts" / name
        assert script.is_file(), f"missing {script}"
        assert os.access(script, os.X_OK), f"not executable: {script}"


def test_environment_example_contains_phase_one_settings() -> None:
    content = (PROJECT_ROOT / ".env.example").read_text(encoding="utf-8")

    for key in (
        "DATABASE_URL=sqlite:///./data/app.db",
        "CELERY_BROKER_URL=filesystem://",
        "OPENCLI_CDP_ENDPOINT=http://localhost:9222",
    ):
        assert key in content


def test_scaffold_contains_frontend_backend_and_runtime_placeholder() -> None:
    assert (PROJECT_ROOT / "frontend" / "package.json").is_file()
    assert (PROJECT_ROOT / "backend" / "pyproject.toml").is_file()
    assert (PROJECT_ROOT / "data" / ".gitkeep").is_file()
