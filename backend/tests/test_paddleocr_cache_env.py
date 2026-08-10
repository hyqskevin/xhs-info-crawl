"""验证 get_settings() 调用后,环境变量 PADDLE_PDX_CACHE_HOME 和 HF_HOME 已设置。

之前只靠 scripts/dev-worker.sh 的 export,直接跑 uvicorn/celery 时会缺失,
导致 paddleocr 污染 ~/.paddlex/(违反 AGENTS.md 硬约束)。
"""
import os
from pathlib import Path

from app.core.config import get_settings


def test_get_settings_sets_paddle_pdx_cache_home_env(tmp_path: Path, monkeypatch) -> None:
    """get_settings() 后 os.environ['PADDLE_PDX_CACHE_HOME'] 已设置。"""
    get_settings.cache_clear()
    monkeypatch.delenv("PADDLE_PDX_CACHE_HOME", raising=False)
    monkeypatch.delenv("HF_HOME", raising=False)
    monkeypatch.setenv("PADDLE_PDX_CACHE_HOME", str(tmp_path / "paddlex"))
    monkeypatch.setenv("HF_HOME", str(tmp_path / "huggingface"))

    get_settings.cache_clear()
    settings = get_settings()

    assert os.environ.get("PADDLE_PDX_CACHE_HOME") is not None
    assert str(settings.paddle_pdx_cache_home.resolve()) == os.environ["PADDLE_PDX_CACHE_HOME"]


def test_get_settings_sets_hf_home_env(tmp_path: Path, monkeypatch) -> None:
    """get_settings() 后 os.environ['HF_HOME'] 已设置。"""
    get_settings.cache_clear()
    monkeypatch.delenv("PADDLE_PDX_CACHE_HOME", raising=False)
    monkeypatch.delenv("HF_HOME", raising=False)
    monkeypatch.setenv("PADDLE_PDX_CACHE_HOME", str(tmp_path / "paddlex"))
    monkeypatch.setenv("HF_HOME", str(tmp_path / "huggingface"))

    get_settings.cache_clear()
    settings = get_settings()

    assert os.environ.get("HF_HOME") is not None
    assert str(settings.huggingface_cache_home.resolve()) == os.environ["HF_HOME"]


def test_get_settings_creates_cache_directories(tmp_path: Path, monkeypatch) -> None:
    """get_settings() 创建缓存目录(若不存在)。"""
    get_settings.cache_clear()
    paddlex_dir = tmp_path / "paddlex"
    hf_dir = tmp_path / "huggingface"
    monkeypatch.setenv("PADDLE_PDX_CACHE_HOME", str(paddlex_dir))
    monkeypatch.setenv("HF_HOME", str(hf_dir))

    get_settings.cache_clear()
    get_settings()

    assert paddlex_dir.is_dir()
    assert hf_dir.is_dir()


def test_get_settings_does_not_override_existing_env(tmp_path: Path, monkeypatch) -> None:
    """get_settings() 用 setdefault,不覆盖已存在的环境变量。"""
    get_settings.cache_clear()
    pre_existing = str(tmp_path / "pre-existing-paddlex")
    monkeypatch.setenv("PADDLE_PDX_CACHE_HOME", pre_existing)
    monkeypatch.setenv("HF_HOME", str(tmp_path / "pre-existing-hf"))

    get_settings.cache_clear()
    get_settings()

    assert os.environ["PADDLE_PDX_CACHE_HOME"] == pre_existing
