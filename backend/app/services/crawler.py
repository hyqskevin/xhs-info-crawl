class OpenCLIError(RuntimeError):
    pass


class OpenCLITimeout(OpenCLIError):
    pass


class AuthenticationRequired(OpenCLIError):
    pass


class VerificationRequired(AuthenticationRequired):
    pass


class CrawlHalted(Exception):
    """连续笔记处理失败达到阈值，任务应 PAUSED 等待用户决策（扫码/验证/结束）。"""
    pass


_VERIFICATION_SIGNALS = (
    "captcha",
    "安全验证",
    "请完成验证",
    "扫码验证",
    "异常访问验证",
    "risk verification",
    # 2026-08-22 task28 反馈：opencli SECURITY_BLOCK / 风控 / 访问频繁
    # 必须被识别为 verification 信号，立即触发 VerificationRequired → 任务熔断
    "security block",
    "security_block",
    "risk control",
    "访问频繁",
    "风控",
)


def is_verification_required(message: str) -> bool:
    normalized = (message or "").strip().lower()
    return any(signal in normalized for signal in _VERIFICATION_SIGNALS)
