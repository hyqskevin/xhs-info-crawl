"""启动器入口:PyWebView 窗口 + 进程管理 + 状态服务。

关联 spec:
- docs/superpowers/specs/2026-08-10-one-click-packaging-design.md § 2 + § 4
- docs/superpowers/specs/2026-08-16-packaged-frontend-static-serving-design.md
- docs/superpowers/specs/2026-08-16-packaged-default-login-and-mainthread-window-design.md
"""
from __future__ import annotations

import atexit
import logging
import signal
import sys
import threading
import uvicorn
from pathlib import Path

from launcher.env_bootstrap import (
    ensure_env_file,
    force_local_host,
    set_cache_env_vars,
    update_env_value,
)
from launcher.inject_app_config import inject_app_config
from launcher.port_finder import find_available_port
from launcher.process_manager import ProcessManager
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


class Api:
    """PyWebView 暴露给前端 JS 的接口(open_url / open_dir / exit / get_status_port)。"""

    def __init__(self, project_root: Path):
        self._project_root = project_root
        # 由 main() 在 launcher status_server 起来后注入;前端 JS 用这个拿 status API 端口
        self._status_port: int | None = None

    def set_status_port(self, port: int) -> None:
        """由 main() 在 status_server 启动后调用,前端 JS 通过 pywebview.api.get_status_port() 获取。"""
        self._status_port = port

    def get_status_port(self) -> int:
        """前端 JS 用这个方法拿到 launcher status_server 的端口,
        比 query string 可靠(macOS PyWebView 不一定把 query string 传给 window.location.search)。
        关联: docs/superpowers/specs/2026-08-17-launcher-ui-baseurl-pywebview-design.md
        """
        if self._status_port is None:
            # 兜底:从 process_manager 实际状态推断
            return self._status_port or 0
        return self._status_port

    def open_url(self, url: str) -> None:
        import webbrowser
        webbrowser.open(url)

    def open_dir(self, path: str) -> str:
        """在系统文件管理器(Finder/Explorer)中打开目录。返回绝对路径。"""
        import os
        import subprocess
        # 展开 ~ → 用户主目录(launcher UI 推荐的存储路径以 ~ 开头)
        target = Path(os.path.expanduser(path))
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
        """退出启动器:用户点 PyWebView 窗口的「退出」按钮时调用。

        发 SIGTERM 给当前进程 → 触发 main.py 的 signal handler → pm.cleanup()。
        不直接 destroy 窗口,避免子进程被进程组信号链杀而无法 graceful shutdown。
        """
        import os
        os.kill(os.getpid(), signal.SIGTERM)


def run_gui_main_thread(url: str, project_root: Path, cleanup, status_port: int = 0, log=None) -> None:
    """在主线程运行 PyWebView 窗口(OSX 硬性要求),关窗/异常后调 cleanup。

    关联 spec: docs/superpowers/specs/2026-08-16-packaged-default-login-and-mainthread-window-design.md
    - macOS 上 PyWebView 必须在主线程创建 NSWindow 并跑事件循环,
      放 daemon 线程会抛 WebViewException(must be run on a main thread),窗口从不显示。
    - 窗口关闭(webview.start() 返回)或抛异常 → finally 调 cleanup 杀全部子进程,不留孤儿。
    - KeyboardInterrupt(Ctrl-C)由调用方的 signal handler 处理,这里不拦截。
    - status_port: 注入到 Api,前端 JS 用 pywebview.api.get_status_port() 拿到 launcher status API 端口。
      PyWebView macOS 不一定把 query string 传给 window.location.search,走 JS API 更可靠。
      关联: docs/superpowers/specs/2026-08-17-launcher-ui-baseurl-pywebview-design.md
    """
    try:
        import webview

        api = Api(project_root=project_root)
        api.set_status_port(status_port)
        webview.create_window(
            "小红书活动信息抓取系统",
            url,
            width=900,
            height=700,
            min_size=(720, 600),
            js_api=api,
        )
        webview.start()
    except Exception as exc:
        msg = f"PyWebView 运行异常: {exc}"
        logger.exception(msg)
        if log is not None:
            log(msg)
    finally:
        cleanup()


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
    1. 初始化 .env(SECRET_KEY 兜底,不生成随机密码)
    2. 找端口 + 注入前端配置
    3. 启动状态服务(后台线程)
    4. 启动子进程(API/Worker/Beat/Web)
    5. 主线程跑 PyWebView(macOS 硬性要求),关窗/异常后 cleanup 全部子进程
    """
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

    project_root = get_project_root()
    venv_python = get_venv_python(project_root)

    logger.info("启动器启动,项目根目录: %s", project_root)

    # 1. 初始化 .env(SECRET_KEY 兜底;admin 密码统一默认 Admin@123,由后端建库播种)
    env_path = project_root / ".env"
    ensure_env_file(env_path, project_root / ".env.example")

    # 2. 找端口 + 写 API_BASE_URL
    api_port, web_port = bootstrap_env(project_root)
    logger.info("API 端口: %d, Web 端口: %d", api_port, web_port)

    # 2.5 探测 opencli daemon 端口(仅探测,不写 .env;opencli v1.8.6+ 已强制 19825)
    try:
        from launcher.opencli_port_detector import bootstrap_daemon_port
        detected = bootstrap_daemon_port()
        if detected:
            logger.info("opencli daemon 端口探测: %d", detected)
    except Exception as exc:
        logger.warning("opencli daemon 端口探测失败(非致命): %s", exc)

    # 3. 注入前端配置(把端口写到 index.html,前端运行时读取 __APP_CONFIG__)
    frontend_dist = project_root / "app" / "frontend" / "dist"
    if frontend_dist.exists():
        inject_app_config(dist=frontend_dist, env_file=env_path)
        logger.info("前端配置已注入到 %s", frontend_dist / "index.html")
    else:
        logger.warning("前端 dist 不存在,跳过 inject: %s", frontend_dist)

    # 3. 创建进程管理器
    pm = ProcessManager(project_root=project_root, venv_python=venv_python)

    # 3.1 注册退出时的清理钩子
    # 关联 spec: docs/superpowers/specs/2026-08-16-launcher-cleanup-on-exit-design.md § 2-3
    # atexit:正常退出 / 未捕获异常 / sys.exit()
    # signal handler:SIGTERM / SIGINT / SIGHUP
    atexit.register(pm.cleanup)

    def _signal_handler(signum, frame):  # noqa: ARG001
        signame = signal.Signals(signum).name if isinstance(signum, int) else str(signum)
        logger.info("收到信号 %s,清理子进程后退出", signame)
        pm.cleanup()
        sys.exit(0)

    # SIGTERM:osascript "tell application to quit" / kill PID
    # SIGINT:开发模式 Ctrl-C
    # SIGHUP:终端关闭(双击 .app 不会触发,但 start.sh 后台跑时会)
    for sig in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
        try:
            signal.signal(sig, _signal_handler)
        except (ValueError, OSError):
            # 某些平台/线程下无法注册(如子线程),忽略
            pass

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

    # 5.5 status_port 已经找到,等 run_gui_main_thread 创建 Api 后注入
    # (Api 在 run_gui_main_thread 里创建,因为 PyWebView 必须在主线程用)

    # 6. 启动后端 + 前端静态服务
    pm.start_service("api")
    pm.start_service("worker")
    pm.start_service("beat")
    pm.start_service("web")

    # 7. 主线程跑 PyWebView(macOS 硬性要求,GUI 必须主线程)
    # 窗口关闭(webview.start() 返回)或抛异常 → run_gui_main_thread 的 finally 调 pm.cleanup()
    # 杀掉 API/Worker/Beat/Web 全部子进程,释放端口,不留孤儿进程。
    ui_dist = project_root / "launcher" / "ui" / "dist"
    if ui_dist.exists():
        url = f"file://{ui_dist / 'index.html'}?statusPort={status_port}&apiPort={api_port}&webPort={web_port}"
    else:
        url = f"data:text/html,<html><body><h1>启动器 UI 未构建</h1><p>状态服务: http://127.0.0.1:{status_port}</p></body></html>"

    run_gui_main_thread(url, project_root, pm.cleanup, status_port=status_port, log=lambda msg: logger.warning(msg))


if __name__ == "__main__":
    main()
