from datetime import datetime, timedelta, timezone
from collections.abc import Callable
from typing import Any
from dataclasses import dataclass


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


@dataclass(frozen=True)
class ScrollPolicy:
    target_count: int = 50
    max_rounds: int = 8
    pixels: int = 800
    stagnant_rounds: int = 2


def check_login(runner: Runner) -> bool:
    result = runner(["opencli", "xiaohongshu", "whoami", "-f", "json", "--window", "background"])
    error = result.get("error") or {}
    if error.get("exitCode") == 77 or error.get("code") == "AUTH_REQUIRED":
        raise AuthenticationRequired("请在 Chrome 登录小红书后重试")
    if not result.get("ok"):
        raise OpenCLIError(str(error.get("message", "OpenCLI login check failed")))
    return True


def collect_with_scroll(snapshot: Callable[[], list[Any]], scroll: Callable[[int], None], policy: ScrollPolicy) -> list[Any]:
    items = snapshot()
    stagnant = 0
    for _ in range(policy.max_rounds):
        if len(items) >= policy.target_count:
            break
        before = len(items)
        scroll(policy.pixels)
        items = snapshot()
        stagnant = stagnant + 1 if len(items) <= before else 0
        if stagnant >= policy.stagnant_rounds:
            break
    return items[: policy.target_count]


def search_recent_notes(query: str, limit: int, runner: Runner, apply_filters: Callable[[], None] | None = None) -> list[dict[str, Any]]:
    check_login(runner)
    if apply_filters:
        apply_filters()
    result = runner(["opencli", "xiaohongshu", "search", query, "--limit", str(limit), "-f", "json", "--window", "background"])
    error = result.get("error") or {}
    if error.get("exitCode") == 77 or error.get("code") == "AUTH_REQUIRED":
        raise AuthenticationRequired("请在 Chrome 登录小红书后重试")
    if not result.get("ok"):
        raise OpenCLIError(str(error.get("message", "OpenCLI search failed")))
    data = result.get("data", [])
    notes = data if isinstance(data, list) else []
    return filter_recent_notes(notes, days=7) if notes and all("published_at" in note for note in notes) else notes


search_notes = search_recent_notes
