"""opencli daemon 端口自动检测。

启动器启动时调用,从 19825 开始扫描 ±5 范围,找到实际 opencli daemon 监听的端口。

注意:opencli v1.8.6+ 已不再支持 OPENCLI_DAEMON_PORT 环境变量(它强制使用 19825)
所以本模块只探测,不写 .env / 设 os.environ,避免触发 opencli doctor 报错
"The OpenCLI Chrome extension can only connect to localhost:19825"。
探测结果供 UI 显示当前 daemon 端口。
关联 spec: docs/superpowers/specs/2026-08-17-launcher-system-config-and-opencli-verify-design.md § 1
"""
from __future__ import annotations

import logging
import socket

logger = logging.getLogger(__name__)

# 默认探测范围:19825 ± 5(opencli 历史默认端口)
DEFAULT_PORT_RANGE = range(19825, 19830)


def _is_port_listening(host: str, port: int, timeout: float = 0.3) -> bool:
    """快速探测端口是否在 LISTEN。"""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except (ConnectionRefusedError, OSError, socket.timeout):
        return False


def detect_daemon_port(host: str = "127.0.0.1", port_range=DEFAULT_PORT_RANGE) -> int | None:
    """扫描 port_range,返回第一个 LISTEN 端口;都没找到返 None。

    不写入 .env(避免被 opencli 拒识),仅供 status_server 在响应中展示当前 daemon 端口。
    """
    for port in port_range:
        if _is_port_listening(host, port):
            logger.info("opencli daemon 端口扫描命中 %s:%d", host, port)
            return port
    return None


def bootstrap_daemon_port(host: str = "127.0.0.1") -> int | None:
    """启动器启动时调用:探测 daemon 端口,返回最终端口。

    opencli v1.8.6+ 强制使用 19825,所以这里只探测 19825 附近,无副作用。
    """
    detected = detect_daemon_port(host)
    if detected is None:
        logger.warning("未探测到 opencli daemon 端口(扫描 19825-19829)")
    return detected