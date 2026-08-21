"""本地状态 HTTP 服务:启动器 UI 通过这个服务查询和控制后端进程。

关联 spec: docs/superpowers/specs/2026-08-10-one-click-packaging-design.md § 2.2 + § 4.4
"""
from __future__ import annotations

import logging
import os
import platform
import threading
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from launcher.opencli_checker import check_opencli, OPENCLI_DOWNLOAD_URL, OpenCLIResult
from launcher.ocr_installer import get_ocr_status, download_and_install, OcrInstallResult
from launcher.process_manager import ProcessManager
from launcher.env_bootstrap import update_env_value

logger = logging.getLogger(__name__)


class StatusServer:
    """启动器本地状态服务。

    UI 通过 fetch 轮询这个服务来获取/控制状态。
    """

    def __init__(
        self,
        process_manager: ProcessManager,
        project_root: Path,
        venv_python: Path,
        api_base_url: str = "http://127.0.0.1:8000",
        web_base_url: str = "http://127.0.0.1:5173",
    ):
        self.process_manager = process_manager
        self.project_root = project_root
        self.venv_python = venv_python
        self.api_base_url = api_base_url
        self.web_base_url = web_base_url
        self._install_thread: Optional[threading.Thread] = None
        self._install_progress: dict = {"active": False, "percent": 0, "message": ""}
        self.app = self._create_app()

    def _create_app(self) -> FastAPI:
        app = FastAPI(title="Launcher Status Server")
        app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_methods=["*"],
            allow_headers=["*"],
        )

        @app.get("/status")
        def get_status():
            return self.process_manager.get_status()

        @app.get("/api-port")
        def get_api_port():
            """返回后端 API 实际监听的端口(用于启动器 UI 打开业务前端)。"""
            # 从 api_base_url (如 http://127.0.0.1:8001) 解析端口
            from urllib.parse import urlparse
            parsed = urlparse(self.api_base_url)
            return {"port": parsed.port or 8000}

        @app.get("/web-port")
        def get_web_port():
            """返回前端静态服务实际监听的端口(用于启动器 UI 打开业务前端页面)。

            与 /api-port 对称:api-port 指向后端 API,web-port 指向前端页面所在端口。
            """
            from urllib.parse import urlparse
            parsed = urlparse(self.web_base_url)
            return {"port": parsed.port or 5173, "url": self.web_base_url}

        @app.get("/initial-password")
        def get_initial_password():
            """返回启动器自动生成的初始密码(用于启动器 UI 顶部 banner)。

            仅当 data/run/INITIAL_ADMIN_PASSWORD.txt 存在时返回;
            该文件由 ensure_env_file 自动写密码时创建,用户手动配置密码时不会创建。

            关联 spec: docs/superpowers/specs/2026-08-16-launcher-password-visibility-design.md § 2
            """
            from fastapi.responses import JSONResponse
            password_file = self.project_root / "data" / "run" / "INITIAL_ADMIN_PASSWORD.txt"
            if not password_file.exists():
                # 用户手动配置,启动器 UI 不展示 banner
                return JSONResponse(status_code=204, content=None)
            content = password_file.read_text(encoding="utf-8")
            # 解析 password=<value> 行
            password = None
            auto_generated = True
            generated_at = None
            for line in content.splitlines():
                line = line.strip()
                if line.startswith("password="):
                    password = line.split("=", 1)[1].strip()
                elif line.startswith("# 类型:"):
                    auto_generated = "自动生成" in line
                elif line.startswith("# 生成时间:"):
                    generated_at = line.replace("# 生成时间:", "").strip()
            if not password:
                return JSONResponse(status_code=204, content=None)
            return {
                "password": password,
                "auto_generated": auto_generated,
                "generated_at": generated_at,
            }

        @app.post("/service/{name}/restart")
        def restart_service(name: str):
            success = self.process_manager.restart_service(name)
            return {"ok": success}

        @app.post("/service/all/stop")
        def stop_all():
            self.process_manager.stop_all()
            return {"ok": True}

        @app.get("/opencli/test")
        def test_opencli():
            result: OpenCLIResult = check_opencli()
            return {
                "ok": result.ok,
                "version": result.version,
                "reason": result.reason,
                "message": result.message,
                # 细粒度独立状态
                "daemon": {
                    "running": result.daemon_running,
                    "port": result.daemon_port,
                },
                "chrome": {
                    "running": result.chrome_running,
                    "path": result.chrome_path,
                },
                "extension": {
                    "connected": result.extension_connected,
                    "profile": result.extension_profile,
                },
            }

        @app.get("/opencli/download-url")
        def opencli_download_url():
            return {"url": OPENCLI_DOWNLOAD_URL}

        # ── 系统配置（LLM / OCR / opencli 路径 / 存储路径）──
        # launcher 阶段用户填的 LLM 数据 → 写到 .env + 重启 worker 让新配置生效
        # 不走后端 PUT /api/v1/settings/system-config（避免鉴权 + cache 同步的麻烦）
        _LAUNCHER_SYSTEM_CONFIG_KEYS = (
            "minimax_api_key",
            "minimax_base_url",
            "minimax_model",
            "minimax_vision_model",
            "minimax_timeout_seconds",
            "minimax_concurrency",
            "ocr_enabled",
            "ocr_language",
            "ocr_min_confidence",
            "ocr_parallel_workers",
            "opencli_bin",
            "chrome_bin",
            "chrome_user_data_dir",
            # 存储路径 — base dir 模式
            # 关联 spec: docs/superpowers/specs/2026-08-17-launcher-storage-base-dir-design.md
            # 用户只设 DATA_DIR;其他子目录(IMAGE_DIR / EXPORT_DIR / ARCHIVE_DIR /
            # PADDLE_PDX_CACHE_HOME / HF_HOME 等)由 backend Settings 自动从 DATA_DIR 推导。
            # LOG_DIR 例外:launcher 自己用,需要单独设。
            "data_dir",
            "log_dir",
        )

        # 用户字段(走双写 + DATA_DIR 优先);bootstrap 字段只走 project_root;
        # ocr_enabled 由改动 3 sync 函数单方管理,不参与合并
        _LAUNCHER_USER_FIELD_KEYS = frozenset({
            "minimax_api_key",
            "minimax_base_url",
            "minimax_model",
            "minimax_vision_model",
            "minimax_timeout_seconds",
            "minimax_concurrency",
            "ocr_language",
            "ocr_min_confidence",
            "ocr_parallel_workers",
            "opencli_bin",
            "chrome_bin",
            "chrome_user_data_dir",
        })
        # 启动器 bootstrap 字段,只写 project_root,不被 DATA_DIR 覆盖
        # 这些是运行环境绑定(port/host/secret),不能从用户数据回填
        _LAUNCHER_BOOTSTRAP_KEYS = frozenset()
        # 路径类 bootstrap(DATA_DIR 本身 + LOG_DIR 必须从 project_root 读,
        # 否则启动器找不到数据目录):data_dir/log_dir 在 _read_launcher_system_config
        # 里同样从 project_root/.env 拿,不参与 DATA_DIR 合并

        # macOS 规范的 Application Support 目录,推荐作为默认 data_dir
        # 避免升级 .app 时数据被覆盖,且 Time Machine 自动备份
        DEFAULT_DATA_DIR = "~/Library/Application Support/com.xhs-info-crawl.local"

        # 防重犯:启动器负责同步 OCR_ENABLED 的唯一标记位。
        # 第一次被调用时执行,后续 GET 跳过(幂等)。
        # 用 dict 包装保证 closure 内可改 self._ocr_sync_done
        _sync_state = {"done": False}

        def _read_env_file(path: Path) -> dict[str, str]:
            """读单个 .env 文件,返回 {KEY: value} 字典(空值保留空串)。

            注释/无 = 行跳过。命中 # 开头的或空字符串值也会被读到。
            """
            result: dict[str, str] = {}
            if not path.exists():
                return result
            for line in path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line.startswith("#") or "=" not in line:
                    continue
                k, _, v = line.partition("=")
                k = k.strip()
                if not k:
                    continue
                result[k] = v.strip()
            return result

        def _resolve_data_dir_from_env(env_dict: dict[str, str]) -> Path | None:
            """从 .env dict 拿 DATA_DIR 指针;空值返回 None。"""
            raw = env_dict.get("DATA_DIR", "").strip()
            if not raw:
                return None
            if raw.startswith("~"):
                raw = str(Path(raw).expanduser())
            return Path(raw)

        def _merge_project_and_data_env() -> dict[str, str]:
            """合并 project_root/.env + DATA_DIR/.env → {KEY: value}。

            合并规则(关联 design docs/packaging-design.md §3.3):
            1. 先读 project_root/.env(bootstrap + 启动器自写)
            2. 再读 DATA_DIR/.env(用户配置主源)
            3. 用户字段(minimax_*/opencli_bin/chrome_bin/chrome_user_data_dir/
               ocr_language/ocr_min_confidence/ocr_parallel_workers)→
               DATA_DIR 非空值覆盖 project_root 空值
            4. bootstrap 字段(目前仅 data_dir/log_dir 算 bootstrap 类)→
               project_root 优先

            ocr_enabled 不参与合并,由 sync_ocr_enabled_with_installed_state 单向写入。
            """
            project_env_path = self.project_root / ".env"
            project_env = _read_env_file(project_env_path)
            data_dir = _resolve_data_dir_from_env(project_env)
            data_env_path = data_dir / ".env" if data_dir else None
            data_env = _read_env_file(data_env_path) if data_env_path else {}

            merged: dict[str, str] = dict(project_env)
            for k, v in data_env.items():
                # 用户字段:DATA_DIR 非空覆盖 project_root
                k_lower = k.lower()
                if k_lower in _LAUNCHER_USER_FIELD_KEYS and v:
                    merged[k] = v
                elif k_lower not in _LAUNCHER_USER_FIELD_KEYS:
                    # 非用户字段(用户主动写 DATA_DIR 里其他键不影响启动器)
                    # 不动 merged
                    continue
            return merged

        def _read_launcher_system_config() -> dict[str, str]:
            """从 .env 读 LLM / OCR / opencli_bin / chrome_bin / 存储路径 配置。

            改动 2:多路径读 .env — project_root + DATA_DIR/.env 合并。

            返回空字符串表示未配置；缺失 key 也返回空字符串（前端展示默认 placeholder）。
            """
            merged = _merge_project_and_data_env()
            config = {k: "" for k in _LAUNCHER_SYSTEM_CONFIG_KEYS}
            for k, v in merged.items():
                k_lower = k.lower()
                if k_lower in config:
                    # OCR_ENABLED 不参与合并 — 必须从 project_root 读
                    # (改动 3 sync 函数单方管理,启动器 bootstrap 写入优先)
                    if k_lower == "ocr_enabled":
                        # 只在 project_env 直接有值时采用
                        if k in merged and merged.get(k):
                            # merged 里 DATA_DIR 的 ocr_enabled 已经被排除,
                            # 但 project_env 的 ocr_enabled 是源头
                            config[k_lower] = v
                        continue
                    config[k_lower] = v
            # 存储路径字段缺省时返回 DEFAULT_DATA_DIR 让前端显示推荐路径
            # base dir 模式:只返回 DATA_DIR + LOG_DIR;其他子目录由 backend Settings 推导
            defaults = {
                "data_dir": DEFAULT_DATA_DIR,
                "log_dir": f"{DEFAULT_DATA_DIR}/logs",
            }
            for field_name, default_path in defaults.items():
                if not config.get(field_name):
                    config[field_name] = default_path
            return config

        def sync_ocr_enabled_with_installed_state() -> None:
            """改动 3:检测到 OCR 模型已装 → 自动把 OCR_ENABLED=true 写到 project_root/.env。

            关联 spec: docs/superpowers/specs/2026-08-21-packaging-ocr-llm-flow-fix-design.md § 改动 3
            关联设计: docs/packaging-design.md §3.6

            触发时机:第一次 GET /system-config 时执行一次(幂等)。
            不主动把 OCR_ENABLED 翻 false(保留用户选择)。
            """
            if _sync_state["done"]:
                return
            env_path = self.project_root / ".env"
            env = _read_env_file(env_path)
            current = env.get("OCR_ENABLED", "").strip().lower()
            if current == "true":
                _sync_state["done"] = True
                return
            # 检测 OCR 安装状态 — 复用一个函数(ocr_installer.get_ocr_status)
            status = get_ocr_status(self.project_root)
            if status.get("status") == "installed":
                update_env_value(env_path, "OCR_ENABLED", "true")
                os.environ["OCR_ENABLED"] = "true"
                logger.info("OCR 模型已装但 OCR_ENABLED=false,自动同步为 true")
            _sync_state["done"] = True

        @app.get("/system-config")
        def get_launcher_system_config():
            """从 .env 读取当前 LLM / OCR / opencli / chrome 配置。

            第一次调用时触发 sync_ocr_enabled_with_installed_state。
            """
            sync_ocr_enabled_with_installed_state()
            return _read_launcher_system_config()

        @app.put("/system-config")
        async def put_launcher_system_config(request: Request):
            """保存系统配置：写 .env + 重启 worker 让新配置生效。

            改动 6:用户字段双写 (project_root + DATA_DIR),bootstrap 字段只写 project_root。

            body JSON 字段:
            - minimax_api_key (str, 允许 mask 显示)
            - minimax_base_url (str)
            - minimax_model (str)
            - minimax_vision_model (str)
            - minimax_timeout_seconds (int)
            - minimax_concurrency (int)
            - ocr_enabled (bool)
            - ocr_language (str)
            - ocr_min_confidence (float)
            - ocr_parallel_workers (int)
            - opencli_bin (str)
            - chrome_bin (str)
            - chrome_user_data_dir (str)

            任意字段缺失或为 null 不修改现有 .env。
            """
            from fastapi import HTTPException
            import json as _json

            try:
                payload = await request.json()
            except _json.JSONDecodeError as exc:
                raise HTTPException(422, f"JSON 解析失败: {exc}")

            if not isinstance(payload, dict):
                raise HTTPException(422, "请求体必须是 JSON 对象")

            env_path = self.project_root / ".env"
            # DATA_DIR/.env — 用户配置主源
            proj_env = _read_env_file(env_path)
            data_dir_path = _resolve_data_dir_from_env(proj_env)
            data_env_path = data_dir_path / ".env" if data_dir_path else None

            updates: dict[str, str] = {}
            user_field_updates: dict[str, str] = {}
            for k, v in payload.items():
                if k not in _LAUNCHER_SYSTEM_CONFIG_KEYS:
                    continue
                if v is None:
                    continue
                # 存储路径字段:空字符串视为"恢复默认"(base dir 模式)
                if k in ("data_dir", "log_dir"):
                    s = str(v).strip()
                    if not s:
                        if k == "data_dir":
                            s = DEFAULT_DATA_DIR
                        elif k == "log_dir":
                            s = f"{DEFAULT_DATA_DIR}/logs"
                    # 展开 ~ → 用户主目录
                    if s.startswith("~"):
                        s = str(Path(s).expanduser())
                    updates[k.upper()] = s
                    continue
                # bool 转 0/1 写到 .env,方便 pydantic-settings 解析
                if isinstance(v, bool):
                    str_v = "true" if v else "false"
                else:
                    str_v = str(v)
                # ocr_enabled 不参与双写:启动器 bootstrap 字段,仅写 project_root
                # 由 sync 函数管
                if k == "ocr_enabled":
                    updates["OCR_ENABLED"] = str_v
                    continue
                # 其他用户字段:主写 project_root(兜底),双写到 DATA_DIR(用户配置主源)
                updates[k.upper()] = str_v
                if k in _LAUNCHER_USER_FIELD_KEYS and data_env_path is not None:
                    user_field_updates[k.upper()] = str_v

            if not updates:
                raise HTTPException(422, "没有可更新的字段")

            # 写入 .env 前,确保所有 *_DIR 目录都存在(防止 api/worker 启动时崩)
            for env_key, value in updates.items():
                if env_key.endswith("_DIR"):
                    try:
                        os.makedirs(value, exist_ok=True)
                    except OSError as exc:
                        raise HTTPException(
                            422,
                            f"无法创建目录 {value}: {exc};请检查路径是否合法且有写权限",
                        ) from exc

            # 1) 写 project_root/.env(全员)
            for env_key, value in updates.items():
                update_env_value(env_path, env_key, value)
                # 同步 launcher 进程的 os.environ,启动新 worker 时可继承
                import os as _os
                _os.environ[env_key] = value

            # 2) 写 DATA_DIR/.env(仅用户字段,且 DATA_DIR 存在)
            # 确保 DATA_DIR/.env 文件存在;第一次写时创建空文件
            if data_env_path is not None and user_field_updates:
                if not data_env_path.exists():
                    data_env_path.parent.mkdir(parents=True, exist_ok=True)
                    data_env_path.write_text("", encoding="utf-8")
                for env_key, value in user_field_updates.items():
                    update_env_value(data_env_path, env_key, value)
                    logger.info("DATA_DIR/.env 双写: %s=%s", env_key, "***" if "KEY" in env_key else value)

            # 判断是否有 *_DIR 路径变更(存储路径)
            # 路径变更需要重启 api + worker + beat + web,确保所有子进程都用新路径
            # LLM / OCR / opencli 变更只需重启 api + worker(pydantic-settings cache)
            has_path_change = any(k.endswith("_DIR") for k in updates.keys())

            restart_results = {
                "api": self.process_manager.restart_service("api"),
                "worker": self.process_manager.restart_service("worker"),
            }
            if has_path_change:
                # 路径变更:web/beat 进程内的浏览器与定时任务也要重启
                # 否则新图片仍写到旧目录
                restart_results["web"] = self.process_manager.restart_service("web")
                restart_results["beat"] = self.process_manager.restart_service("beat")

            logger.info(
                "通过 launcher 保存系统配置: %s -> 重启 %s",
                updates,
                ", ".join(f"{k}={v}" for k, v in restart_results.items()),
                list(updates.keys()),
                restart_results["api"],
                restart_results["worker"],
            )

            return {
                "ok": True,
                "saved_keys": list(updates.keys()),
                "restart": restart_results,
            }

        @app.get("/ocr/status")
        def ocr_status():
            return get_ocr_status(self.project_root)

        @app.post("/ocr/install")
        def ocr_install():
            if self._install_progress.get("active"):
                return {"ok": False, "message": "已有安装任务在运行"}
            os_name = "macos" if platform.system() == "Darwin" else "windows"
            arch = "arm64" if platform.machine() in ("arm64", "aarch64") else "x64"
            version = "3.7.0"

            def run_install():
                self._install_progress = {"active": True, "percent": 0, "message": "下载中"}
                try:
                    result: OcrInstallResult = download_and_install(
                        project_root=self.project_root,
                        os_name=os_name,
                        arch=arch,
                        version=version,
                        venv_python=self.venv_python,
                    )
                    self._install_progress = {
                        "active": False,
                        "percent": 100 if result.ok else 0,
                        "message": result.message,
                        "ok": result.ok,
                    }
                except Exception as exc:
                    self._install_progress = {
                        "active": False,
                        "percent": 0,
                        "message": f"安装失败: {exc}",
                        "ok": False,
                    }

            self._install_thread = threading.Thread(target=run_install, daemon=True)
            self._install_thread.start()
            return {"ok": True, "message": "安装已启动"}

        @app.get("/ocr/install-progress")
        def ocr_install_progress():
            return self._install_progress

        @app.post("/ocr/test")
        def ocr_test():
            # 直接调 backend app.services.diagnostics_ocr.probe_ocr,不走 HTTP/JWT。
            # 之前 httpx.post 走业务 API 必须 JWT,但 launcher 没有 token → 401。
            # OCR 诊断属于 launcher 内部探针,本来就是 backend 公开函数,
            # 直接 import 比 HTTP 代理更稳定(API 关闭也能测)。
            # 关联 spec: docs/superpowers/specs/2026-08-17-launcher-ocr-direct-design.md
            try:
                import os
                import sys
                # 把 backend app 加到 sys.path,确保 import app.services.diagnostics_ocr 找得到
                backend_root = self.project_root / "app" / "backend"
                backend_root_str = str(backend_root)
                if backend_root_str not in sys.path:
                    sys.path.insert(0, backend_root_str)
                # .env 在 project_root 而不是 backend 目录;pydantic-settings 默认从 cwd 找,
                # launcher cwd 是 project_root/launcher,所以显式指 env_file 让 Settings 加载 OCR_ENABLED 等。
                # 关联 spec: docs/superpowers/specs/2026-08-17-launcher-ocr-direct-design.md
                from app.services.diagnostics_ocr import probe_ocr
                from app.core.config import Settings
                env_file = self.project_root / ".env"
                settings = Settings(_env_file=str(env_file) if env_file.exists() else None)
                return probe_ocr(settings)
            except Exception as exc:
                import traceback
                logger.warning("OCR 诊断失败: %s", exc, exc_info=True)
                return {"ok": False, "reason": "probe_failed", "message": f"{type(exc).__name__}: {exc}"}

        @app.get("/logs/tail")
        def logs_tail(lines: int = 50):
            return {"lines": self.process_manager.get_logs_tail(lines)}

        return app
