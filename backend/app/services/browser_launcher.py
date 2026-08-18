"""浏览器拉起 + opencli 链路打开登录页。

关联 spec: docs/superpowers/specs/2026-08-16-dashboard-open-login-button-design.md

两条路径：
- ``open_xhs_login``：拉系统 Chrome 打开登录页(原行为,保留作为 fallback)
- ``open_xhs_login_via_opencli``：优先 ``opencli browser <profile> open <url>``,
  让 opencli daemon 管的 profile Chrome 打开登录页(用户机器上 profile 仍带 cookie),
  无 profile / daemon 未跑 → fallback 到 ``open_xhs_login``
"""
from __future__ import annotations

import logging
import shutil
import subprocess
import sys
from collections.abc import Callable
from typing import Any

logger = logging.getLogger(__name__)


class BrowserLaunchError(RuntimeError):
    pass


def _default_run(args: list[str], **kwargs: Any) -> Any:
    """subprocess.run 的默认注入点(便于测试替换)。"""
    kwargs.setdefault("check", False)
    kwargs.setdefault("capture_output", True)
    kwargs.setdefault("text", True)
    kwargs.setdefault("timeout", 30)
    return subprocess.run(args, **kwargs)


def open_xhs_login(
    settings,
    *,
    platform_name: str | None = None,
    run: Callable[..., Any] = _default_run,
) -> str:
    """拉系统 Chrome 打开小红书登录页(保留作为 fallback)。

    关联 spec: docs/superpowers/specs/2026-08-16-packaged-default-login-and-mainthread-window-design.md
    """
    platform_name = platform_name or sys.platform
    url = settings.xhs_login_url
    browser = settings.xhs_login_browser
    if platform_name == "darwin":
        command = ["open", "-a", browser, url]
    elif platform_name.startswith("win"):
        command = ["cmd", "/c", "start", "", browser, url]
    else:
        executable = "google-chrome" if browser.lower() == "google chrome" else browser
        command = [executable, url]
    try:
        run(command, check=True)
    except (OSError, subprocess.CalledProcessError) as exc:
        raise BrowserLaunchError(f"无法打开 Chrome，请手动访问 {url}") from exc
    return url


def _resolve_opencli_bin(settings) -> str | None:
    bin_name = (getattr(settings, "opencli_bin", "") or "opencli").strip() or "opencli"
    return shutil.which(bin_name)


def _extract_first_profile(daemon_status_text: str) -> str | None:
    """从 ``opencli daemon status`` 输出解析第一个 connected profile 名。

    输出格式(>=v1.8.5)：
        Daemon: running (PID 2423)
        Extension: connected (v1.0.22)
        Profiles: jjm94buu v1.0.22
        Port: 19825
    """
    for line in (daemon_status_text or "").splitlines():
        s = line.strip()
        if s.startswith("Profiles:"):
            parts = s.split(":", 1)[1].strip().split()
            return parts[0] if parts and parts[0] else None
    return None


def open_xhs_login_via_opencli(
    settings,
    *,
    run: Callable[..., Any] = _default_run,
    daemon_status_runner: Callable[..., Any] | None = None,
    fallback_runner: Callable[..., Any] | None = None,
    platform_name: str | None = None,
) -> tuple[str, str]:
    """优先走 opencli daemon 的 profile Chrome 打开登录页。

    返回 ``(url, source)``：
    - source=``opencli``：成功通过 ``opencli browser <profile> open <url>`` 打开
    - source=``system_chrome_fallback``：fallback 到系统 Chrome(open_xhs_login)

    触发 fallback 的条件：
    - opencli 二进制找不到
    - ``opencli daemon status`` 失败或超时
    - daemon status 输出解析不到 profile
    - ``opencli browser <profile> open`` 调用本身失败(此情况 raise BrowserLaunchError)
    """
    url = settings.xhs_login_url
    bin_path = _resolve_opencli_bin(settings)
    if not bin_path:
        logger.info("opencli 不在 PATH,fallback 到系统 Chrome")
        open_xhs_login(settings, platform_name=platform_name, run=fallback_runner or run)
        return url, "system_chrome_fallback"

    status_runner = daemon_status_runner or run
    try:
        status_proc = status_runner([bin_path, "daemon", "status"], timeout=5)
    except (OSError, subprocess.TimeoutExpired) as exc:
        logger.warning("opencli daemon status 调用失败 (%s),fallback 到系统 Chrome", exc)
        open_xhs_login(settings, platform_name=platform_name, run=fallback_runner or run)
        return url, "system_chrome_fallback"

    if getattr(status_proc, "returncode", 1) != 0:
        logger.warning("opencli daemon status rc=%s,fallback 到系统 Chrome", status_proc.returncode)
        open_xhs_login(settings, platform_name=platform_name, run=fallback_runner or run)
        return url, "system_chrome_fallback"

    profile = _extract_first_profile(getattr(status_proc, "stdout", "") or "")
    if not profile:
        logger.info("opencli daemon 未连任何 profile,fallback 到系统 Chrome")
        open_xhs_login(settings, platform_name=platform_name, run=fallback_runner or run)
        return url, "system_chrome_fallback"

    try:
        run([bin_path, "browser", profile, "open", url], timeout=15)
    except (OSError, subprocess.TimeoutExpired, subprocess.CalledProcessError) as exc:
        logger.warning("opencli browser open 失败 (%s),不再 fallback,提示用户手动访问", exc)
        raise BrowserLaunchError(
            f"无法通过 opencli 打开 Chrome,请手动访问 {url}（profile={profile}）"
        ) from exc

    logger.info("opencli browser %s open %s 成功", profile, url)
    return url, "opencli"