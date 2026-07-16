from datetime import datetime, timedelta, timezone
from collections.abc import Callable
from typing import Any


class OpenCLIError(RuntimeError):
    pass


class OpenCLITimeout(OpenCLIError):
    pass


class AuthenticationRequired(OpenCLIError):
    pass


def map_opencli_error(code: int) -> OpenCLIError:
    if code == 75:
        return OpenCLITimeout("OpenCLI timeout")
    if code == 77:
        return AuthenticationRequired("OpenCLI authentication required")
    return OpenCLIError(f"OpenCLI failed with code {code}")


def filter_recent_notes(notes: list[dict[str, object]], now: datetime | None = None, days: int = 7) -> list[dict[str, object]]:
    current = now or datetime.now(timezone.utc)
    cutoff = current - timedelta(days=days)
    return [note for note in notes if datetime.fromisoformat(str(note["published_at"]).replace("Z", "+00:00")) >= cutoff]


Runner = Callable[[list[str]], dict[str, Any]]


def check_login(runner: Runner) -> bool:
    result = runner(["opencli", "xiaohongshu", "whoami", "-f", "json", "--window", "background"])
    error = result.get("error") or {}
    if error.get("exitCode") == 77 or error.get("code") == "AUTH_REQUIRED":
        raise AuthenticationRequired("请在 Chrome 登录小红书后重试")
    if not result.get("ok"):
        raise OpenCLIError(str(error.get("message", "OpenCLI login check failed")))
    return True


def search_notes(query: str, limit: int, runner: Runner) -> list[dict[str, Any]]:
    check_login(runner)
    result = runner(["opencli", "xiaohongshu", "search", query, "--limit", str(limit), "-f", "json", "--window", "background"])
    error = result.get("error") or {}
    if error.get("exitCode") == 77 or error.get("code") == "AUTH_REQUIRED":
        raise AuthenticationRequired("请在 Chrome 登录小红书后重试")
    if not result.get("ok"):
        raise OpenCLIError(str(error.get("message", "OpenCLI search failed")))
    data = result.get("data", [])
    return data if isinstance(data, list) else []
