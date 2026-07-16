from functools import lru_cache
from pathlib import Path

from pydantic import computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "小红书本地活动信息抓取系统"
    app_env: str = "development"
    api_v1_prefix: str = "/api/v1"
    secret_key: str = "change-me-in-local-env"
    project_root: Path = Path(__file__).resolve().parents[3]
    database_url: str | None = None
    celery_broker_url: str = "filesystem://"
    opencli_cdp_endpoint: str = "http://localhost:9222"
    minimax_api_key: str = ""

    @computed_field
    @property
    def data_dir(self) -> Path:
        return self.project_root / "data"

    @computed_field
    @property
    def sqlite_path(self) -> Path:
        return self.data_dir / "app.db"

    @computed_field
    @property
    def image_dir(self) -> Path:
        return self.data_dir / "images"

    @computed_field
    @property
    def export_dir(self) -> Path:
        return self.data_dir / "exports"

    @computed_field
    @property
    def celery_folder(self) -> Path:
        return self.data_dir / "celery"

    @property
    def effective_database_url(self) -> str:
        return self.database_url or f"sqlite:///{self.sqlite_path}"

    def ensure_runtime_directories(self) -> None:
        for path in (
            self.sqlite_path.parent,
            self.image_dir,
            self.export_dir,
            self.celery_folder / "queue",
            self.celery_folder / "processed",
        ):
            path.mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    return Settings()
