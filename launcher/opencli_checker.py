"""OpenCLI 连接测试:调用 opencli doctor 检测连接状态。

关联 spec: docs/superpowers/specs/2026-08-10-one-click-packaging-design.md § 2.5
"""
from __future__ import annotations

import logging
import re
import subprocess
from dataclasses import dataclass

logger = logging.getLogger(__name__)

OPENCLI_DOWNLOAD_URL = "https://opencli.info/download"


@dataclass
class OpenCLIResult:
    """OpenCLI 测试结果。"""
    ok: bool
    version: str = ""
    reason: str = ""
    message: str = ""


def check_opencli(bin_path: str = "opencli", timeout: float = 10.0) -> OpenCLIResult:
    """测试 OpenCLI 连接。

    调用 `opencli doctor`,解析输出判断连接状态。
    """
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
        )
    except subprocess.TimeoutExpired:
        return OpenCLIResult(
            ok=False,
            reason="timeout",
            message=f"opencli doctor 超时({timeout}s),请检查 OpenCLIApp 是否正常运行",
        )

    output = (proc.stdout or "") + (proc.stderr or "")
    if proc.returncode == 0 and ("daemon: ok" in output or "extension: connected" in output):
        version_match = re.search(r"version[:\s]+([\d.]+)", output, re.IGNORECASE)
        version = version_match.group(1) if version_match else ""
        return OpenCLIResult(ok=True, version=version, message="连接正常")

    stderr = proc.stderr or ""
    stdout = proc.stdout or ""
    if "daemon not running" in stderr or "daemon not running" in stdout:
        return OpenCLIResult(
            ok=False,
            reason="daemon_not_running",
            message="OpenCLIApp 未启动,请打开 OpenCLIApp 应用",
        )
    if "extension not connected" in stderr or "extension not connected" in stdout:
        return OpenCLIResult(
            ok=False,
            reason="extension_not_connected",
            message="未装 Chrome 扩展,在 OpenCLIApp 里点 [安装扩展]",
        )

    return OpenCLIResult(
        ok=False,
        reason="unknown_error",
        message=stderr.strip() or stdout.strip() or "未知错误",
    )
