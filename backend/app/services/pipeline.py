import time
from collections.abc import Callable, Iterable
from typing import Any, TypeVar

from app.services.crawler import AuthenticationRequired

T = TypeVar("T")


def run_stage(operation: Callable[[], T], attempts: int, delay_seconds: float) -> T:
    last_error: Exception | None = None
    for attempt in range(max(1, attempts)):
        try:
            return operation()
        except AuthenticationRequired:
            raise
        except Exception as exc:
            last_error = exc
            if attempt + 1 < attempts and delay_seconds > 0:
                time.sleep(delay_seconds)
    assert last_error is not None
    raise last_error


def deduplicate_results(rows: Iterable[tuple[str, dict[str, Any]]]) -> list[tuple[str, dict[str, Any]]]:
    seen: set[str] = set()
    unique = []
    for city, item in rows:
        url = str(item.get("url") or "")
        if not url or url in seen:
            continue
        seen.add(url)
        unique.append((city, item))
    return unique


def process_with_isolation(items: Iterable[T], processor: Callable[[T], Any], on_failure: Callable[[T, Exception], Any]) -> None:
    for item in items:
        try:
            processor(item)
        except AuthenticationRequired:
            raise
        except Exception as exc:
            on_failure(item, exc)
