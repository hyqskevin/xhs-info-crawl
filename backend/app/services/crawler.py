from datetime import datetime, timedelta, timezone


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
