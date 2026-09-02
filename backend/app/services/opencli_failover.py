"""opencli 主备账号切换（failover）执行器。

关联 spec: docs/superpowers/specs/2026-08-24-opencli-profile-multi-account-design.md §3.3

opencli 自身没有 retry / failover 钩子;主备账号切换要在 Python 脚本层用
subprocess.run + try/except + 数组遍历实现。本模块把"主 → 备链式重试"封成
一个同步原语,供定时任务脚本和后续 celery task 调用。

设计要点:
- 主账号 Popen exit 0 → 直接返,不再试备
- 主账号 Popen exit != 0 / TimeoutExpired → 试下一个备账号
- 备账号们按数组顺序遍历,直到有一个成功
- 全部失败 → 抛 AllAccountsFailed(全部账号的 stderr 摘要)
- command_builder(account) → list[str] 形 opencli 子命令 + 参数;
  调用方负责把 account.profile_alias / session_name 注入到 cmd(如
  ['opencli', '--profile', acct.profile_alias, 'xiaohongshu', 'search', ...])
- 本模块不依赖 OpenCLIAdapter(避免与 task_registry / bind_task 副作用耦合),
  纯 subprocess 通路。
"""
from __future__ import annotations

import asyncio
import logging
import subprocess
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)


class AllAccountsFailed(RuntimeError):
    """主 + 所有备账号 opencli 命令全部失败。"""

    def __init__(self, attempts: list[tuple[str, int, str]]):
        # attempts: [(session_name, returncode, stderr_tail), ...]
        self.attempts = attempts
        msg_lines = [f"主备 {len(attempts)} 个账号全部失败:"]
        for session_name, returncode, stderr_tail in attempts:
            msg_lines.append(
                f"  - {session_name}: exit={returncode} stderr={stderr_tail[:200]!r}"
            )
        super().__init__("\n".join(msg_lines))


@dataclass
class _AccountLike:
    """最小字段约束:command_builder 用得到 profile_alias + session_name。"""

    profile_alias: str
    session_name: str


def run_with_failover(
    command_builder: Callable[[Any], Sequence[str]],
    primary: Any,
    fallback_accounts: Sequence[Any] | None = None,
    timeout: float = 60.0,
) -> tuple[Any, Any]:
    """主 → 备账号链式重试 opencli 子命令。

    Args:
        command_builder: callable(account) -> sequence of str(opencli 子命令及参数)。
            调用方负责在 builder 内拼 ['opencli', '--profile', acct.profile_alias, ...]。
        primary: 主账号(必须有 .profile_alias / .session_name;或 duck-typing 同)
        fallback_accounts: 备账号列表(顺序遍历)
        timeout: 单次 Popen 超时(秒)

    Returns:
        (parsed_result, used_account): 第一个成功的子进程输出(json.loads 后的对象)
        和实际用到的账号(primary 或 fallback 之一)

    Raises:
        AllAccountsFailed: 主 + 所有备都失败
        FileNotFoundError: opencli 命令找不到
    """
    accounts: list[Any] = [primary] + list(fallback_accounts or [])
    attempts: list[tuple[str, int, str]] = []
    for acnt in accounts:
        cmd = list(command_builder(acnt))
        session_name = getattr(acnt, "session_name", "<unknown>")
        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
        except subprocess.TimeoutExpired as exc:
            attempts.append((session_name, -1, f"timeout after {timeout}s"))
            logger.warning("account %s timeout after %ss", session_name, timeout)
            continue
        except FileNotFoundError:
            # opencli 不可用 → 直接抛,无需试下一个(全都会 FileNotFoundError)
            raise
        if proc.returncode == 0:
            import json as _json
            stdout = (proc.stdout or "").strip()
            try:
                parsed: Any = _json.loads(stdout) if stdout else None
            except _json.JSONDecodeError:
                parsed = stdout
            return parsed, acnt
        attempts.append((session_name, proc.returncode, (proc.stderr or "").strip()))
        logger.warning(
            "account %s failed (exit=%s);try next",
            session_name,
            proc.returncode,
        )
    raise AllAccountsFailed(attempts)


# ── async 版本：celery 异步任务可直接 await ───────────────────────────────


async def arun_with_failover(
    command_builder: Callable[[Any], Sequence[str]],
    primary: Any,
    fallback_accounts: Sequence[Any] | None = None,
    timeout: float = 60.0,
) -> tuple[Any, Any]:
    """异步版 run_with_failover — asyncio.create_subprocess_exec 实现。"""
    accounts: list[Any] = [primary] + list(fallback_accounts or [])
    attempts: list[tuple[str, int, str]] = []
    for acnt in accounts:
        cmd = list(command_builder(acnt))
        session_name = getattr(acnt, "session_name", "<unknown>")
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            try:
                stdout_b, stderr_b = await asyncio.wait_for(
                    proc.communicate(), timeout=timeout
                )
            except asyncio.TimeoutError:
                proc.kill()
                await proc.wait()
                attempts.append((session_name, -1, f"timeout after {timeout}s"))
                logger.warning("account %s async timeout", session_name)
                continue
        except FileNotFoundError:
            raise
        if proc.returncode == 0:
            import json as _json
            stdout = (stdout_b.decode() if stdout_b else "").strip()
            try:
                parsed: Any = _json.loads(stdout) if stdout else None
            except _json.JSONDecodeError:
                parsed = stdout
            return parsed, acnt
        stderr_text = (stderr_b.decode() if stderr_b else "").strip()
        attempts.append((session_name, proc.returncode or -1, stderr_text))
        logger.warning("account %s async failed (exit=%s)", session_name, proc.returncode)
    raise AllAccountsFailed(attempts)