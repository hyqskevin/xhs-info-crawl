"""task_registry：跨进程跟踪正在运行的抓取任务子进程。

worker 注册自己当前 note 子进程的 PID；后端 stop 接口通过它找到 PID 并 kill。
"""

import os
import time
from pathlib import Path

import pytest


REGISTRY = Path("/tmp/xhs_task_registry.json")


@pytest.fixture(autouse=True)
def _clean_registry():
    """每个测试前后清空 registry 文件。"""
    if REGISTRY.exists():
        REGISTRY.unlink()
    yield
    if REGISTRY.exists():
        REGISTRY.unlink()


def test_register_and_get():
    from app.services.task_registry import register, get
    register(1, 12345)
    info = get(1)
    assert info is not None
    assert info["pid"] == 12345
    assert "registered_at" in info


def test_get_missing_returns_none():
    from app.services.task_registry import get
    assert get(999) is None


def test_unregister_removes_entry():
    from app.services.task_registry import register, unregister, get
    register(2, 22222)
    assert get(2) is not None
    unregister(2)
    assert get(2) is None


def test_register_overwrites_previous():
    from app.services.task_registry import register, get
    register(3, 30000)
    register(3, 30001)
    assert get(3)["pid"] == 30001


def test_concurrent_register_no_data_loss():
    """并发 register 同一 task_id 不能丢数据（最后一个写入生效）。"""
    import threading

    from app.services.task_registry import register, get

    def worker(pid_value: int):
        register(4, pid_value)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(5, 15)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=5)

    final = get(4)
    assert final is not None
    assert final["pid"] in range(5, 15)


def test_get_pid_returns_none_for_unregistered():
    """刚 unregister 后立即 get 应该返回 None。"""
    from app.services.task_registry import register, unregister, get
    register(5, 55555)
    unregister(5)
    assert get(5) is None


def test_registry_survives_via_file(tmp_path, monkeypatch):
    """registry 用文件持久化，进程间共享。"""
    # 修改模块的 REGISTRY_PATH
    from app.services import task_registry
    monkeypatch.setattr(task_registry, "REGISTRY_PATH", tmp_path / "reg.json")

    task_registry.register(6, 66666)
    # 模拟"另一个进程"读
    data = task_registry._read()
    assert data.get("6", {}).get("pid") == 66666


def test_execution_tokens_keep_old_and_new_children_separate():
    from app.services.task_registry import get, register, unregister

    register(7, 70001, run_token="old")
    register(7, 70002, run_token="new")

    assert get(7, run_token="old")["pid"] == 70001
    assert get(7, run_token="new")["pid"] == 70002
    unregister(7, run_token="old")
    assert get(7, run_token="old") is None
    assert get(7, run_token="new")["pid"] == 70002
