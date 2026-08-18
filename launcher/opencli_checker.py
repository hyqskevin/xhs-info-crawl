"""OpenCLI 连接测试:调用 opencli doctor 检测连接状态。

关联 spec: docs/superpowers/specs/2026-08-10-one-click-packaging-design.md § 2.5
"""
from __future__ import annotations

import logging
import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

OPENCLI_DOWNLOAD_URL = "https://opencli.info/download"


@dataclass
class OpenCLIResult:
    """OpenCLI 测试结果。"""
    ok: bool
    version: str = ""
    reason: str = ""
    message: str = ""
    # 细粒度状态:每个子项独立判断
    daemon_running: bool = False
    daemon_port: int = 0
    chrome_running: bool = False
    chrome_path: str = ""
    extension_connected: bool = False
    extension_profile: str = ""


def _find_opencli() -> str | None:
    """查找 opencli 可执行文件。

    优先级:
    1. 系统 PATH(用户终端装的位置)
    2. ~/.local/bin/opencli(OpenCLIApp 默认安装位置)
    3. /usr/local/bin/opencli
    4. ~/Library/Application Support/opencli/bin/opencli
    """
    # 1. shutil.which 已经在 PATH 中查找
    found = shutil.which("opencli")
    if found:
        return found

    # 2. 显式检查常见 GUI 安装路径(macOS 上 .app 启动时 PATH 不完整)
    candidates = [
        Path.home() / ".local" / "bin" / "opencli",
        Path.home() / "Library" / "Application Support" / "opencli" / "bin" / "opencli",
        Path("/usr/local/bin/opencli"),
        Path("/opt/homebrew/bin/opencli"),
    ]
    for c in candidates:
        if c.exists() and os.access(c, os.X_OK):
            logger.info("在 %s 找到 opencli", c)
            return str(c)
    return None


def _resolve_daemon_port() -> int:
    """解析 opencli daemon 实际端口。

    优先级:
    1. 读 .env 的 OPENCLI_DAEMON_PORT
    2. 默认 19825(兼容老 .env)

    返回 19825 也作为兜底值;真正状态由 doctor 决定。
    """
    # 优先查 .env(launcher 可能写过)
    env_path = Path.home() / ".local" / "share" / "opencli" / ".env"
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8", errors="ignore").splitlines():
            line = line.strip()
            if line.startswith("OPENCLI_DAEMON_PORT="):
                try:
                    return int(line.split("=", 1)[1].strip())
                except ValueError:
                    pass
    return 19825


def _detect_chrome_running() -> tuple[bool, str]:
    """检测本机 Chrome 进程是否运行(macOS/Linux 通用)。"""
    import platform
    try:
        if platform.system() == "Darwin":
            proc = subprocess.run(
                ["pgrep", "-f", "Google Chrome"],
                capture_output=True, text=True, timeout=3,
            )
        elif platform.system() == "Windows":
            proc = subprocess.run(
                ["tasklist", "/FI", "IMAGENAME eq chrome.exe"],
                capture_output=True, text=True, timeout=3,
            )
            return ("chrome.exe" in proc.stdout.lower(), "chrome.exe")
        else:
            proc = subprocess.run(
                ["pgrep", "-f", "chrome"],
                capture_output=True, text=True, timeout=3,
            )
        running = bool(proc.stdout.strip())
        # 尝试找 Chrome 路径
        if platform.system() == "Darwin":
            path = "/Applications/Google Chrome.app"
            return (running, path if running else "")
        return (running, "")
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return (False, "")


def _parse_doctor_output(output: str) -> dict[str, object]:
    """从 opencli doctor 输出解析 daemon/extension/profile 信息。

    支持两种输出格式:
    - 老: "daemon: ok" / "extension: connected" / "profile: xxx"
    - 新: "[OK] Daemon: running on port 19825" / "[OK] Extension: connected (jjm94buu)"
    """
    text_lower = output.lower()
    result = {
        "daemon_running": False,
        "extension_connected": False,
        "profile": "",
    }

    # daemon
    if "daemon: ok" in text_lower or "[ok] daemon" in text_lower:
        result["daemon_running"] = True
    # 老格式: "daemon not running";新格式: "[FAIL] Daemon: not running"
    if "daemon not running" in text_lower or "[fail] daemon" in text_lower:
        result["daemon_running"] = False

    # extension
    if "extension: connected" in text_lower or "[ok] extension" in text_lower:
        result["extension_connected"] = True
    if "extension not connected" in text_lower or "[fail] extension" in text_lower:
        result["extension_connected"] = False

    # profile: "profile: jjm94buu" / "Extension: connected (jjm94buu)"
    profile_match = re.search(r"profile:\s*([\w-]+)", text_lower)
    if profile_match:
        result["profile"] = profile_match.group(1)
    else:
        bracket_match = re.search(r"connected\s*\(([\w-]+)\)", text_lower)
        if bracket_match:
            result["profile"] = bracket_match.group(1)

    return result


def check_opencli(timeout: float = 10.0) -> OpenCLIResult:
    """测试 OpenCLI 连接。

    调用 `opencli doctor`,解析输出判断连接状态。
    同时独立检测 daemon 端口 / Chrome 进程 / Extension 状态。
    """
    # 先独立探测 daemon 端口 + Chrome 进程
    daemon_port = _resolve_daemon_port()
    chrome_running, chrome_path = _detect_chrome_running()

    bin_path = _find_opencli()
    if not bin_path:
        return OpenCLIResult(
            ok=False,
            reason="not_installed",
            message="未安装 OpenCLI,请点 [下载 OpenCLI] 安装",
            daemon_port=daemon_port,
            chrome_running=chrome_running,
            chrome_path=chrome_path,
        )

    try:
        proc = subprocess.run(
            [bin_path, "doctor"],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except FileNotFoundError:
        return OpenCLIResult(
            ok=False,
            reason="not_installed",
            message="未安装 OpenCLI,请点 [下载 OpenCLI] 安装",
            daemon_port=daemon_port,
            chrome_running=chrome_running,
            chrome_path=chrome_path,
        )
    except subprocess.TimeoutExpired:
        return OpenCLIResult(
            ok=False,
            reason="timeout",
            message=f"opencli doctor 超时({timeout}s),请检查 OpenCLIApp 是否正常运行",
            daemon_port=daemon_port,
            chrome_running=chrome_running,
            chrome_path=chrome_path,
        )

    output = (proc.stdout or "") + (proc.stderr or "")
    parsed = _parse_doctor_output(output)

    # 兼容老版本输出
    daemon_ok_legacy = (
        "daemon: ok" in output.lower()
        or "[ok] daemon" in output.lower()
        or "everything looks good" in output.lower()
    )
    extension_ok_legacy = (
        "extension: connected" in output.lower()
        or "[ok] extension" in output.lower()
    )

    daemon_running = parsed["daemon_running"] or daemon_ok_legacy
    extension_connected = parsed["extension_connected"] or extension_ok_legacy

    if proc.returncode == 0 and (daemon_running or extension_connected):
        # 从 opencli v1.8.5 doctor (node v24.16.0) 提取版本
        version_match = re.search(r"opencli[^\d]*([\d.]+)", output, re.IGNORECASE)
        version = version_match.group(1) if version_match else ""

        # 总览 ok:daemon + extension + chrome 都 OK 才算完全 ok
        ok = daemon_running and extension_connected and chrome_running
        return OpenCLIResult(
            ok=ok,
            version=version,
            message="连接正常" if ok else "部分组件未就绪",
            daemon_running=daemon_running,
            daemon_port=daemon_port,
            chrome_running=chrome_running,
            chrome_path=chrome_path,
            extension_connected=extension_connected,
            extension_profile=parsed["profile"] or "",
        )

    stderr = proc.stderr or ""
    stdout = proc.stdout or ""
    if "daemon not running" in stderr or "daemon not running" in stdout:
        return OpenCLIResult(
            ok=False,
            reason="daemon_not_running",
            message="OpenCLIApp 未启动,请打开 OpenCLIApp 应用",
            daemon_port=daemon_port,
            daemon_running=False,
            chrome_running=chrome_running,
            chrome_path=chrome_path,
        )
    if "extension not connected" in stderr or "extension not connected" in stdout:
        return OpenCLIResult(
            ok=False,
            reason="extension_not_connected",
            message="未装 Chrome 扩展,在 OpenCLIApp 里点 [安装扩展]",
            daemon_port=daemon_port,
            chrome_running=chrome_running,
            chrome_path=chrome_path,
            extension_connected=False,
        )

    return OpenCLIResult(
        ok=False,
        reason="unknown_error",
        message=stderr.strip() or stdout.strip() or "未知错误",
        daemon_port=daemon_port,
        chrome_running=chrome_running,
        chrome_path=chrome_path,
    )
