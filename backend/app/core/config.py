from functools import lru_cache
from pathlib import Path

from pydantic import Field, computed_field
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
    api_host: str = "127.0.0.1"
    api_port: int = 8000
    web_host: str = "127.0.0.1"
    web_port: int = 5173
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    secret_key: str = "change-me-in-local-env"
    jwt_expire_hours: int = 24
    project_root: Path = Path(__file__).resolve().parents[3]
    database_url: str | None = None
    celery_broker_url: str = "filesystem://"
    celery_timezone: str = "Asia/Shanghai"
    celery_worker_pool: str = "solo"
    celery_worker_concurrency: int = 1
    celery_log_level: str = "INFO"
    weekly_crawl_day_of_week: int = 1
    weekly_crawl_hour: int = 2
    weekly_crawl_minute: int = 0
    opencli_cdp_endpoint: str = "http://localhost:9222"
    search_interval_min: int = 10
    search_interval_max: int = 15
    search_limit: int = 50
    weekly_search_limit: int = 500
    minimax_api_key: str = ""
    data_dir_setting: Path = Field(Path("./data"), validation_alias="DATA_DIR")
    image_dir_setting: Path = Field(Path("./data/images"), validation_alias="IMAGE_DIR")
    export_dir_setting: Path = Field(Path("./data/exports"), validation_alias="EXPORT_DIR")
    celery_folder_setting: Path = Field(Path("./data/celery"), validation_alias="CELERY_FOLDER")

    def resolve_project_path(self, path: Path) -> Path:
        return path if path.is_absolute() else self.project_root / path

    @computed_field
    @property
    def data_dir(self) -> Path:
        return self.resolve_project_path(self.data_dir_setting)

    @computed_field
    @property
    def sqlite_path(self) -> Path:
        return self.data_dir / "app.db"

    @computed_field
    @property
    def image_dir(self) -> Path:
        return self.resolve_project_path(self.image_dir_setting)

    @computed_field
    @property
    def export_dir(self) -> Path:
        return self.resolve_project_path(self.export_dir_setting)

    @computed_field
    @property
    def celery_folder(self) -> Path:
        return self.resolve_project_path(self.celery_folder_setting)

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def effective_database_url(self) -> str:
        if self.database_url and self.database_url.startswith("sqlite:///./"):
            relative_path = self.database_url.removeprefix("sqlite:///./")
            return f"sqlite:///{(self.project_root / relative_path).resolve()}"
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
