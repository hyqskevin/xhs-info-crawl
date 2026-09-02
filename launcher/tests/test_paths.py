"""launcher/paths.py 路径解析单元测试。"""

from pathlib import Path

import pytest

from launcher import paths


def test_resolve_data_dir_fallback_to_project_data(tmp_path: Path) -> None:
    """无 .env 时退化到 project_root/data。"""
    assert paths.resolve_data_dir(tmp_path) == (tmp_path / "data").resolve()


def test_resolve_data_dir_reads_env_absolute(tmp_path: Path) -> None:
    env = tmp_path / ".env"
    target = tmp_path / "custom_data"
    env.write_text(f"DATA_DIR={target}\n", encoding="utf-8")
    assert paths.resolve_data_dir(tmp_path) == target.resolve()


def test_resolve_data_dir_reads_env_relative(tmp_path: Path) -> None:
    env = tmp_path / ".env"
    env.write_text("DATA_DIR=./relative_data\n", encoding="utf-8")
    assert paths.resolve_data_dir(tmp_path) == (tmp_path / "relative_data").resolve()


def test_resolve_log_dir_explicit_over_data_dir(tmp_path: Path) -> None:
    env = tmp_path / ".env"
    log_dir = tmp_path / "custom_logs"
    env.write_text(f"DATA_DIR={tmp_path / 'data'}\nLOG_DIR={log_dir}\n", encoding="utf-8")
    assert paths.resolve_log_dir(tmp_path) == log_dir.resolve()


def test_resolve_log_dir_fallback_to_data_dir_logs(tmp_path: Path) -> None:
    env = tmp_path / ".env"
    env.write_text(f"DATA_DIR={tmp_path / 'data'}\n", encoding="utf-8")
    assert paths.resolve_log_dir(tmp_path) == (tmp_path / "data" / "logs").resolve()


def test_resolve_celery_dir_explicit_over_data_dir(tmp_path: Path) -> None:
    env = tmp_path / ".env"
    celery_dir = tmp_path / "custom_celery"
    env.write_text(
        f"DATA_DIR={tmp_path / 'data'}\nCELERY_FOLDER={celery_dir}\n",
        encoding="utf-8",
    )
    assert paths.resolve_celery_dir(tmp_path) == celery_dir.resolve()


def test_resolve_celery_dir_fallback_to_data_dir_celery(tmp_path: Path) -> None:
    env = tmp_path / ".env"
    env.write_text(f"DATA_DIR={tmp_path / 'data'}\n", encoding="utf-8")
    assert paths.resolve_celery_dir(tmp_path) == (tmp_path / "data" / "celery").resolve()


def test_resolve_paddlex_dir_env_var_wins(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    env_dir = tmp_path / "env_paddlex"
    monkeypatch.setenv("PADDLE_PDX_CACHE_HOME", str(env_dir))
    assert paths.resolve_paddlex_dir(tmp_path) == env_dir


def test_resolve_paddlex_dir_from_env_file_over_data_dir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    env = tmp_path / ".env"
    file_dir = tmp_path / "file_paddlex"
    env.write_text(f"PADDLE_PDX_CACHE_HOME={file_dir}\n", encoding="utf-8")
    monkeypatch.delenv("PADDLE_PDX_CACHE_HOME", raising=False)
    assert paths.resolve_paddlex_dir(tmp_path) == file_dir.resolve()


def test_resolve_paddlex_dir_fallback_to_data_dir_paddlex(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    env = tmp_path / ".env"
    env.write_text(f"DATA_DIR={tmp_path / 'data'}\n", encoding="utf-8")
    monkeypatch.delenv("PADDLE_PDX_CACHE_HOME", raising=False)
    assert paths.resolve_paddlex_dir(tmp_path) == (tmp_path / "data" / "paddlex").resolve()
