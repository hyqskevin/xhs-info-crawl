"""启动前清理孤儿 celery worker/beat。

被三处入口调用:
- scripts/dev-worker.sh / dev-beat.sh(dev 模式)
- launcher.process_manager.ProcessManager.start_service(.app 模式)

设计要点(spec §4):
- 命令行精确匹配:`celery.*-A app.tasks.celery_app.*(worker|beat)`
- 排除调用方自己 PID(不排除 PGID——dev 脚本 uv run wrapper 跟 shell 同 PGID)
- SIGTERM → 5s 超时 → SIGKILL 兜底
- 固定写日志到 log_path

关联 spec: docs/superpowers/specs/2026-08-22-worker-cleanup-on-startup-design.md
"""
from __future__ import annotations

import argparse
import logging
import os
import re
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger("launcher.orphan_cleanup")

_WORKER_PATTERN = re.compile(r"celery.*-A\s+app\.tasks\.celery_app(?:\:celery_app)?\s+worker")
_BEAT_PATTERN = re.compile(r"celery.*-A\s+app\.tasks\.celery_app(?:\:celery_app)?\s+beat")


def _list_matching_pids(role: str) -> list[int]:
    """用 ps -eo pid=,command= 列出匹配 role 的所有 PID。

    macOS / Linux 上 ps 都不默认截断 1024 字节的命令行,本项目命令行约 150 字节足够。
    """
    pattern = _WORKER_PATTERN if role == "worker" else _BEAT_PATTERN
    try:
        out = subprocess.run(
            ["ps", "-eo", "pid=,command="],
            capture_output=True, text=True, check=False, timeout=5,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        logger.warning("ps 调用失败: %s", exc)
        return []
    if out.returncode != 0:
        logger.warning("ps 返回非 0: %s", out.stderr.strip())
        return []
    pids: list[int] = []
    for line in out.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        # 格式: "  PID command..."
        parts = line.split(None, 1)
        if len(parts) != 2:
            continue
        try:
            pid = int(parts[0])
        except ValueError:
            continue
        cmdline = parts[1]
        if pattern.search(cmdline):
            pids.append(pid)
    return pids


def _is_pid_alive(pid: int) -> bool:
    """判断 PID 是否仍在"活动"状态。

    优先用 os.kill(pid, 0);对 zombie(unix 上 SIGTERM 后没被父进程 wait)会用
    ps 看 STAT 是否 Z(<defunct>)——zombie 已经死了,只是 PID 还被占着,不应再 SIGKILL。
    """
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True  # 其他用户进程,跟我们无关
    # POSIX 上 zombie:kill 0 仍返回 0。用 ps 检查 STAT。
    try:
        out = subprocess.run(
            ["ps", "-o", "stat=", "-p", str(pid)],
            capture_output=True, text=True, check=False, timeout=2,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return True  # 拿不到信号就保守认为还在
    stat = out.stdout.strip()
    # macOS 输出 "Z" / "Z+";Linux 也类似
    return not stat.startswith("Z")


def _wait_pid_gone(pid: int, timeout: float) -> bool:
    """轮询等待 PID 退出,timeout 秒内返回 True 表示已退。"""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if not _is_pid_alive(pid):
            return True
        time.sleep(0.1)
    return False


def _write_log(log_path: Path, fields: dict[str, Any]) -> None:
    """追加一行结构化日志(ISO 时间戳 + key=value 字段)。

    写日志失败不影响主流程(spec §4.4「不阻断启动」)。
    """
    log_path.parent.mkdir(parents=True, exist_ok=True)
    ts = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime()) + f",{int(time.time()*1000)%1000:03d}"
    parts = [ts, "INFO"] + [f"{k}={v}" for k, v in fields.items()]
    try:
        with log_path.open("a", encoding="utf-8") as fh:
            fh.write(" ".join(parts) + "\n")
    except OSError as exc:
        # 日志写失败不应阻断 cleanup 主流程
        logger.warning("写清理日志失败 (path=%s): %s", log_path, exc)


def cleanup_orphan_celery(
    role: str,
    log_path: Path,
    timeout_seconds: float = 5.0,
) -> dict[str, list[int]]:
    """清理 project_root 之外不属于当前进程的孤儿 worker/beat。

    返回 {"terminated":[...], "killed":[...]}。
    """
    start_mono = time.monotonic()
    self_pid = os.getpid()
    matched = _list_matching_pids(role)
    targets = [p for p in matched if p != self_pid]
    _write_log(log_path, {
        "event": "cleanup_start",
        "role": role,
        "self_pid": self_pid,
        "matched_pids": matched,
        "target_pids": targets,
    })

    terminated: list[int] = []
    killed: list[int] = []
    for pid in targets:
        try:
            os.kill(pid, signal.SIGTERM)
            _write_log(log_path, {"event": "sigterm", "role": role, "pid": pid})
        except ProcessLookupError:
            continue  # 已经退了,跳过
        except PermissionError:
            _write_log(log_path, {"event": "sigterm_denied", "role": role, "pid": pid})
            continue

        if _wait_pid_gone(pid, timeout_seconds):
            terminated.append(pid)
        else:
            try:
                os.kill(pid, signal.SIGKILL)
                killed.append(pid)
                _write_log(log_path, {"event": "sigkilled", "role": role, "pid": pid, "reason": "timeout"})
            except ProcessLookupError:
                terminated.append(pid)  # 在 SIGTERM 和 SIGKILL 之间退了

        # 试图 reap 自身的子进程 zomie,避免在 macOS/Linux 上 zombie 残留导致
        # 上层 `_pid_alive()` 用 `os.kill(pid, 0)` 时 zombie 仍返回 0 而误判存活。
        # 仅当 PID 真是当前进程的子进程时才能 reap;不是则 OSError EINVAL 忽略。
        try:
            os.waitpid(pid, os.WNOHANG)
        except (ChildProcessError, OSError):
            pass

    _write_log(log_path, {
        "event": "cleanup_done",
        "role": role,
        "terminated": terminated,
        "killed": killed,
        "duration_ms": int((time.monotonic() - start_mono) * 1000),
    })
    return {"terminated": terminated, "killed": killed}


def main() -> int:
    parser = argparse.ArgumentParser(
        description="清理同类残留 celery worker/beat 进程",
    )
    parser.add_argument("--role", required=True, choices=["worker", "beat"])
    parser.add_argument("--log", required=True, help="日志文件路径")
    parser.add_argument("--timeout", type=float, default=5.0, help="SIGTERM 超时(秒)")
    args = parser.parse_args()

    result = cleanup_orphan_celery(args.role, Path(args.log), args.timeout)
    # 退出码:有清理行为 = 0,无 = 0(无差别,避免污染 shell $?)
    print(f"terminated={result['terminated']} killed={result['killed']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
