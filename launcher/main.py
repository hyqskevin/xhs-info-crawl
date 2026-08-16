"""启动器入口:PyWebView 窗口 + 进程管理 + 状态服务。

关联 spec:
- docs/superpowers/specs/2026-08-10-one-click-packaging-design.md § 2 + § 4
- docs/superpowers/specs/2026-08-16-packaged-frontend-static-serving-design.md
- docs/superpowers/specs/2026-08-16-launcher-password-visibility-design.md
"""
from __future__ import annotations

import logging
import sys
import threading
import uvicorn
from pathlib import Path

from launcher.env_bootstrap import (
    build_api_base_url,
    build_cors_origins,
    ensure_env_file,
    force_local_host,
    set_cache_env_vars,
    update_env_value,
)
from launcher.inject_app_config import inject_app_config
from launcher.password_recording import record_initial_password
from launcher.port_finder import find_available_port
from launcher.process_manager import ProcessManager
from launcher.pywebview_safety import run_main_loop, safe_pywebview_start
from launcher.status_server import StatusServer

logger = logging.getLogger(__name__)


def get_project_root() -> Path:
    """获取项目根目录(启动器所在目录的父目录)。"""
    return Path(__file__).parent.parent.resolve()


def get_venv_python(project_root: Path) -> Path:
    """获取便携 Python 解释器路径。"""
    if sys.platform == "darwin":
        return project_root / "runtime" / "venv" / "bin" / "python"
    else:
        return project_root / "runtime" / "venv" / "Scripts" / "python.exe"


def bootstrap_env(project_root: Path) -> tuple[int, int]:
    """找端口 + 写 API_BASE_URL,返回 (API 端口, Web 端口)。

    Web 端口从 5173 开始扫描,被占用跳到 5174... 直到 5199。
    如果开发模式下 vite dev 已占 5173,Web 端口会被推到 5174。

    注意:.env 的创建/初始化由调用方负责(在 main() 里),
    这样可以拿到 ensure_env_file 的返回值(自动生成的密码)。
    """
    env_path = project_root / ".env"

    # 1. 强制 API_HOST=127.0.0.1
    force_local_host(env_path)

    # 2. 设置缓存环境变量
    set_cache_env_vars(project_root)

    # 3. 找 API 可用端口
    api_port = find_available_port(start=8001, end=8020)
    update_env_value(env_path, "API_PORT", str(api_port))

    # 4. 找 Web 可用端口(开发模式 5173 通常已被 vite 占用)
    web_port = find_available_port(start=5173, end=5199)
    update_env_value(env_path, "WEB_PORT", str(web_port))

    # 5. 写 API_BASE_URL,前端通过 __APP_CONFIG__ 读取
    update_env_value(env_path, "API_BASE_URL", f"http://127.0.0.1:{api_port}")

    return api_port, web_port


def main():
    """启动器主入口。

    流程:
    1. 初始化 .env(记录自动生成的初始密码到文件)
    2. 找端口 + 注入前端配置
    3. 启动状态服务(后台线程)
    4. 启动子进程(API/Worker/Beat/Web)
    5. 把 PyWebView 启动放到 daemon thread(失败不影响子进程)
    6. 主线程 keep alive,直到收到 KeyboardInterrupt 或显式清理
    """
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

    project_root = get_project_root()
    venv_python = get_venv_python(project_root)

    logger.info("启动器启动,项目根目录: %s", project_root)

    # 1. 初始化 .env(返回自动生成的密码,如果本次调用真生成了)
    env_path = project_root / ".env"
    auto_pwd = ensure_env_file(env_path, project_root / ".env.example")
    if auto_pwd:
        record_initial_password(project_root, auto_pwd, auto_generated=True)
        logger.warning(
            "已自动生成初始 admin 密码: %s 写入文件: data/run/INITIAL_ADMIN_PASSWORD.txt",
            auto_pwd,
        )
        logger.warning("登录后请到「操作账号」立即修改密码")

    # 2. 找端口 + 写 API_BASE_URL
    api_port, web_port = bootstrap_env(project_root)
    logger.info("API 端口: %d, Web 端口: %d", api_port, web_port)

    # 3. 注入前端配置(把端口写到 index.html,前端运行时读取 __APP_CONFIG__)
    frontend_dist = project_root / "app" / "frontend" / "dist"
    if frontend_dist.exists():
        inject_app_config(dist=frontend_dist, env_file=env_path)
        logger.info("前端配置已注入到 %s", frontend_dist / "index.html")
    else:
        logger.warning("前端 dist 不存在,跳过 inject: %s", frontend_dist)

    # 3. 创建进程管理器
    pm = ProcessManager(project_root=project_root, venv_python=venv_python)

    # 4. 创建状态服务(同时传 api_base_url 和 web_base_url)
    status_server = StatusServer(
        process_manager=pm,
        project_root=project_root,
        venv_python=venv_python,
        api_base_url=f"http://127.0.0.1:{api_port}",
        web_base_url=f"http://127.0.0.1:{web_port}",
    )

    # 5. 启动状态服务(在后台线程)
    status_port = find_available_port(start=9000, end=9020)
    status_thread = threading.Thread(
        target=lambda: uvicorn.run(status_server.app, host="127.0.0.1", port=status_port, log_level="warning"),
        daemon=True,
    )
    status_thread.start()
    logger.info("状态服务启动: http://127.0.0.1:%d", status_port)

    # 6. 启动后端 + 前端静态服务
    pm.start_service("api")
    pm.start_service("worker")
    pm.start_service("beat")
    pm.start_service("web")

    # 7. 把 PyWebView 启动放到 daemon thread
    # 失败不影响主进程和子进程(子进程独立存活,用户仍可通过浏览器访问 API)
    ui_dist = project_root / "launcher" / "ui" / "dist"
    if ui_dist.exists():
        url = f"file://{ui_dist / 'index.html'}?statusPort={status_port}&apiPort={api_port}&webPort={web_port}"
    else:
        url = f"data:text/html,<html><body><h1>启动器 UI 未构建</h1><p>状态服务: http://127.0.0.1:{status_port}</p></body></html>"

    class Api:
        def __init__(self, project_root: Path):
            self._project_root = project_root

        def open_url(self, url: str) -> None:
            import webbrowser
            webbrowser.open(url)

        def open_dir(self, path: str) -> str:
            """在系统文件管理器(Finder/Explorer)中打开目录。返回绝对路径。"""
            import subprocess
            target = Path(path)
            if not target.is_absolute():
                target = self._project_root / path
            target = target.resolve()
            if not target.exists():
                raise FileNotFoundError(f"路径不存在: {target}")
            if sys.platform == "darwin":
                subprocess.Popen(["open", str(target)])
            elif sys.platform.startswith("win"):
                subprocess.Popen(["explorer", str(target)])
            else:
                subprocess.Popen(["xdg-open", str(target)])
            return str(target)

        def exit(self) -> None:
            """退出启动器:用户点 PyWebView 窗口的「退出」按钮时调用。"""
            import webview as _wv
            if _wv.windows:
                for w in _wv.windows:
                    w.destroy()

    def create_pywebview_window():
        import webview
        api = Api(project_root=project_root)
        return webview.create_window(
            "小红书活动信息抓取系统",
            url,
            width=900,
            height=700,
            min_size=(720, 600),
            js_api=api,
        )

    webview_thread = threading.Thread(
        target=lambda: safe_pywebview_start(
            window_creator=create_pywebview_window,
            log=lambda msg: logger.warning(msg),
        ),
        daemon=True,
        name="pywebview-window",
    )
    webview_thread.start()
    logger.info("PyWebView 窗口已在后台线程启动(daemon),失败不影响主进程")

    # 8. 主线程 keep alive,直到 KeyboardInterrupt(开发模式 Ctrl-C)或 SIGTERM
    # PyWebView 失败/退出不影响子进程继续运行
    try:
        run_main_loop(
            on_iteration=lambda: None,
            exception_log=lambda msg: logger.warning(msg),
        )
    except KeyboardInterrupt:
        logger.info("收到 KeyboardInterrupt,准备退出")
    finally:
        logger.info("启动器退出,清理子进程")
        pm.cleanup()


if __name__ == "__main__":
    main()
