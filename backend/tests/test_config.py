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
    assert (settings.celery_folder / "queue").is_dir()
    assert (settings.celery_folder / "processed").is_dir()


def test_runtime_paths_can_be_overridden_from_environment(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("DATA_DIR", "./runtime")
    monkeypatch.setenv("IMAGE_DIR", "./assets/images")
    monkeypatch.setenv("EXPORT_DIR", "./deliverables")
    monkeypatch.setenv("CELERY_FOLDER", "./runtime/tasks")

    settings = Settings(project_root=tmp_path)

    assert settings.data_dir == tmp_path / "runtime"
    assert settings.image_dir == tmp_path / "assets" / "images"
    assert settings.export_dir == tmp_path / "deliverables"
    assert settings.celery_folder == tmp_path / "runtime" / "tasks"


def test_paddleocr_model_dir_field_removed() -> None:
    """死配置 paddleocr_model_dir 已删除(从未被 paddleocr_adapter 使用)。"""
    settings = Settings(_env_file=None)
    assert not hasattr(settings, "paddleocr_model_dir"), (
        "paddleocr_model_dir 是死配置,paddleocr_adapter.py 从未使用,应已删除"
    )


def test_paddle_pdx_cache_home_field_exists_with_default() -> None:
    """新增 paddle_pdx_cache_home 字段,默认 ./data/paddlex。"""
    settings = Settings(_env_file=None)
    assert hasattr(settings, "paddle_pdx_cache_home")
    assert settings.paddle_pdx_cache_home == Path("./data/paddlex")


def test_huggingface_cache_home_field_exists_with_default() -> None:
    """新增 huggingface_cache_home 字段,默认 ./data/huggingface。"""
    settings = Settings(_env_file=None)
    assert hasattr(settings, "huggingface_cache_home")
    assert settings.huggingface_cache_home == Path("./data/huggingface")


def test_paddle_pdx_cache_home_reads_from_env(tmp_path: Path, monkeypatch) -> None:
    """PADDLE_PDX_CACHE_HOME 环境变量可覆盖默认值。"""
    custom = tmp_path / "paddlex"
    monkeypatch.setenv("PADDLE_PDX_CACHE_HOME", str(custom))
    settings = Settings(_env_file=None)
    assert settings.paddle_pdx_cache_home == custom


def test_huggingface_cache_home_reads_from_hf_home_env(tmp_path: Path, monkeypatch) -> None:
    """HF_HOME 环境变量可覆盖 huggingface_cache_home 默认值(验证 validation_alias 生效)。"""
    custom = tmp_path / "huggingface"
    monkeypatch.setenv("HF_HOME", str(custom))
    settings = Settings(_env_file=None)
    assert settings.huggingface_cache_home == custom
