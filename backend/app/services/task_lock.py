from contextlib import contextmanager
from collections.abc import Iterator
from threading import Lock


class TaskAlreadyRunning(RuntimeError):
    pass


class TaskLock:
    def __init__(self) -> None:
        self._guard = Lock()
        self.running = False

    @contextmanager
    def acquire(self) -> Iterator[None]:
        with self._guard:
            if self.running:
                raise TaskAlreadyRunning("TASK_IN_PROGRESS")
            self.running = True
        try:
            yield
        finally:
            with self._guard:
                self.running = False
