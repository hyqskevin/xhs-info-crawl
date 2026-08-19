"""Chrome 实例池：为每个 XhsAccount 启动一个独立 Chrome 进程。

每个实例：
- 独立 --user-data-dir（隔离 cookie/历史/缓存）
- 独立 --remote-debugging-port（crawler 通过 OPENCLI_CDP_ENDPOINT 路由）
- 独立生命周期（release 时 SIGKILL）

绕开 opencli Browser Bridge 的多 profile 限制，真正实现账号级隔离。
关联 spec: docs/superpowers/specs/2026-08-12-chrome-pool-design.md
"""
from __future__ import annotations

import logging
import os
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

# CDP 默认起始端口；如有冲突由 OS 分配，并回写到 instance.port
_CDP_PORT_START = 9223
_CDP_PORT_RANGE = 100  # 9223-9322 范围内分配
_CDP_READY_TIMEOUT_S = 10

# 跨平台 Chrome 自动检测候选路径。resolve_chrome_bin 在 Settings.chrome_bin 找不到时扫描这里。
# 用户依然可以通过 Settings / .env 覆盖为任何自定义绝对路径。

# Linux / macOS PATH 上的可执行文件名（shutil.which 解析）
_BIN_NAMES = (
    "google-chrome",
    "google-chrome-stable",
    "chromium",
    "chromium-browser",
    "chrome",
)

# 候选路径模板：(Path.glob 模式, 期望 basename)。自动检测会用 _detect_chrome_bin 自动扫描。
_LINUX_DIRS = ("/usr/bin", "/usr/local/bin", "/opt/google/chrome", "/snap/bin")
_MACOS_APP_GLOBS = (
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Google Chrome Canary.app/Contents/MacOS/Google Chrome Canary",
    str(Path.home() / "Applications/Google Chrome.app/Contents/MacOS/Google Chrome"),  # path-policy-exempt: read-only home probe
)
_WINDOWS_GLOBS = (
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    str(Path.home() / "AppData/Local/Google/Chrome/Application/chrome.exe"),  # path-policy-exempt: read-only home probe
)


class ChromeLaunchError(RuntimeError):
    """Chrome 实例启动失败（可恢复：用户可重试或排查 Chrome 路径）。"""


@dataclass
class ChromeInstance:
    """一个 Chrome 实例（一个 XhsAccount 对应一个）。"""

    session_name: str
    port: int
    user_data_dir: Path
    process: subprocess.Popen

    @property
    def cdp_endpoint(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    def alive(self) -> bool:
        return self.process.poll() is None


class ChromePool:
    """管理 Chrome 实例的生命周期。

    用法：
        pool = ChromePool(chrome_bin=..., base_user_data_dir=Path('./data/chrome-pool'))
        a = pool.acquire('xhs-a')  # 启动 Chrome for 账号 A
        b = pool.acquire('xhs-b')  # 启动 Chrome for 账号 B
        ... # crawler 通过 a.cdp_endpoint 发请求
        pool.release_all()  # 全部 kill
    """

    def __init__(
        self,
        chrome_bin: str,
        base_user_data_dir: Path,
        cdp_port_start: int = _CDP_PORT_START,
    ) -> None:
        # chrome_bin 懒解析：仅在 acquire() 时调 resolve_chrome_bin，
        # 便于构造期 monkeypatch + 错误延后到启动 Chrome 时才报。
        self._chrome_bin = chrome_bin
        self._base_user_data_dir = Path(base_user_data_dir)
        self._base_user_data_dir.mkdir(parents=True, exist_ok=True)
        self._cdp_port_start = cdp_port_start
        self._instances: dict[str, ChromeInstance] = {}
        self._next_port_offset = 0

    def acquire(self, session_name: str) -> ChromeInstance:
        """获取（或启动）该 session_name 对应的 Chrome 实例。已存在则直接复用。"""
        if session_name in self._instances:
            inst = self._instances[session_name]
            if inst.alive():
                return inst
            # 已死：清理 + 重新启动
            self._safe_kill(inst.process)
            self._instances.pop(session_name, None)

        if not Path(self._chrome_bin).exists():
            # 懒解析：自动检测 chrome_bin（PATH 名 / 平台常见安装位置）
            self._chrome_bin = resolve_chrome_bin(self._chrome_bin)
            if not Path(self._chrome_bin).exists():
                raise ChromeLaunchError(
                    f"chrome 二进制不存在：{self._chrome_bin!r}"
                    "（请确认 Chrome 已安装或更新 Settings.chrome_bin）"
                )

        port = self._next_port_offset % _CDP_PORT_RANGE + self._cdp_port_start
        self._next_port_offset += 1
        user_data_dir = self._base_user_data_dir / session_name
        user_data_dir.mkdir(parents=True, exist_ok=True)

        proc = self._launch(port=port, user_data_dir=user_data_dir)
        instance = ChromeInstance(
            session_name=session_name,
            port=port,
            user_data_dir=user_data_dir,
            process=proc,
        )
        self._instances[session_name] = instance
        self._wait_cdp_ready(instance)
        return instance

    def release(self, session_name: str) -> None:
        """释放指定 session_name 的 Chrome 实例（kill 子进程）。"""
        inst = self._instances.pop(session_name, None)
        if inst is None:
            return
        self._safe_kill(inst.process)

    def release_all(self) -> None:
        """释放所有 Chrome 实例。多次调用安全。"""
        for name in list(self._instances.keys()):
            self.release(name)

    def get(self, session_name: str) -> ChromeInstance | None:
        """已 acquire 的实例（不启动新实例）。"""
        return self._instances.get(session_name)

    def _launch(self, port: int, user_data_dir: Path) -> subprocess.Popen:
        cmd = [
            self._chrome_bin,
            "--headless=new=new",
            "--no-sandbox",
            "--disable-gpu",
            f"--remote-debugging-port={port}",
            f"--user-data-dir={user_data_dir}",
            "about:blank",
        ]
        try:
            return subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                stdin=subprocess.DEVNULL,
            )
        except FileNotFoundError as exc:
            raise ChromeLaunchError(f"无法启动 Chrome：{exc}") from exc

    def _wait_cdp_ready(self, instance: ChromeInstance, timeout: float = _CDP_READY_TIMEOUT_S) -> None:
        """轮询 CDP /json/version 直到就绪或超时。仅记录警告，不抛错（crawler 调 opencli 时仍会拿到错误）。"""
        import urllib.request
        import urllib.error

        # 允许测试桩短路：环境变量 OPENCLI_SKIP_CDP_READY=1 跳过 CDP 健康检查
        if os.environ.get("OPENCLI_SKIP_CDP_READY") == "1":
            return
        deadline = time.monotonic() + timeout
        url = f"{instance.cdp_endpoint}/json/version"
        while time.monotonic() < deadline:
            try:
                with urllib.request.urlopen(url, timeout=1) as resp:
                    if resp.status == 200:
                        return
            except (urllib.error.URLError, ConnectionError, OSError):
                time.sleep(0.2)
        logger.warning("Chrome 实例 %s 的 CDP 端点 %s 在 %ss 内未就绪", instance.session_name, instance.cdp_endpoint, timeout)

    @staticmethod
    def _safe_kill(proc: subprocess.Popen) -> None:
        if proc.poll() is None:
            try:
                proc.kill()
            except ProcessLookupError:
                pass
        try:
            proc.wait(timeout=2)
        except subprocess.TimeoutExpired:
            pass


# ── 全局单例（API 与 crawl_task 共享 ChromePool）──────────────────────────

_global_pool: ChromePool | None = None


def get_global_chrome_pool() -> ChromePool:
    """获取全局 ChromePool 单例（懒初始化）。

    用途：
    - API 端点（check-login）启动 Chrome 实例让用户扫码
    - crawl_task 任务启动时复用同池中的 Chrome

    何时释放：仅后端进程退出时（atexit）或显式调用 shutdown_global_chrome_pool()。
    """
    global _global_pool
    if _global_pool is None:
        from app.core.config import get_settings
        settings = get_settings()
        _global_pool = ChromePool(
            chrome_bin=settings.chrome_bin,
            base_user_data_dir=settings.resolve_project_path(settings.chrome_user_data_dir),
        )
    return _global_pool


def shutdown_global_chrome_pool() -> None:
    """释放全局 ChromePool（kill 所有 Chrome 进程）。"""
    global _global_pool
    if _global_pool is not None:
        _global_pool.release_all()
        _global_pool = None


def resolve_chrome_bin(chrome_bin: str) -> str:
    """把 Settings.chrome_bin 解析为可执行绝对路径。

    解析顺序：
    1. 已是绝对路径且存在 → 直接返回（用户自定义路径生效）
    2. 当作 PATH 名 → shutil.which 解析
    3. 否则按 sys.platform 扫描常见安装位置（macOS .app / Linux / Windows Program Files）
    4. 全部失败 → 抛 ChromeLaunchError 带可读提示
    """
    if not chrome_bin:
        raise ChromeLaunchError(
            "chrome_bin 未配置（请在 Settings 或 .env 中设置 chrome_bin）"
        )
    # 1. 绝对路径存在 → 直接用
    candidate = Path(chrome_bin).expanduser()
    if candidate.is_absolute() and candidate.exists():
        return str(candidate.resolve())
    # 2. shutil.which 解析（PATH 名 / 相对路径）
    which_hit = shutil.which(chrome_bin)
    if which_hit:
        return str(Path(which_hit).resolve())
    # 3. 平台扫描
    detected = _detect_chrome_bin()
    if detected is not None:
        logger.info("chrome_bin=%r 未在 PATH 中找到,自动检测到 %s", chrome_bin, detected)
        return detected
    # 4. 失败
    raise ChromeLaunchError(
        f"chrome 二进制不存在：{chrome_bin!r}。"
        f"已扫描 PATH 与 {_platform_label()} 常见安装路径均未命中。"
        "请确认 Chrome 已安装，或在 Settings.chrome_bin 中指定绝对路径。"
    )


def _detect_chrome_bin() -> str | None:
    """按 sys.platform 自动扫描系统里的 Chrome。"""
    platform = sys.platform
    if platform == "darwin":
        return _detect_macos()
    if platform.startswith("win"):
        return _detect_windows()
    return _detect_linux()


def _detect_macos() -> str | None:
    # 1. shutil.which 各常见名
    for name in _BIN_NAMES:
        hit = shutil.which(name)
        if hit:
            return hit
    # 2. 标准 /Applications 路径
    for path in _MACOS_APP_GLOBS:
        p = Path(path).expanduser()
        if p.exists():
            return str(p.resolve())
    # 3. 扫描 /Applications 下任意 *Chrome*.app（自动检测非标准安装位置）
    for app_dir in ("/Applications", str(Path.home() / "Applications")):  # path-policy-exempt: read-only home probe
        base = Path(app_dir)
        if not base.exists():
            continue
        for app in base.glob("*Chrome*.app"):
            inner = app / "Contents" / "MacOS" / "Google Chrome"
            if not inner.exists():
                # 部分 .app 命名如 'Google Chrome Canary.app' 时二进制带 Canary 后缀
                for candidate in app.glob("Contents/MacOS/Google Chrome*"):
                    if candidate.is_file():
                        return str(candidate.resolve())
            else:
                return str(inner.resolve())
    return None


def _detect_linux() -> str | None:
    # 1. PATH
    for name in _BIN_NAMES:
        hit = shutil.which(name)
        if hit:
            return hit
    # 2. 常见系统目录
    for d in _LINUX_DIRS:
        for name in _BIN_NAMES:
            p = Path(d) / name
            if p.exists() and os.access(p, os.X_OK):
                return str(p.resolve())
    return None


def _detect_windows() -> str | None:
    # 1. PATH
    for name in _BIN_NAMES:
        hit = shutil.which(name + ".exe") or shutil.which(name)
        if hit:
            return hit
    # 2. 常见 Program Files 路径
    for path in _WINDOWS_GLOBS:
        p = Path(path).expanduser()
        if p.exists():
            return str(p.resolve())
    return None


def _platform_label() -> str:
    if sys.platform == "darwin":
        return "macOS"
    if sys.platform.startswith("win"):
        return "Windows"
    return "Linux"


import atexit as _atexit
_atexit.register(shutdown_global_chrome_pool)