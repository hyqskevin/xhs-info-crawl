"""账号加载与 Chrome CDP 端点解析。

- ``load_xhs_accounts`` 加载启用账号（按 priority、id 排序）；
- ``_account_cdp_endpoint`` / ``_resolve_cdp_endpoint_for_account`` 静态/动态解析 CDP 端点；
- ``_make_chrome_pool_for_task`` 为当前任务启动 ChromePool（复用全局单例）；
- ``wait_for_login`` / ``open_account_login`` 账号切换-自动登录辅助。
"""
from __future__ import annotations

import time

from sqlalchemy import select

from app.models.xhs_account import XhsAccount
from app.services.chrome_pool import ChromeLaunchError, ChromePool, get_global_chrome_pool
from app.services.crawler import AuthenticationRequired, OpenCLIError, VerificationRequired


def load_xhs_accounts(db) -> list:
    """加载已启用的 XhsAccount 列表，按 priority 升序、id 升序排列。

    无账号配置时返回空列表，调用方负责回退到默认 session 'xhs-crawler'。
    """
    return list(db.scalars(
        select(XhsAccount)
        .where(XhsAccount.enabled.is_(True))
        .order_by(XhsAccount.priority, XhsAccount.id)
    ).all())


def _account_cdp_endpoint(account) -> str | None:
    """从 XhsAccount.cdp_port 推导 CDP 端点（仅基于账号行静态推导，不依赖 pool 实例）；None 表示回退默认 Chrome Browser Bridge。"""
    port = getattr(account, "cdp_port", None)
    if port is None:
        return None
    return f"http://127.0.0.1:{port}"


def _resolve_cdp_endpoint_for_account(account, chrome_pool) -> str | None:
    """优先用 chrome_pool 中已启动实例的端点（动态端口）；fallback 到账号行的 cdp_port。"""
    if chrome_pool is not None:
        instance = chrome_pool.get(account.session_name)
        if instance is not None:
            return instance.cdp_endpoint
    return _account_cdp_endpoint(account)


def _make_chrome_pool_for_task(settings, db, accounts) -> ChromePool:
    """为当前任务启动 ChromePool（每个有 cdp_port 的账号一个实例）。

    使用全局 ChromePool 单例——API 端点（如 check-login）和 crawl_task 共享同一池，
    避免重复启动 Chrome 实例导致端口冲突。
    """
    from app.services.opencli_extension import cdp_version_ok

    pool = get_global_chrome_pool()
    # 同步端口到 DB（持久化，供下次复用）
    for account in accounts:
        port = getattr(account, "cdp_port", None)
        if port is None:
            continue
        try:
            # preferred_port = 账号自己的 DB 端口：空闲时优先复用，
            # 写回 DB 不会撞其他账号的 cdp_port UNIQUE 约束
            instance = pool.acquire(account.session_name, preferred_port=port)
        except ChromeLaunchError:
            raise
        if instance.port != port:
            # 端口漂移：DB 原端口若有活 Chrome（多半就是该账号之前的实例）→ adopt 回，
            # 漂移实例 release 丢弃；否则写回漂移端口（IntegrityError 防御转可读错误）
            if cdp_version_ok(port):
                pool.release(account.session_name)
                instance = pool.adopt_existing(account.session_name, port)
            else:
                try:
                    account.cdp_port = instance.port
                    db.commit()
                except Exception as exc:
                    db.rollback()
                    pool.release(account.session_name)
                    raise ChromeLaunchError(
                        f"账号 {account.name!r} 的 cdp_port={instance.port} 与其他账号冲突，"
                        f"已放弃该实例；请稍后重试（原端口 {port} 无活实例）"
                    ) from exc
    return pool


# ── 账号切换-自动登录辅助（spec: 2026-08-19-xhs-account-switch-auto-login-design.md）──────


def wait_for_login(adapter, settings, timeout=None) -> bool:
    """等待指定账号登录完成：轮询 adapter.check_login()，logged_in 为真即返回 True。

    未登录/风控/瞬时 opencli 错误都被视为"还没登录"，继续轮询直到超时。
    超时抛 ``AuthenticationRequired``（供上层切换账号）。

    间隔与总超时来自 ``settings.xhs_account_login_wait_interval/timeout``。
    """
    timeout = timeout if timeout is not None else getattr(settings, "xhs_account_login_wait_timeout", 120)
    interval = getattr(settings, "xhs_account_login_wait_interval", 5)
    deadline = time.monotonic() + max(timeout, 0)
    # 至少执行一次检查；即便已过截止时间，只要本次检查成功仍返回 True
    while True:
        try:
            raw = adapter.check_login()
            if raw and raw.get("logged_in"):
                return True
        except (OpenCLIError, AuthenticationRequired, VerificationRequired):
            pass
        except Exception:  # noqa: BLE001 - 任何检查异常都当"还没登录"继续轮询
            pass
        if time.monotonic() >= deadline:
            raise AuthenticationRequired("等待登录超时，请确认已完成扫码")
        time.sleep(max(interval, 0))


def open_account_login(adapter, settings, session_name=None) -> bool:
    """在指定账号（adapter 已带其 cdp_endpoint 路由）上打开小红书登录页，让用户扫码。

    复用 opencli ``browser <session> open <url> --window foreground``。
    失败返回 False 不抛错（上层可回退到 open_xhs_login）。
    """
    try:
        session = session_name or adapter.session
        return bool(
            adapter.run(
                ["browser", session, "open", settings.xhs_login_url, "--window", "foreground"],
                enforce_execution=False,
                timeout=15,
            )
        )
    except (OpenCLIError, AuthenticationRequired, VerificationRequired):
        return False
    except Exception:  # noqa: BLE001 - 打开登录页失败不阻断切换
        return False
