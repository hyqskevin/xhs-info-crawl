"""launcher 全局测试 fixtures。

隔离 PADDLE_PDX_CACHE_HOME / HF_HOME,避免 bootstrap_env() 内部
set_cache_env_vars 的 setdefault 副作用污染其他测试模块。
关联回归: launcher/tests/test_bootstrap_env_does_not_pollute_cache_env.py
"""
from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _isolate_cache_env(monkeypatch: pytest.MonkeyPatch):
    """每个测试前后清理 PADDLE_PDX_CACHE_HOME / HF_HOME,避免跨测试污染。

    bootstrap_env() → set_cache_env_vars() 走 os.environ.setdefault 写入
    PADDLE_PDX_CACHE_HOME / HF_HOME。setdefault 在测试函数体内发生的写入
    不被 monkeypatch 追踪 — fixture 在 yield 后再次 delenv 才能清干净。

    放到 conftest.py 是为了让所有 launcher/tests/ 下的测试模块都自动套用
    这个隔离(autouse=True)。
    """
    monkeypatch.delenv("PADDLE_PDX_CACHE_HOME", raising=False)
    monkeypatch.delenv("HF_HOME", raising=False)
    yield
    # yield 后再次清理:清掉 set_cache_env_vars setdefault 在测试体内写入的值。
    # 注意此时 monkeypatch.setitem 已撤销,但 os.environ.setdefault 写入不会被撤销。
    monkeypatch.delenv("PADDLE_PDX_CACHE_HOME", raising=False)
    monkeypatch.delenv("HF_HOME", raising=False)