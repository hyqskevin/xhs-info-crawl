"""回归测试:bootstrap_env 调用后,conftest 隔离 fixture 应清空污染。

背景:
- set_cache_env_vars() 用 os.environ.setdefault 写入 PADDLE_PDX_CACHE_HOME / HF_HOME
- 这些写入发生在测试函数体内,monkeypatch.setitem 撤销不覆盖 setdefault
- 修复:launcher/tests/conftest.py 加 autouse fixture,yield 后再 delenv 清掉 setdefault 副作用

本测试验证隔离 fixture 生效:
- 测试期间,bootstrap_env 后 os.environ['PADDLE_PDX_CACHE_HOME'] 已被 fixture 起始 delenv 清空
  → setdefault 写入后,直到 fixture yield 后才被清掉
- 但**下一个测试**开始时,fixture 起始 delenv 应保证 cache env 已清空

通过测试方法:在 fixture yield 后(测试函数返回后),让 fixture 再 delenv,然后用另一个测试函数
验证此时 os.environ['PADDLE_PDX_CACHE_HOME'] 为 None。
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest


def test_bootstrap_env_invokes_set_cache_env_vars(tmp_path: Path) -> None:
    """bootstrap_env 调用后,测试函数体内能确认 set_cache_env_vars 确实写入了 env。

    这是**前置事实**:确实会写入,所以后续测试必须靠 fixture 清掉。
    """
    from launcher.main import bootstrap_env

    env_path = tmp_path / ".env"
    env_path.write_text(
        "DATA_DIR=./data\n"
        "SECRET_KEY=pytest-only-jwt-secret-at-least-32-bytes\n",
        encoding="utf-8",
    )
    target = tmp_path / "data"
    target.mkdir()

    bootstrap_env(tmp_path)

    # 函数体内,setdefault 刚写入,断言 env 被污染是预期行为(产线需要)
    leaked = os.environ.get("PADDLE_PDX_CACHE_HOME")
    assert leaked is not None, (
        "bootstrap_env 应该通过 set_cache_env_vars 写入 PADDLE_PDX_CACHE_HOME,"
        "如果这里为 None,说明生产逻辑被改坏了"
    )
    assert leaked == str(tmp_path / "data" / "paddlex")


def test_next_test_sees_clean_cache_env(tmp_path: Path) -> None:
    """前一个测试即使调用了 bootstrap_env,本测试开始时 PADDLE_PDX_CACHE_HOME 必须为 None。

    隔离由 autouse fixture _isolate_cache_env 在 conftest.py 提供:
    yield 后再 delenv,清掉上一个测试 setdefault 写入的副作用。
    """
    leaked = os.environ.get("PADDLE_PDX_CACHE_HOME")
    hf = os.environ.get("HF_HOME")
    assert leaked is None, (
        f"上一个测试污染了 PADDLE_PDX_CACHE_HOME={leaked!r},"
        f"conftest._isolate_cache_env fixture 应该在 yield 后清空"
    )
    assert hf is None, f"HF_HOME 残留 {hf!r}"