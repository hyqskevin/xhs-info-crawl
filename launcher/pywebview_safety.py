"""PyWebView 启动崩溃保护:webview.start() 抛异常不影响主进程和子进程。

关联 spec: docs/superpowers/specs/2026-08-16-launcher-password-visibility-design.md § 4

背景:
- macOS 上双击 .app 启动时,PyWebView 创建 NSWindow 可能因 GUI 环境问题抛异常
- 顶层 main() 当前用 try/finally 包裹 webview.start(),异常会传到 main()
- 现状:webview.start 抛 RuntimeError → main() 退出 → pm.cleanup() 触发 → 子进程 SIGTERM
- 用户看到「双击启动后立即消失」

修复:
- 把 webview.start() 包装成 safe_pywebview_start,内部 try/except 只记日志
- 主进程进入 run_main_loop keep alive,即使 PyWebView 挂了子进程继续运行
"""
from __future__ import annotations

import logging
import time

logger = logging.getLogger(__name__)


def safe_pywebview_start(window_creator, log=None) -> None:
    """安全启动 PyWebView 窗口,异常只记日志不传播。

    Args:
        window_creator: 无参 callable,内部创建并返回 webview.Window
        log: 可选 log callback,用于 main.py 记录到 launcher.log
    """
    try:
        window = window_creator()
        import webview

        webview.start()
    except Exception as exc:
        msg = f"PyWebView 启动失败(已忽略,后端进程继续运行): {exc}"
        logger.exception(msg)
        if log is not None:
            log(msg)


def run_main_loop(on_iteration=None, exception_log=None, sleep_seconds: int = 60) -> None:
    """主进程 keep alive 循环,任何异常只记日志。

    每 sleep_seconds 调一次 on_iteration(可空,例如做健康检查),
    捕获所有异常并继续。KeyboardInterrupt 传播给调用者(让程序正常退出)。
    """
    while True:
        try:
            if on_iteration is not None:
                on_iteration()
            time.sleep(sleep_seconds)
        except KeyboardInterrupt:
            raise
        except Exception as exc:
            msg = f"主循环异常(已忽略): {exc}"
            logger.exception(msg)
            if exception_log is not None:
                exception_log(msg)