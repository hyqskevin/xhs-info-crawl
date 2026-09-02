"""adapter_failover 主备账号切换原语（crawl_task 主循环专用）。

关联 spec: docs/superpowers/specs/2026-09-01-crawl-task-failover-integration-design.md §3.1

设计动机
--------
``app.services.opencli_failover.run_with_failover`` 是 subprocess 层的主备链式重试
原语（拼 ``['opencli', '--profile', alias, 'xxx']`` 子命令 + JSON.loads 解析）。
但 crawl_task 主循环用的是 OpenCLIAdapter 高层抽象 —— 不需要拼子命令,直接调
adapter 的 ``check_login()`` / ``logout()`` / ``download_and_ocr()`` 等方法,
还要管 ChromePool 资源、扫码等待、bind_task、状态保存等副作用。
两套抽象层不兼容,所以 crawl_task 主循环不能直接套 subprocess 版。

本模块提供**适配器层**版本:
- 接受一个 ``command(adapter, account) -> T`` 可调用,不再拼子命令
- ``adapter_factory(account, settings)`` 由调用方决定如何构造 adapter
  (crawl_task 传入 ``OpenCLIAdapter(settings, session=account.session_name,
   cdp_endpoint=..., profile_alias=...)``)
- 链式:primary → fallbacks → 第一个成功立即返回 (result, used_account)
- 全部失败 → ``AdapterAllFailed(attempts=[AdapterAttempt, ...])``
- 可选 ``bind_task(adapter)`` 回调:每个 adapter 构造后绑定 task 上下文
- 可选 ``on_success(used_account)`` 回调:成功切换时通知调用方更新 account_index
"""
from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any


@dataclass
class AdapterAttempt:
    """单次账号尝试失败记录。"""

    session_name: str
    error: Exception


class AdapterAllFailed(RuntimeError):
    """主 + 所有备账号 adapter command 全部失败。"""

    def __init__(self, attempts: list[AdapterAttempt]):
        self.attempts = attempts
        lines = [f"主备 {len(attempts)} 个账号 adapter 全部失败："]
        for a in attempts:
            lines.append(
                f"  - {a.session_name}: {type(a.error).__name__}: {a.error}"
            )
        super().__init__("\n".join(lines))


def run_with_adapter_failover(
    command: Callable[[Any, Any], Any],
    primary_account: Any,
    fallback_accounts: Sequence[Any] | None = None,
    *,
    adapter_factory: Callable[[Any, Any], Any],
    settings: Any = None,
    bind_task: Callable[[Any], None] | None = None,
    on_success: Callable[[Any], None] | None = None,
    no_retry_exceptions: Sequence[type[BaseException]] = (),
) -> tuple[Any, Any]:
    """主 → 备账号链式调用 command(adapter, account)。

    Args:
        command: callable(adapter, account) -> T。每个账号一次调用,
            由调用方在内部组合 ``check_login`` / ``open_account_login`` /
            ``wait_for_login`` / ``download_and_ocr`` 等高层方法。
        primary_account: 主账号（必须有 .session_name 或 duck-type 同）;
            也可 duck-type 为 SimpleNamespace。
        fallback_accounts: 备账号列表（顺序遍历）；None 或空表示无备。
        adapter_factory: callable(account, settings) -> adapter。
            调用方负责把 profile_alias / cdp_endpoint 注入。
        settings: 透传给 adapter_factory。
        bind_task: 可选 callable(adapter) -> None。每个 adapter 构造后被调用,
            供调用方绑定 task 上下文（assert_execution_active / warning_sink）。
        on_success: 可选 callable(used_account) -> None。首个账号成功后被调用,
            供调用方更新 account_index 等外部状态。
        no_retry_exceptions: 命中即直通向上抛的异常类型元组（默认 () 不直通）。
            用于控制流异常（如 ExecutionStopped / ExecutionSuperseded）——
            它们不代表"账号失败"，不该触发链式换号，直接交给上层处理。

    Returns:
        (result, used_account): 第一个成功的 command 返回值 + 实际用到的账号。

    Raises:
        AdapterAllFailed: primary + 所有 fallback 都失败;
            attempts 列表按遍历顺序记录每个账号的 session_name + 抛出的异常。
    """
    accounts: list[Any] = [primary_account] + list(fallback_accounts or [])
    attempts: list[AdapterAttempt] = []
    for account in accounts:
        adapter = adapter_factory(account, settings)
        if bind_task is not None:
            bind_task(adapter)
        try:
            result = command(adapter, account)
        except no_retry_exceptions:
            # 控制流异常（停止/被取代）：不是账号失败，立即向上传播
            raise
        except Exception as exc:  # noqa: BLE001 - 其余 command 异常都视为该账号失败
            session_name = getattr(account, "session_name", "<unknown>")
            attempts.append(AdapterAttempt(session_name=session_name, error=exc))
            continue
        # 成功
        if on_success is not None:
            on_success(account)
        return result, account
    raise AdapterAllFailed(attempts)