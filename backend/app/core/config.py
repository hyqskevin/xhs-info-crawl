import os
from functools import lru_cache
from pathlib import Path
from typing import Any

from pydantic import Field, computed_field, model_validator
from pydantic_settings import BaseSettings, PydanticBaseSettingsSource, SettingsConfigDict


class _DataDirEnvSource(PydanticBaseSettingsSource):
    """读 <DATA_DIR>/.env 作为补充源,优先级低于 cwd/.env。

    解决 dev 模式下项目根 `.env` 里的用户配置(如 MINIMAX_API_KEY)不被
    `data/.env` 空值覆盖的问题;同时为打包版保留 fallback 能力:
    当 cwd/.env(通常是 .app/.env) 没写用户配置 key 时,从 DATA_DIR/.env 读。

    优先级(从高到低):init_settings > env_settings > dotenv_settings(cwd/.env)
    > _DataDirEnvSource(data/.env) > file_secret_settings

    关联 spec: docs/superpowers/specs/2026-08-23-settings-load-data-dir-env-design.md
    关联 spec: docs/superpowers/specs/2026-09-02-env-loading-priority-design.md
    """

    def __init__(self, settings_cls: type[BaseSettings]) -> None:
        super().__init__(settings_cls)
        # 读 cwd 下 .env 拿到 DATA_DIR(还没被 Settings 解析过,只能手解)
        cwd_env_path = Path.cwd() / ".env"
        data_dir: Path | None = None
        if cwd_env_path.exists():
            for line in cwd_env_path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line.startswith("#") or "=" not in line:
                    continue
                k, _, v = line.partition("=")
                if k.strip() == "DATA_DIR":
                    raw = v.strip()
                    if raw:
                        candidate = Path(raw).expanduser()
                        if candidate.is_absolute():
                            data_dir = candidate.resolve()
                        else:
                            data_dir = (Path.cwd() / candidate).resolve()
                    break
        self._path = data_dir / ".env" if data_dir else None

    def get_field_value(
        self, field: Any, field_name: str
    ) -> tuple[Any, str, bool]:
        if self._path is None or not self._path.exists():
            return None, field_name, False
        for line in self._path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            if k.strip().upper() == field_name.upper():
                return v.strip(), field_name, False
        return None, field_name, False

    def __call__(self) -> dict[str, Any]:
        """返回 DATA_DIR/.env 的全部 {key: value}。

        同时提供原 KEY 大写 + 小写字段名,因为 Settings 字段名是 snake_case 小写
        (无 validation_alias),需要用小写键才能匹配上。dotenv_settings 内部会
        对环境变量名做 case-insensitive 匹配,但 custom source 不会 — 我们手动
        两份都写,保证任意字段定义都能命中。
        """
        if self._path is None or not self._path.exists():
            return {}
        result: dict[str, Any] = {}
        for line in self._path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            raw_key = k.strip()
            value = v.strip()
            result[raw_key] = value
            result[raw_key.lower()] = value
        return result

    def prepare_field_value(
        self, field: Any, value: Any, value_is_complex: bool
    ) -> Any:
        return value


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        # pydantic_settings._settings_build_values 用 state = deep_update(source_state, state)
        # 即累积 state 覆盖新 source_state — **先** 处理的 source 永远赢(不被后处理覆盖)。
        # 想要:init(代码 init) > env(进程环境) > cwd/.env > DATA_DIR/.env > file_secret
        # 即按优先级从高到低排列 sources。
        return (
            init_settings,
            env_settings,
            dotenv_settings,
            _DataDirEnvSource(settings_cls),
            file_secret_settings,
        )

    app_name: str = "小红书本地活动信息抓取系统"
    app_env: str = "development"
    api_v1_prefix: str = "/api/v1"
    api_host: str = "127.0.0.1"
    api_port: int = 8000
    web_host: str = "127.0.0.1"
    web_port: int = 5173
    # CORS origin 列表(逗号分隔)。默认包含 5173-5199 范围内所有 host。
    # 启动器启动后会通过 .env 注入 WEB_PORT,即使端口被推到范围外也能命中。
    # 关联 spec: docs/superpowers/specs/2026-08-16-packaged-frontend-static-serving-design.md
    cors_origins: str = (
        "http://localhost:5173,http://127.0.0.1:5173,"
        "http://localhost:5174,http://127.0.0.1:5174,"
        "http://localhost:5175,http://127.0.0.1:5175,"
        "http://localhost:5176,http://127.0.0.1:5176,"
        "http://localhost:5177,http://127.0.0.1:5177,"
        "http://localhost:5178,http://127.0.0.1:5178,"
        "http://localhost:5179,http://127.0.0.1:5179,"
        "http://localhost:5180,http://127.0.0.1:5180,"
        "http://localhost:5181,http://127.0.0.1:5181,"
        "http://localhost:5182,http://127.0.0.1:5182,"
        "http://localhost:5183,http://127.0.0.1:5183,"
        "http://localhost:5184,http://127.0.0.1:5184,"
        "http://localhost:5185,http://127.0.0.1:5185,"
        "http://localhost:5186,http://127.0.0.1:5186,"
        "http://localhost:5187,http://127.0.0.1:5187,"
        "http://localhost:5188,http://127.0.0.1:5188,"
        "http://localhost:5189,http://127.0.0.1:5189,"
        "http://localhost:5190,http://127.0.0.1:5190,"
        "http://localhost:5191,http://127.0.0.1:5191,"
        "http://localhost:5192,http://127.0.0.1:5192,"
        "http://localhost:5193,http://127.0.0.1:5193,"
        "http://localhost:5194,http://127.0.0.1:5194,"
        "http://localhost:5195,http://127.0.0.1:5195,"
        "http://localhost:5196,http://127.0.0.1:5196,"
        "http://localhost:5197,http://127.0.0.1:5197,"
        "http://localhost:5198,http://127.0.0.1:5198,"
        "http://localhost:5199,http://127.0.0.1:5199"
    )
    secret_key: str = "change-me-in-local-env"
    jwt_expire_hours: int = 24
    project_root: Path = Path(__file__).resolve().parents[3]
    # base dir 模式: DATABASE_URL 留空时自动从 DATA_DIR 拼 sqlite:///$DATA_DIR/app.db
    # 关联 spec: docs/superpowers/specs/2026-08-17-launcher-storage-base-dir-design.md
    database_url: str | None = Field(default=None, validation_alias="DATABASE_URL")
    celery_broker_url: str = "filesystem://"
    celery_timezone: str = "Asia/Shanghai"
    celery_worker_pool: str = "solo"
    celery_worker_concurrency: int = 1
    celery_log_level: str = "INFO"
    weekly_crawl_day_of_week: int = 1
    weekly_crawl_hour: int = 2
    weekly_crawl_minute: int = 0
    opencli_cdp_endpoint: str = "http://localhost:9222"
    opencli_bin: str = "opencli"
    # 默认 opencli profile alias（2026-08-24 加入）。OpenCLIAdapter 构造时不传
    # profile_alias 时,会用这个值作为 --profile <alias> 注入到所有 opencli 子进程。
    # 可被 XhsAccount.session_name 覆盖（每个账号独立 profile）。
    # None = 不注入 --profile,沿用默认 Browser Bridge profile（向后兼容）。
    opencli_default_profile: str | None = Field(default=None, validation_alias="OPENCLI_DEFAULT_PROFILE")
    xhs_login_url: str = "https://www.xiaohongshu.com/explore"
    xhs_login_browser: str = "Google Chrome"
    search_interval_min: int = 10
    search_interval_max: int = 15
    search_limit: int = 50
    weekly_search_limit: int = 500
    consecutive_note_failure_limit: int = 2  # 2026-08-22 task28 反馈改为 2：SECURITY_BLOCK 连续 2 次即熔断
    # 连续 N 篇 note.content 为空触发 PAUSED；默认 5（防小红书风控静默失败）
    crawl_empty_detail_threshold: int = 5
    # 每抓 N 条调一次 adapter.close_session() 重建 CDP 连接；0 表示禁用
    crawl_session_reset_interval: int = 30
    minimax_api_key: str = ""
    minimax_base_url: str = "https://api.openai.com/v1"
    minimax_model: str = ""
    minimax_vision_model: str = ""
    minimax_chat_path: str = "/chat/completions"
    minimax_timeout_seconds: int = 180
    ocr_enabled: bool = False
    ocr_language: str = "ch"
    ocr_min_confidence: float = 0.5
    ocr_use_doc_orientation_classify: bool = False
    ocr_use_doc_unwarping: bool = False
    ocr_use_textline_orientation: bool = False
    # 笔记内图片并行 OCR 线程数（1-4，本地 PaddleOCR 模型，不占网络带宽）
    ocr_parallel_workers: int = 2
    # MiniMax API 并发调用数（1-4，默认 1 向后兼容，小范围并行避免 529 限流）
    minimax_concurrency: int = 1
    # 前端构建产物目录(打包版用,开发模式不存在则跳过挂载)
    frontend_dist_path: Path = Field(
        Path("./frontend/dist"),
        validation_alias="FRONTEND_DIST_PATH",
    )
    xhs_search_target_count: int = 50
    xhs_search_scroll_max_rounds: int = 8
    xhs_detail_scroll_max_rounds: int = 8
    xhs_scroll_pixels: int = 800
    xhs_scroll_stagnant_rounds: int = 2
    pipeline_stage_max_retries: int = 2
    pipeline_stage_retry_delay_seconds: float = 2
    activity_future_window_days: int = 60
    # 多账号轮询：每个账号连续抓 N 篇后主动切换到下一个账号（避免触发频率限制）
    # 仅当配置了 ≥2 个已启用账号时生效；=1 时不切换
    account_rotation_notes: int = 25
    # 账号切换-自动登录：切换目标账号后等待扫码完成 的轮询间隔(秒)与总超时(秒)
    xhs_account_login_wait_interval: int = 5
    xhs_account_login_wait_timeout: int = 120
    # 定时任务多运行连续失败熔断（跨运行级）：阈值与冷却后自动重启间隔(分钟)
    # ScheduledCrawl 行内同名字段为空时回退到这两个全局默认
    schedule_consecutive_fail_limit: int = 3
    schedule_retry_interval_minutes: int = 60
    # ─── 存储路径(用户只设 DATA_DIR,其他自动从 DATA_DIR 推导) ───
    # 关联: docs/superpowers/specs/2026-08-17-launcher-storage-base-dir-design.md
    data_dir_setting: Path = Field(Path("./data"), validation_alias="DATA_DIR")
    # 子目录 *_DIR 默认从 DATA_DIR 拼,但如果用户在 .env 明确设了 *_DIR,
    # 就用用户值(向后兼容 + 高级用户可单独覆盖)
    image_dir_setting: Path | None = Field(default=None, validation_alias="IMAGE_DIR")
    export_dir_setting: Path | None = Field(default=None, validation_alias="EXPORT_DIR")
    archive_dir_setting: Path | None = Field(default=None, validation_alias="ARCHIVE_DIR")
    celery_folder_setting: Path | None = Field(default=None, validation_alias="CELERY_FOLDER")
    tmp_dir_setting: Path | None = Field(default=None, validation_alias="TMP_DIR")
    paddle_pdx_cache_home: Path | None = Field(default=None, validation_alias="PADDLE_PDX_CACHE_HOME")
    huggingface_cache_home: Path | None = Field(default=None, validation_alias="HF_HOME")
    # 任务子进程注册表路径（跨 API 与 worker 进程共享）
    task_registry_path: Path | None = Field(
        default=None, validation_alias="TASK_REGISTRY_PATH"
    )
    # ChromePool 启动的多 Chrome 实例的 user-data-dir 根目录
    chrome_user_data_dir: Path | None = Field(
        default=None, validation_alias="CHROME_USER_DATA_DIR"
    )
    # Chrome 二进制路径（ChromePool 启动用）
    chrome_bin: str = Field(
        "google-chrome",
        validation_alias="CHROME_BIN",
    )
    # opencli Browser Bridge 扩展解压目录（ChromePool 启动实例时 --load-extension）。
    # 配置后实例以非 headless 启动（扩展需真实窗口连接 opencli daemon）；
    # None = 保持 headless、不加载扩展（向后兼容）。
    opencli_extension_path: Path | None = Field(
        default=None, validation_alias="OPENCLI_EXTENSION_PATH"
    )

    @model_validator(mode="after")
    def _sync_storage_subdirs_from_data_dir(self) -> "Settings":
        """从 DATA_DIR 推导所有子目录,除非用户在 .env 明确设了。

        用户体验:只设一个 DATA_DIR=~/xhs-info-crawl,
        子目录自动 ~/xhs-info-crawl/{images,exports,archive,logs,paddlex,huggingface,celery,tmp,run}
        关联 spec: docs/superpowers/specs/2026-08-17-launcher-storage-base-dir-design.md
        """
        data_dir = self.data_dir_setting
        # 把 ~ 展开
        if str(data_dir).startswith("~"):
            data_dir = Path(os.path.expanduser(str(data_dir)))
            self.data_dir_setting = data_dir

        defaults = {
            "image_dir_setting": data_dir / "images",
            "export_dir_setting": data_dir / "exports",
            "archive_dir_setting": data_dir / "archive",
            "celery_folder_setting": data_dir / "celery",
            "tmp_dir_setting": data_dir / "tmp",
            "paddle_pdx_cache_home": data_dir / "paddlex",
            "huggingface_cache_home": data_dir / "huggingface",
            "task_registry_path": data_dir / "run" / "task_registry.json",
            "chrome_user_data_dir": data_dir / "chrome-pool",
        }
        for attr, default_path in defaults.items():
            if getattr(self, attr) is None:
                setattr(self, attr, default_path)
        return self

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
        return self.resolve_project_path(self.image_dir_setting) if self.image_dir_setting else self.data_dir / "images"

    @computed_field
    @property
    def export_dir(self) -> Path:
        return self.resolve_project_path(self.export_dir_setting) if self.export_dir_setting else self.data_dir / "exports"

    @computed_field
    @property
    def archive_dir(self) -> Path:
        return self.resolve_project_path(self.archive_dir_setting) if self.archive_dir_setting else self.data_dir / "archive"

    @computed_field
    @property
    def celery_folder(self) -> Path:
        return self.resolve_project_path(self.celery_folder_setting) if self.celery_folder_setting else self.data_dir / "celery"

    @computed_field
    @property
    def task_registry_file(self) -> Path:
        """解析后的任务注册表文件路径（绝对路径，在项目内）。"""
        path = self.task_registry_path or self.data_dir / "run" / "task_registry.json"
        return self.resolve_project_path(path)

    @computed_field
    @property
    def tmp_dir(self) -> Path:
        """解析后的临时文件目录（绝对路径，在项目内）。"""
        path = self.tmp_dir_setting or self.data_dir / "tmp"
        return self.resolve_project_path(path)

    @computed_field
    @property
    def opencli_extension_dir(self) -> Path | None:
        """解析后的 opencli Browser Bridge 扩展目录（绝对路径）；未配置返回 None。"""
        if self.opencli_extension_path is None:
            return None
        return self.resolve_project_path(self.opencli_extension_path)

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def effective_database_url(self) -> str:
        """DATABASE_URL 缺省时自动从 DATA_DIR 拼 sqlite:///$DATA_DIR/app.db,
        保证 db 跟随 DATA_DIR(用户只设一个 base 目录即可)。
        关联 spec: docs/superpowers/specs/2026-08-17-launcher-storage-base-dir-design.md
        """
        if self.database_url and self.database_url.startswith("sqlite:///./"):
            # 老式 dev 相对路径 → 用 DATA_DIR 重写
            return f"sqlite:///{self.sqlite_path}"
        if self.database_url and self.database_url.startswith("sqlite:///"):
            # 已经是绝对路径(用户自配),保留
            return self.database_url
        # 完全缺省 → 自动从 DATA_DIR 拼
        return f"sqlite:///{self.sqlite_path}"

    def ensure_runtime_directories(self) -> None:
        for path in (
            self.sqlite_path.parent,
            self.image_dir,
            self.export_dir,
            self.archive_dir,
            self.celery_folder / "queue",
            self.celery_folder / "processed",
            self.task_registry_file.parent,
            self.tmp_dir,
            self.resolve_project_path(self.paddle_pdx_cache_home),
            self.resolve_project_path(self.huggingface_cache_home),
        ):
            path.mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    # 关键:在 Python 进程启动时设置环境变量,确保 paddleocr/huggingface 不污染用户 home
    # 之前只靠 scripts/dev-worker.sh 的 export,直接跑 uvicorn/celery 时会缺失
    cache_home = str(settings.paddle_pdx_cache_home.resolve())
    hf_home = str(settings.huggingface_cache_home.resolve())
    os.environ.setdefault("PADDLE_PDX_CACHE_HOME", cache_home)
    os.environ.setdefault("HF_HOME", hf_home)
    # 确保目录存在
    settings.paddle_pdx_cache_home.mkdir(parents=True, exist_ok=True)
    settings.huggingface_cache_home.mkdir(parents=True, exist_ok=True)
    return settings
