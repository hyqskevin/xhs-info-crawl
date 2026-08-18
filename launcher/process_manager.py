"""子进程管理:启动/停止/重启 API/Worker/Beat/Web 进程。

关联 spec: docs/superpowers/specs/2026-08-10-one-click-packaging-design.md § 2.1-2.2
"""
from __future__ import annotations

import logging
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

logger = logging.getLogger(__name__)

SERVICE_NAMES = ("api", "worker", "beat", "web")


class ProcessManager:
    """管理 API/Worker/Beat/Web 四个子进程。

    web 服务是生产模式下的前端静态服务(等价于 vite preview),
    仅在 launcher 启动时启动;开发模式下 vite dev 已在 5173 占用端口,
    launcher 不会额外起 web 进程。

    退出时清理:
    - 子进程用 start_new_session=True 脱离 launcher 进程组(Unix),
      避免 launcher 崩溃时通过进程组信号链杀子进程
    - cleanup() 幂等,可被 atexit / signal handler / finally 多次调用
    - stop_service 默认 5s 超时,超时后 SIGKILL 强杀
    """

    def __init__(self, project_root: Path, venv_python: Path):
        self.project_root = project_root
        self.venv_python = venv_python
        self._processes: dict[str, subprocess.Popen] = {}
        self._logs_dir = project_root / "data" / "logs"
        self._logs_dir.mkdir(parents=True, exist_ok=True)
        # 默认命令模板(可被 _commands 覆盖,用于测试)
        self._commands = self._build_default_commands()
        # cleanup 幂等锁
        self._cleaned = False

    def _build_default_commands(self) -> dict[str, list[str]]:
        """构建默认的服务启动命令。"""
        python = str(self.venv_python)
        backend_dir = self.project_root / "app" / "backend"
        # 从 .env 读 API_PORT 和 WEB_PORT(launcher.bootstrap_env 会写入),
        # 默认 8000 / 5173 防止 .env 不存在时崩
        api_port = self._read_env_int("API_PORT", default=8000)
        web_port = self._read_env_int("WEB_PORT", default=5173)
        frontend_dist = self.project_root / "app" / "frontend" / "dist"
        return {
            "api": [python, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", str(api_port)],
            # worker 用 solo pool:单进程模式,不 fork worker 子进程
            # prefork 模式下 worker 主进程会 fork 出多个 grand-children,
            # launcher 直接 SIGTERM worker main 会留下 grand-children 孤儿
            # solo 模式 worker main 直接执行任务,无 grand-children,可以被干净 kill
            "worker": [python, "-m", "celery", "-A", "app.tasks.crawl_task", "worker", "--pool=solo", "--concurrency=1", "--loglevel=info"],
            "beat": [python, "-m", "celery", "-A", "app.tasks.crawl_task", "beat", "--loglevel=info"],
            # web 服务:等价 vite preview 行为,python -m http.server 提供静态文件
            # bind 127.0.0.1 仅本机访问;directory 指向 frontend/dist
            "web": [python, "-m", "http.server", str(web_port), "--bind", "127.0.0.1", "--directory", str(frontend_dist)],
        }

    def _read_env_int(self, key: str, default: int) -> int:
        """从 .env 读 int 值,找不到或解析失败则用 default。"""
        env_path = self.project_root / ".env"
        if not env_path.exists():
            return default
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if line.startswith("#") or "=" not in line:
                continue
            k, _, value = line.partition("=")
            if k.strip() == key:
                try:
                    return int(value.strip())
                except ValueError:
                    return default
        return default

    def start_service(self, name: str) -> bool:
        """启动指定服务。"""
        if name not in SERVICE_NAMES:
            return False

        # 如果已在运行,直接返回成功
        if name in self._processes:
            proc = self._processes[name]
            if proc.poll() is None:
                return True
            del self._processes[name]

        cmd = self._commands.get(name)
        if not cmd:
            return False

        log_file = self._logs_dir / f"{name}.log"
        log_handle = open(log_file, "ab")

        env = {
            **os.environ,
            "PYTHONPATH": str(self.project_root / "app" / "backend"),
            # 强制无缓冲输出,确保日志实时写入文件
            "PYTHONUNBUFFERED": "1",
        }
        # 脱离 launcher 进程组:避免 launcher 崩溃时通过进程组信号链杀子进程
        # Unix:start_new_session=True (setsid)
        # Windows:CREATE_NEW_PROCESS_GROUP(进程独立 console)
        # 关联 spec: docs/superpowers/specs/2026-08-16-launcher-cleanup-on-exit-design.md § 1
        popen_kwargs: dict = {}
        if sys.platform == "win32":
            popen_kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
        else:
            popen_kwargs["start_new_session"] = True
        proc = subprocess.Popen(
            cmd,
            stdout=log_handle,
            stderr=subprocess.STDOUT,
            cwd=str(self.project_root),
            env=env,
            **popen_kwargs,
        )
        self._processes[name] = proc
        logger.info("启动服务 %s (PID %d, 独立进程组)", name, proc.pid)
        return True

    def stop_service(self, name: str, timeout: float = 5.0) -> bool:
        """停止指定服务。

        流程:
        1. SIGTERM 子进程 → wait timeout(允许 graceful shutdown)
        2. 超时未退出 → SIGKILL **整个进程组**(因为 start_new_session=True,
           PGID == PID,可以用 os.killpg 一并杀掉 grand-children)
        3. 兜底:遍历 PID 列表,任何还在的 PID 直接 SIGKILL

        关联 spec: docs/superpowers/specs/2026-08-16-launcher-cleanup-on-exit-design.md § 4
        """
        if name not in self._processes:
            return True

        proc = self._processes[name]
        if proc.poll() is not None:
            del self._processes[name]
            return True

        # Step 1: SIGTERM 子进程,优雅退出
        proc.terminate()
        try:
            proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            # Step 2: 超时,SIGKILL 整个进程组(包含 grand-children)
            logger.warning(
                "服务 %s (PID %d, PGID %d) %s 秒内未退出,SIGKILL 进程组",
                name,
                proc.pid,
                proc.pid,
                timeout,
            )
            self._kill_process_group(proc.pid)
            try:
                proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                logger.error("服务 %s 进程组 SIGKILL 后仍未退出", name)

        del self._processes[name]
        logger.info("停止服务 %s", name)
        return True

    def _kill_process_group(self, pgid: int) -> None:
        """SIGKILL 整个进程组(macOS/Linux)。

        进程组 ID 与进程启动时传的 start_new_session=True 配套使用。
        start_new_session 让 PGID == PID,所以可以用 proc.pid 直接传。
        """
        if sys.platform == "win32":
            # Windows 用 taskkill /T(递归杀子进程);pgid 在 Windows 无意义
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(pgid)],
                check=False,
                capture_output=True,
            )
            return
        try:
            os.killpg(pgid, signal.SIGKILL)  # type: ignore[attr-defined]
        except (ProcessLookupError, PermissionError, OSError) as exc:
            logger.warning("killpg(%d) 失败: %s", pgid, exc)

    def restart_service(self, name: str) -> bool:
        """重启指定服务。"""
        self.stop_service(name)
        time.sleep(0.3)
        return self.start_service(name)

    def stop_all(self) -> None:
        """停止所有服务。"""
        for name in SERVICE_NAMES:
            self.stop_service(name)

    def get_status(self) -> dict:
        """获取所有服务状态。"""
        result = {}
        for name in SERVICE_NAMES:
            if name not in self._processes:
                result[name] = {"state": "stopped", "pid": None}
                continue

            proc = self._processes[name]
            if proc.poll() is None:
                result[name] = {"state": "running", "pid": proc.pid}
            else:
                result[name] = {"state": "crashed" if proc.returncode != 0 else "stopped", "pid": None}
                del self._processes[name]
        return result

    def get_logs_tail(self, lines: int = 50) -> list[str]:
        """获取最近日志(所有服务合并)。"""
        all_lines = []
        for name in SERVICE_NAMES:
            log_file = self._logs_dir / f"{name}.log"
            if not log_file.exists():
                continue
            try:
                content = log_file.read_text(encoding="utf-8", errors="ignore")
                file_lines = content.splitlines()[-lines:]
                all_lines.extend(file_lines)
            except Exception:
                continue
        return all_lines[-lines:]

    def cleanup(self) -> None:
        """清理资源(退出时调用)。

        幂等:可被 atexit / signal handler / finally 多次调用,只执行一次真实清理。

        关联 spec: docs/superpowers/specs/2026-08-16-launcher-cleanup-on-exit-design.md § 6
        """
        if self._cleaned:
            return
        self._cleaned = True
        logger.info("清理子进程(共 %d 个)", len(self._processes))
        self.stop_all()
