class OpenCLIError(RuntimeError):
    pass


class OpenCLITimeout(OpenCLIError):
    pass


class AuthenticationRequired(OpenCLIError):
    pass


class VerificationRequired(AuthenticationRequired):
    pass


_VERIFICATION_SIGNALS = (
    "captcha",
    "安全验证",
    "请完成验证",
    "扫码验证",
    "异常访问验证",
    "risk verification",
)


def is_verification_required(message: str) -> bool:
    normalized = (message or "").strip().lower()
    return any(signal in normalized for signal in _VERIFICATION_SIGNALS)
