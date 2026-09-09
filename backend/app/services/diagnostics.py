"""仪表盘连接检测：opencli 二进制 / 小红书 whoami / Chrome CDP。

关联 spec: docs/superpowers/specs/2026-08-03-diagnostics-panel-design.md

每个 probe 是独立的轻量探测，失败原因分类可读。供 ``app.api.v1.diagnostics`` 路由调用。
"""
from __future__ import annotations

import json
import logging
import re
import shutil
import socket
import subprocess
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse

from app.core.config import Settings
from app.services.crawler import AuthenticationRequired, OpenCLIError, OpenCLITimeout
from app.services.opencli_adapter import OpenCLIAdapter


logger = logging.getLogger(__name__)


def _iso_now() -> str:
    from app.core.timeutil import now_cn
    return now_cn().isoformat()


def _safe_version(bin_path: str, timeout: float = 5.0) -> str | None:
    """尝试 ``opencli --version``；失败返回 None，不抛。"""
    try:
        proc = subprocess.run(
            [bin_path, "--version"],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    out = (proc.stdout or proc.stderr or "").strip()
    return out or None


# ≥此版本走 daemon+扩展模式检测；<此版本走 CDP 端口检测。
DAEMON_MODE_MIN_VERSION: tuple[int, int, int] = (1, 8, 5)

_VERSION_RE = re.compile(r"(\d+)\.(\d+)\.(\d+)")


def _parse_opencli_version(text: str | None) -> tuple[int, int, int] | None:
    """从 ``opencli --version`` 输出提取语义化版本。

    支持 ``v1.8.5`` / ``1.8.5`` / ``opencli v1.8.5`` 等格式。
    返回 ``(major, minor, patch)`` 或 None（无法解析）。
    """
    if not text:
        return None
    match = _VERSION_RE.search(text)
    if not match:
        return None
    return (int(match.group(1)), int(match.group(2)), int(match.group(3)))


def _parse_daemon_status(text: str) -> dict[str, Any]:
    """解析 ``opencli daemon status`` 输出。"""
    result: dict[str, Any] = {
        "daemon_running": None,
        "extension_connected": None,
        "profiles": [],
        "daemon_port": None,
    }
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("Daemon: running"):
            result["daemon_running"] = True
        elif line.startswith("Daemon: stopped") or line.startswith("Daemon: not running"):
            result["daemon_running"] = False
        elif line.startswith("Extension: disconnected"):
            result["extension_connected"] = False
        elif line.startswith("Extension:") and "profiles connected" in line:
            # opencli ≥1.8.5 多 profile 格式："Extension: 3 profiles connected, none selected"
            result["extension_connected"] = True
        elif line.startswith("Extension: connected"):
            result["extension_connected"] = True
        elif line.startswith("Profiles:"):
            profiles_part = line.split(":", 1)[1].strip()
            if profiles_part:
                # 每个形如 "jjm94buu v1.0.22"，取首个 token 作为 profile id
                result["profiles"] = [p.split()[0] for p in profiles_part.split(",") if p.split()]
        elif line.startswith("Port:"):
            try:
                result["daemon_port"] = int(line.split(":", 1)[1].strip())
            except (IndexError, ValueError):
                pass
    return result


def _probe_daemon(bin_path: str, timeout: float = 5.0) -> dict[str, Any]:
    """运行 ``opencli daemon status``，返回 ``{success, output}``。"""
    try:
        proc = subprocess.run(
            [bin_path, "daemon", "status"],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return {"success": False, "output": None}
    return {"success": proc.returncode == 0, "output": proc.stdout}


def probe_opencli(settings: Settings) -> dict[str, Any]:
    """探测 opencli 二进制是否在 PATH。

    返回 ``{ok, bin, resolved, reason, version}``。
    """
    bin_name = (settings.opencli_bin or "opencli").strip() or "opencli"
    resolved = shutil.which(bin_name)
    if not resolved:
        return {
            "ok": False,
            "bin": bin_name,
            "resolved": None,
            "reason": f"opencli 不在 PATH，请设置 OPENCLI_BIN 环境变量指向 {bin_name} 的绝对路径",
            "version": None,
        }
    version = _safe_version(resolved)
    return {
        "ok": True,
        "bin": bin_name,
        "resolved": resolved,
        "reason": None,
        "version": version,
    }


def probe_xhs_login(settings: Settings, db=None) -> dict[str, Any]:
    """返回所有已启用账号的登录状态（读 DB 缓存，毫秒级，不做 opencli 探测）。

    设计（2026-09-03 规模化改造）：20+ 账号场景下串行 opencli 探测（每个最多 8s）
    需 160s+，超过前端 axios 超时。snapshot 只读 DB 的 login_status 缓存；
    实际探测由前端逐账号并行调 ``POST /xhs-accounts/{id}/check-login``，
    查完一个更新一个，互不阻塞。

    返回 ``{logged_in, reason, accounts}``；``accounts`` 每项含
    ``{account_name, session_name, logged_in, user_id, username}``。
    """
    from app.models.xhs_account import XhsAccount
    from sqlalchemy import select

    accounts_rows = []
    if db is not None:
        accounts_rows = list(db.scalars(
            select(XhsAccount).where(XhsAccount.enabled.is_(True)).order_by(XhsAccount.priority, XhsAccount.id)
        ).all())

    accounts_status: list[dict[str, Any]] = []
    for acc in accounts_rows:
        accounts_status.append({
            "account_name": acc.name,
            "session_name": acc.session_name,
            "logged_in": acc.login_status == "logged_in",
            "user_id": acc.platform_user_id,
            "username": None,
        })

    logged_in = any(a["logged_in"] for a in accounts_status)
    return {
        "logged_in": logged_in,
        "reason": None if logged_in else ("auth_required" if accounts_rows else None),
        "accounts": accounts_status,
    }


def _cdp_host_port(endpoint: str) -> tuple[str, int] | None:
    parsed = urlparse(endpoint)
    host = parsed.hostname
    port = parsed.port
    if not host or not port:
        return None
    return host, port


def _probe_cdp(endpoint: str, timeout: float = 2.0) -> tuple[bool, str | None]:
    addr = _cdp_host_port(endpoint)
    if not addr:
        return False, f"CDP 端点格式无效：{endpoint}"
    host, port = addr
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True, None
    except OSError as exc:
        return False, f"CDP 端点 {endpoint} 连接失败：{exc}"


def probe_xhs_pool(settings: Settings, db=None) -> dict[str, Any]:
    """探测浏览器连接：按 opencli 版本路由到 daemon 或 CDP 检测。

    版本 ≥(1,8,5) → daemon+扩展模式检测；
    版本 <(1,8,5) → CDP 端口检测；
    版本解析失败 → 能力探测兜底（先 daemon，失败再 CDP）。

    返回 ``{mode, version, version_tuple, daemon_running, extension_connected,
    profiles, daemon_port, cdp_endpoint, cdp_reachable, sessions,
    accounts, reason}``：``accounts`` 字典 key 是 session_name，value 含
    ``{account_name, chrome_alive, extension_connected}``（2026-09-03 加）
    """
    from app.models.xhs_account import XhsAccount
    from sqlalchemy import select

    bin_name = (settings.opencli_bin or "opencli").strip() or "opencli"
    resolved = shutil.which(bin_name)

    base: dict[str, Any] = {
        "mode": "unknown",
        "version": None,
        "version_tuple": None,
        "daemon_running": None,
        "extension_connected": None,
        "profiles": [],
        "daemon_port": None,
        "cdp_endpoint": None,
        "cdp_reachable": None,
        "sessions": [],
        "accounts": {},
        "reason": None,
    }

    # 收集每账号扩展状态（2026-09-03）：chrome_pool.get() 不启动新实例，仅检查 alive
    if db is not None:
        try:
            from app.services.chrome_pool import get_global_chrome_pool
            pool = get_global_chrome_pool()
        except Exception:
            pool = None
        if pool is not None:
            accounts_rows = list(db.scalars(
                select(XhsAccount).where(XhsAccount.enabled.is_(True))
                .order_by(XhsAccount.priority, XhsAccount.id)
            ).all())
            for acc in accounts_rows:
                instance = pool.get(acc.session_name)
                alive = bool(instance is not None and instance.alive())
                base["accounts"][acc.session_name] = {
                    "account_name": acc.name,
                    "chrome_alive": alive,
                    # 单 daemon 多 profile：ext 是否连上要看该 session 是否在 profiles 列表
                    "extension_connected": alive,
                }

    if not resolved:
        base["reason"] = f"opencli 不在 PATH，请设置 OPENCLI_BIN 环境变量指向 {bin_name} 的绝对路径"
        return base

    version_raw = _safe_version(resolved)
    version_tuple = _parse_opencli_version(version_raw)
    base["version"] = version_raw
    base["version_tuple"] = list(version_tuple) if version_tuple else None

    # 确定模式：版本驱动为主，版本解析失败时能力探测兜底
    daemon_output: str | None = None
    if version_tuple is not None:
        use_daemon = version_tuple >= DAEMON_MODE_MIN_VERSION
    else:
        # 版本解析失败 → 先试 daemon status
        daemon_result = _probe_daemon(resolved)
        daemon_output = daemon_result["output"] if daemon_result["success"] else None
        use_daemon = daemon_output is not None

    if use_daemon:
        base["mode"] = "daemon"
        output = daemon_output
        if output is None:  # 版本路由路径需主动获取
            daemon_result = _probe_daemon(resolved)
            if not daemon_result["success"] or not daemon_result["output"]:
                base["reason"] = "opencli daemon status 命令失败"
                return base
            output = daemon_result["output"]
        parsed = _parse_daemon_status(output)
        base["daemon_running"] = parsed["daemon_running"]
        base["extension_connected"] = parsed["extension_connected"]
        base["profiles"] = parsed["profiles"]
        base["daemon_port"] = parsed["daemon_port"]
        if not parsed["daemon_running"]:
            base["reason"] = "daemon 未运行"
        elif not parsed["extension_connected"]:
            base["reason"] = "浏览器扩展未连接"
        elif not parsed["profiles"]:
            base["reason"] = "未找到已连接的浏览器 profile"
        # 修正每账号 extension_connected：只在全局 extension_connected 为 True 且 Chrome alive 时为 True
        if base["accounts"]:
            for sess, info in base["accounts"].items():
                info["extension_connected"] = bool(
                    info["chrome_alive"] and parsed["extension_connected"]
                )
        return base

    # CDP 模式（版本 <1.8.5 或兜底路径 daemon 失败）
    endpoint = settings.opencli_cdp_endpoint
    base["cdp_endpoint"] = endpoint
    reachable, reason = _probe_cdp(endpoint)
    base["cdp_reachable"] = reachable
    sessions: list[dict[str, Any]] = []
    if reachable:
        try:
            proc = subprocess.run(
                [resolved, "browser", "list", "--format", "json"],
                capture_output=True,
                text=True,
                timeout=5.0,
                check=False,
            )
            out = (proc.stdout or "").strip()
            if out:
                parsed_json = json.loads(out)
                if isinstance(parsed_json, list):
                    sessions = [row for row in parsed_json if isinstance(row, dict)]
                elif isinstance(parsed_json, dict) and "sessions" in parsed_json and isinstance(parsed_json["sessions"], list):
                    sessions = [row for row in parsed_json["sessions"] if isinstance(row, dict)]
        except (OSError, subprocess.TimeoutExpired, json.JSONDecodeError) as exc:
            logger.info("probe_xhs_pool browser list 解析失败：%s", exc)
    base["sessions"] = sessions
    base["reason"] = reason
    # 兜底路径下 CDP 也不可达 → mode=unknown
    if version_tuple is None and not reachable:
        base["mode"] = "unknown"
    else:
        base["mode"] = "cdp"
    return base


def probe_snapshot(settings: Settings, db=None) -> dict[str, Any]:
    """三合一聚合，任一 probe 异常都被隔离不影响其它段。"""
    sections: dict[str, dict[str, Any]] = {}
    for name, fn in (
        ("opencli", probe_opencli),
        ("xhs_login", lambda s: probe_xhs_login(s, db=db)),
        ("xhs_pool", lambda s: probe_xhs_pool(s, db=db)),
    ):
        try:
            sections[name] = fn(settings)
        except Exception as exc:  # pragma: no cover - 防御
            logger.warning("probe_snapshot %s unexpected error: %s", name, exc)
            sections[name] = {"ok": False, "reason": str(exc)}
    sections["checked_at"] = _iso_now()
    return sections