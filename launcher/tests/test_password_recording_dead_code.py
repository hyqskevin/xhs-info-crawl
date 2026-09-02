"""P2-5 死代码清理:launcher.password_recording 整体无调用方。

audit 批次 3 发现:
- launcher/password_recording.py 的 record_initial_password 函数被自身测试覆盖,
  无生产调用方(用户报告「初始密码 banner 永不出现」就是因为没人调它)
- launcher/tests/test_password_recording.py 3 个测试随之删除

注意:
- status_server.get_initial_password 端点(/initial-password)反向依赖 password 文件,
  但其不依赖 launcher.password_recording 模块本身(测试中直接 write_text 写文件即可),
  故保留该端点 + test_initial_password_endpoint_* 测试

TDD:本文件 RED 断言模块不应再存在 → GREEN 删除模块 + 删除 3 个原测试
"""
from pathlib import Path

import pytest


def test_password_recording_module_removed() -> None:
    """launcher.password_recording 模块应已删除(无生产调用方)。"""
    with pytest.raises(ModuleNotFoundError):
        importlib_import("launcher.password_recording")


def test_record_initial_password_attribute_removed() -> None:
    """record_initial_password 符号从 launcher 命名空间消失。

    belt-and-suspenders:即便有人重新建了模块但漏导 record_initial_password,
    测试也能抓到。
    """
    with pytest.raises((ModuleNotFoundError, ImportError, AttributeError)):
        fromlib_attr("launcher.password_recording", "record_initial_password")


def test_status_server_initial_password_endpoint_kept(tmp_path) -> None:
    """反向断言:删 password_recording 模块不应误伤 status_server 端点。

    /initial-password 端点由 launcher UI banner 使用,必须保留。
    """
    from unittest.mock import MagicMock

    from launcher.status_server import StatusServer

    # 构造一个最小 StatusServer,实例化后应暴露 .app 属性(FastAPI 实例)且注册了端点
    pm = MagicMock()
    pm.get_status.return_value = {name: {"state": "running", "pid": 1} for name in ("api", "worker", "beat", "web")}
    pm.get_logs_tail.return_value = []
    server = StatusServer(
        process_manager=pm,
        project_root=tmp_path,
        venv_python=Path(__import__("sys").executable),
    )
    # FastAPI app 应在实例上,且 routes 中能找到 /initial-password
    assert hasattr(server, "app"), "StatusServer 实例必须有 .app 属性(FastAPI)"
    paths = {route.path for route in server.app.routes}
    assert "/initial-password" in paths, (
        f"端点 /initial-password 必须保留(launcher UI banner 在用),实际 routes: {sorted(paths)}"
    )


# —— 内部 helper ——

def importlib_import(name: str):
    """小封装:让测试断言失败信息更可读。"""
    import importlib

    return importlib.import_module(name)


def fromlib_attr(module: str, attr: str):
    """小封装:importlib.import_module + getattr。"""
    mod = importlib_import(module)
    return getattr(mod, attr)