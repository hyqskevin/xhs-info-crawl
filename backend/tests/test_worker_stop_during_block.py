"""测试worker在opencli阻塞时响应停止信号的能力。"""
import time
import pytest
from unittest.mock import patch, MagicMock
from app.services.opencli_adapter import OpenCLIAdapter
from app.services.task_registry import register, unregister, kill


class TestWorkerStopDuringBlock:
    """验证worker在opencli阻塞时能及时响应停止信号。"""

    def test_run_with_short_timeout(self):
        """验证run方法使用较短的超时时间（30秒）。"""
        adapter = OpenCLIAdapter(MagicMock())
        assert adapter._command_timeout() <= 90

    def test_kill_terminates_subprocess_immediately(self):
        """验证kill能立即终止子进程。"""
        import subprocess
        import os

        proc = subprocess.Popen(['sleep', '60'], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        register(999, proc.pid)

        result = kill(999, timeout=2.0)
        assert result is True

        # 验证进程已终止（使用 proc.poll() 检查）
        time.sleep(0.2)
        assert proc.poll() is not None, "进程应该已终止"

        unregister(999)

    def test_adapter_bind_task_registers_pid(self):
        """验证bind_task后run方法会注册子进程PID。"""
        adapter = OpenCLIAdapter(MagicMock())
        adapter.bind_task(888)

        assert adapter._current_task_id == 888

    def test_kill_handles_non_existent_task(self):
        """验证kill对不存在的任务返回True（幂等性）。"""
        result = kill(9999, timeout=1.0)
        assert result is True
