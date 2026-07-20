# Stop Execution Fence and Browser Cleanup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prevent stopped or superseded crawl executions from starting additional OpenCLI commands, close the crawler session tab on every exit path, and keep the Celery worker available for subsequent tasks.

**Architecture:** Bind task-scoped execution and warning callbacks to `OpenCLIAdapter`. Every business command checks execution ownership before process creation and again after PID registration; browser workflows use a bounded, guard-bypassing cleanup command in `finally`. `run_crawl` remains responsible for database status and task logs, while the adapter remains independent of SQLAlchemy models.

**Tech Stack:** Python 3.11, FastAPI, Celery, SQLAlchemy, pytest, OpenCLI subprocess adapter, filesystem PID registry.

## Global Constraints

- Do not terminate the Celery worker as part of stopping one crawl task.
- Every task-bound business OpenCLI command must check `task_id + run_token` ownership before `Popen` and immediately after PID registration.
- Browser cleanup must target only the adapter's dedicated `xhs-crawler` session tab and must never close the user's entire Chrome process.
- Cleanup bypasses the business execution guard, has a maximum timeout of 10 seconds, and cannot change `STOPPED` to `FAILED`.
- After a browser-open command is attempted, cleanup must run even if that open command is interrupted after Chrome has already created the tab.
- Do not log Cookie values, JWTs, complete `xsec_token` values, or local `.env` contents.
- Existing unbound OpenCLI calls used by login checks and configuration management must remain compatible.

---

### Task 1: Add a command-level execution fence

**Files:**
- Create: `backend/tests/test_opencli_execution_fence.py`
- Modify: `backend/app/services/opencli_adapter.py:1-86`

**Interfaces:**
- Consumes: `task_registry.register(task_id: int, pid: int, run_token: str | None)` and `task_registry.unregister(task_id: int, run_token: str | None)`.
- Produces: `OpenCLIAdapter.bind_task(task_id: int, run_token: str | None = None, execution_guard: Callable[[], None] | None = None, warning_sink: Callable[[str], None] | None = None) -> None`.
- Produces: `OpenCLIAdapter.run(args: list[str], *, task_id: int | None = None, run_token: str | None = None, enforce_execution: bool = True, timeout: int | None = None) -> Any`.

- [x] **Step 1: Write failing fence tests**

Create `backend/tests/test_opencli_execution_fence.py` with a process double that records termination:

```python
import subprocess

import pytest

from app.core.config import Settings
from app.services import task_registry
from app.services.opencli_adapter import OpenCLIAdapter


class ExecutionStoppedForTest(Exception):
    pass


class FakeProc:
    pid = 45678

    def __init__(self) -> None:
        self.returncode: int | None = None
        self.killed = False
        self.communicate_calls = 0

    def communicate(self, timeout=None):
        self.communicate_calls += 1
        if self.returncode is None:
            self.returncode = 0
        return "[]", ""

    def poll(self):
        return self.returncode

    def kill(self) -> None:
        self.killed = True
        self.returncode = -9


@pytest.fixture(autouse=True)
def clean_registry(monkeypatch, tmp_path):
    monkeypatch.setattr(task_registry, "REGISTRY_PATH", tmp_path / "registry.json")


def test_guard_failure_before_popen_starts_no_process(monkeypatch) -> None:
    popen_calls = []
    monkeypatch.setattr(subprocess, "Popen", lambda *args, **kwargs: popen_calls.append(args))
    adapter = OpenCLIAdapter(Settings())
    adapter.bind_task(
        12,
        "run-token",
        execution_guard=lambda: (_ for _ in ()).throw(ExecutionStoppedForTest()),
    )

    with pytest.raises(ExecutionStoppedForTest):
        adapter.run(["xiaohongshu", "whoami"])

    assert popen_calls == []
    assert task_registry.get(12, "run-token") is None


def test_guard_failure_after_registration_kills_new_process(monkeypatch) -> None:
    proc = FakeProc()
    monkeypatch.setattr(subprocess, "Popen", lambda *args, **kwargs: proc)
    checks = 0

    def guard() -> None:
        nonlocal checks
        checks += 1
        if checks == 2:
            raise ExecutionStoppedForTest()

    adapter = OpenCLIAdapter(Settings())
    adapter.bind_task(13, "run-token", execution_guard=guard)

    with pytest.raises(ExecutionStoppedForTest):
        adapter.run(["xiaohongshu", "whoami"])

    assert checks == 2
    assert proc.killed is True
    assert proc.communicate_calls == 1
    assert task_registry.get(13, "run-token") is None


def test_unbound_adapter_remains_compatible(monkeypatch) -> None:
    proc = FakeProc()
    monkeypatch.setattr(subprocess, "Popen", lambda *args, **kwargs: proc)

    assert OpenCLIAdapter(Settings()).run(["xiaohongshu", "whoami"]) == []
```

- [x] **Step 2: Run the new tests and verify RED**

Run:

```bash
cd backend && .venv/bin/pytest -q tests/test_opencli_execution_fence.py
```

Expected: the first two tests fail because `bind_task` does not accept `execution_guard`; the compatibility test passes.

- [x] **Step 3: Implement the minimal execution fence**

In `backend/app/services/opencli_adapter.py`, import `Callable`, add callback fields, and extend `bind_task`:

```python
from collections.abc import Callable


class OpenCLIAdapter:
    def __init__(self, settings: Settings, session: str = "xhs-crawler") -> None:
        self.settings = settings
        self.session = session
        self._current_task_id: int | None = None
        self._current_run_token: str | None = None
        self._execution_guard: Callable[[], None] | None = None
        self._warning_sink: Callable[[str], None] | None = None

    def bind_task(
        self,
        task_id: int,
        run_token: str | None = None,
        execution_guard: Callable[[], None] | None = None,
        warning_sink: Callable[[str], None] | None = None,
    ) -> None:
        self._current_task_id = task_id
        self._current_run_token = run_token
        self._execution_guard = execution_guard
        self._warning_sink = warning_sink
```

Add focused helpers:

```python
    def _assert_execution_active(self, enforce_execution: bool) -> None:
        if enforce_execution and self._execution_guard is not None:
            self._execution_guard()

    @staticmethod
    def _kill_and_reap(proc: subprocess.Popen) -> None:
        if proc.poll() is None:
            proc.kill()
        proc.communicate()
```

Extend `run()` with `enforce_execution` and `timeout`. Call `_assert_execution_active()` before `Popen`, then again immediately after registry registration. If the second call raises, call `_kill_and_reap(proc)` and re-raise. Preserve the existing timeout, exit-code translation, JSON parsing, and token-aware `unregister` in `finally`.

Use `timeout if timeout is not None else self._command_timeout()` as the effective timeout. Do not catch or translate exceptions raised by the execution guard.

- [x] **Step 4: Run focused and existing subprocess tests**

Run:

```bash
cd backend && .venv/bin/pytest -q tests/test_opencli_execution_fence.py tests/test_adapter_popen_register.py tests/test_worker_stop_during_block.py
```

Expected: all tests pass; PID registration remains token-aware and guard failures do not leave registry entries.

- [x] **Step 5: Commit the execution fence**

```bash
git add backend/app/services/opencli_adapter.py backend/tests/test_opencli_execution_fence.py
git commit -m "fix: fence stopped OpenCLI executions"
```

---

### Task 2: Make browser tab cleanup exception-safe

**Files:**
- Modify: `backend/tests/test_opencli_execution_fence.py`
- Modify: `backend/app/services/opencli_adapter.py:94-136`
- Modify: `docs/superpowers/specs/2026-07-20-stop-execution-fence-browser-cleanup-design.md:120-132`

**Interfaces:**
- Consumes: the extended `OpenCLIAdapter.run(..., enforce_execution: bool, timeout: int | None)` from Task 1.
- Produces: `OpenCLIAdapter._close_browser_tab() -> None`, a best-effort cleanup operation for the adapter session.

- [ ] **Step 1: Add failing browser-cleanup tests**

Append tests using a monkeypatched adapter `run` that accepts keyword arguments:

```python
def test_search_closes_session_tab_when_middle_command_stops(monkeypatch) -> None:
    adapter = OpenCLIAdapter(Settings())
    calls: list[tuple[list[str], dict]] = []

    def fake_run(args, **kwargs):
        calls.append((args, kwargs))
        if args[:2] == ["xiaohongshu", "whoami"]:
            return {"logged_in": True}
        if args[:3] == ["browser", adapter.session, "open"]:
            return {"opened": True}
        if args[:3] == ["browser", adapter.session, "close"]:
            return {"closed": True}
        raise ExecutionStoppedForTest()

    monkeypatch.setattr(adapter, "run", fake_run)

    with pytest.raises(ExecutionStoppedForTest):
        adapter.search_recent("宁波 活动", "一周内")

    close_calls = [(args, kwargs) for args, kwargs in calls if args[:3] == ["browser", adapter.session, "close"]]
    assert close_calls == [
        (["browser", adapter.session, "close"], {"enforce_execution": False, "timeout": 10})
    ]


def test_note_attempts_cleanup_when_open_command_is_interrupted(monkeypatch) -> None:
    adapter = OpenCLIAdapter(Settings())
    calls: list[tuple[list[str], dict]] = []

    def fake_run(args, **kwargs):
        calls.append((args, kwargs))
        if args[:2] == ["xiaohongshu", "whoami"]:
            return {"logged_in": True}
        if args[:3] == ["browser", adapter.session, "close"]:
            return {"closed": True}
        if args[:3] == ["browser", adapter.session, "open"]:
            raise ExecutionStoppedForTest()
        return {}

    monkeypatch.setattr(adapter, "run", fake_run)

    with pytest.raises(ExecutionStoppedForTest):
        adapter.note("https://www.xiaohongshu.com/explore/note-id")

    assert any(args[:3] == ["browser", adapter.session, "close"] for args, _ in calls)


def test_cleanup_failure_uses_warning_sink_without_masking_result(monkeypatch) -> None:
    warnings = []
    adapter = OpenCLIAdapter(Settings())
    adapter.bind_task(14, "run-token", warning_sink=warnings.append)

    def fake_run(args, **kwargs):
        if args[:2] == ["xiaohongshu", "whoami"]:
            return {"logged_in": True}
        if args[:3] == ["browser", adapter.session, "open"]:
            return {"opened": True}
        if args[:3] == ["browser", adapter.session, "eval"]:
            script = args[3]
            if "optionExists" in script or "targetText" in script:
                return True
            return []
        if args[:3] == ["browser", adapter.session, "close"]:
            raise RuntimeError("close failed")
        return True

    monkeypatch.setattr(adapter, "run", fake_run)

    assert adapter.search_recent("宁波 活动", "不限") == []
    assert len(warnings) == 1
    assert "浏览器标签页清理失败" in warnings[0]
```

- [ ] **Step 2: Run cleanup tests and verify RED**

Run:

```bash
cd backend && .venv/bin/pytest -q tests/test_opencli_execution_fence.py -k 'closes_session_tab or attempts_cleanup or cleanup_failure'
```

Expected: tests fail because cleanup is not in `finally`, interrupted open is not cleaned up, and no warning sink helper exists.

- [ ] **Step 3: Implement bounded best-effort cleanup**

Add a logger and two helpers to `OpenCLIAdapter`:

```python
import logging

logger = logging.getLogger(__name__)


    def _warn(self, message: str) -> None:
        if self._warning_sink is not None:
            self._warning_sink(message)
        else:
            logger.warning(message)

    def _close_browser_tab(self) -> None:
        try:
            self.run(
                ["browser", self.session, "close"],
                enforce_execution=False,
                timeout=10,
            )
        except Exception as exc:
            self._warn(f"浏览器标签页清理失败: {exc}")
```

Refactor `search_recent()` and `note()` so the `try` block begins immediately before attempting `browser open`, and `_close_browser_tab()` runs in `finally` whenever the open invocation was attempted. This intentionally handles the case where Chrome creates a tab before an interrupted OpenCLI process reports success. The adapter session is dedicated to the crawler, so a best-effort close does not target arbitrary user tabs.

Return parsed search results and normalized note details from inside the `try`; do not place business commands after the cleanup block.

Update the approved spec sentence “如果 `browser open` 本身失败，不执行多余关闭” to state that cleanup begins once the open invocation is attempted, because interruption may happen after Chrome has already created the tab.

- [ ] **Step 4: Run adapter regression tests**

Run:

```bash
cd backend && .venv/bin/pytest -q tests/test_opencli_execution_fence.py tests/test_opencli_and_dedup_integration.py tests/test_adapter_popen_register.py
```

Expected: all tests pass; normal paths close exactly once, exceptional paths attempt cleanup, and cleanup failures do not mask the business result.

- [ ] **Step 5: Commit browser cleanup**

```bash
git add backend/app/services/opencli_adapter.py backend/tests/test_opencli_execution_fence.py docs/superpowers/specs/2026-07-20-stop-execution-fence-browser-cleanup-design.md
git commit -m "fix: clean up stopped crawler tabs"
```

---

### Task 3: Bind database execution ownership and task warnings

**Files:**
- Modify: `backend/app/tasks/crawl_task.py:267-273`
- Modify: `backend/tests/test_crawl_execution_ownership.py`

**Interfaces:**
- Consumes: `assert_execution_active(db, task_id: int, run_token: str) -> None` and `log(db, task_id: int, level: str, message: str) -> None`.
- Produces: a task-bound adapter whose guard observes current database status/token and whose cleanup warnings appear in `task_logs`.

- [ ] **Step 1: Write a failing callback-binding test**

Append to `backend/tests/test_crawl_execution_ownership.py`:

```python
from sqlalchemy import select

from app.models.task import CrawlTask, TaskLog


def test_worker_binds_execution_guard_and_warning_sink(db_session, monkeypatch) -> None:
    city = City(name="宁波", code="nb", enabled=True, recent_filter="一周内")
    keyword = Keyword(city_code="nb", word="活动", enabled=True)
    task = CrawlTask(
        type="mixed",
        status="PENDING",
        run_token="bound-token",
        params={"city": "nb", "keywords": ["活动"], "blogger_ids": []},
    )
    db_session.add_all([city, keyword, task])
    db_session.commit()
    captured = {}

    class FakeAdapter:
        def __init__(self, _settings):
            pass

        def bind_task(self, task_id, run_token, execution_guard=None, warning_sink=None):
            captured.update(
                task_id=task_id,
                run_token=run_token,
                execution_guard=execution_guard,
                warning_sink=warning_sink,
            )

        def search_recent(self, *_args):
            captured["execution_guard"]()
            captured["warning_sink"]("浏览器标签页清理失败: test")
            return []

    monkeypatch.setattr(crawl_task, "SessionLocal", lambda: db_session)
    monkeypatch.setattr(crawl_task, "OpenCLIAdapter", FakeAdapter)

    crawl_task.run_crawl.run(task.id, "bound-token")

    assert captured["task_id"] == task.id
    assert captured["run_token"] == "bound-token"
    assert callable(captured["execution_guard"])
    assert callable(captured["warning_sink"])
    messages = list(db_session.scalars(select(TaskLog.message).where(TaskLog.task_id == task.id)))
    assert "浏览器标签页清理失败: test" in messages
```

- [ ] **Step 2: Run the binding test and verify RED**

Run:

```bash
cd backend && .venv/bin/pytest -q tests/test_crawl_execution_ownership.py::test_worker_binds_execution_guard_and_warning_sink
```

Expected: fail because `run_crawl` currently passes only `task_id` and `run_token` to `bind_task`.

- [ ] **Step 3: Bind callbacks in `run_crawl`**

Replace the current binding call with:

```python
        adapter.bind_task(
            task.id,
            run_token,
            execution_guard=lambda: assert_execution_active(db, task.id, run_token),
            warning_sink=lambda message: log(db, task.id, "WARNING", message),
        )
```

Do not move state transitions into the adapter. Existing `ExecutionStopped` and `ExecutionSuperseded` handlers remain the only owners of crawl task status.

- [ ] **Step 4: Run ownership and stop regressions**

Run:

```bash
cd backend && .venv/bin/pytest -q tests/test_crawl_execution_ownership.py tests/test_crawl_task_resilience.py tests/test_task_stop_immediate.py tests/test_crawl_auto_stop_previous.py
```

Expected: all tests pass; stopped tasks do not process another note, old tokens cannot write, and warning messages are visible in task logs.

- [ ] **Step 5: Commit task binding**

```bash
git add backend/app/tasks/crawl_task.py backend/tests/test_crawl_execution_ownership.py
git commit -m "fix: bind crawl execution checks to OpenCLI"
```

---

### Task 4: Document behavior and complete verification

**Files:**
- Modify: `docs/crawler-design.md:162-168`
- Modify: `docs/api-doc.md:228-240`
- Modify: `docs/TODO.md`
- Modify: `docs/superpowers/specs/2026-07-20-stop-execution-fence-browser-cleanup-design.md:3`
- Create: `tests/test-stop-execution-fence-browser-cleanup.md`

**Interfaces:**
- Consumes: the command fence, browser cleanup, worker callback binding, and existing stop/restart API.
- Produces: documented automated and real-browser acceptance evidence for this TODO.

- [ ] **Step 1: Add the E2E test-case document**

Create `tests/test-stop-execution-fence-browser-cleanup.md` with the following cases:

```markdown
# 停止执行栅栏与浏览器标签页清理测试案例

## 自动化测试

1. 运行 `cd backend && .venv/bin/pytest -q tests/test_opencli_execution_fence.py`。
2. 验证停止状态在 `Popen` 前出现时不创建进程。
3. 验证停止发生在 PID 登记后时，新进程被结束并回收。
4. 验证搜索和详情流程发生异常时都执行 crawler session 标签页清理。
5. 验证清理失败只写 WARNING，不覆盖任务停止状态。

## 真实浏览器验收

1. 保持本地 API、Celery worker、前端和已登录小红书的 Chrome 运行。
2. 从仪表盘发起一个至少包含多篇笔记的抓取任务。
3. 在搜索、滚动或详情处理阶段点击“停止抓取”，记录点击时间。
4. 验证 5 秒内日志不再出现新的业务 `open`、`eval`、`scroll`、`note` 或 `download` 操作。
5. 验证包含标签页清理时最迟 15 秒进入 `STOPPED`。
6. 验证 `/tmp/xhs_task_registry.json` 中没有该 `task_id + run_token`。
7. 验证 crawler session 打开的抓取标签页关闭，用户其他 Chrome 标签页和登录态仍保留。
8. 不重启 worker，发起第二条新任务并验证进入 `RUNNING`。
9. 验证第一条任务的进度、日志和数据不再变化。
```

- [ ] **Step 2: Update design and API documentation**

In `docs/crawler-design.md`, replace the ambiguous “worker ... 退出” wording with “当前 `run_crawl` 返回，Celery worker 保持运行”，and document pre-Popen/post-registration guards plus bounded `finally` cleanup.

In `docs/api-doc.md`, document `STOP_REQUESTED`, the 5-second no-new-business-command target, the 15-second cleanup-inclusive `STOPPED` target, and warning-log behavior.

- [ ] **Step 3: Run the complete automated suite**

Run:

```bash
make test
make test-e2e
git diff --check
```

Expected: backend, frontend component, and Playwright suites exit 0; no formatting errors; tests do not invoke real OpenCLI or mutate the local broker/database.

- [ ] **Step 4: Run real local worker acceptance**

Use the steps in `tests/test-stop-execution-fence-browser-cleanup.md`. Record the tested task IDs and timestamps in the test document without recording URLs containing complete tokens.

Expected: no new business command after stop, registry empty, crawler tab closed, old task stable, worker alive, and second task runs.

- [ ] **Step 5: Close the TODO after all acceptance passes**

Change the spec status to `已审核并实现`. Move “停止执行栅栏与浏览器标签页清理” and the overlapping manual “验证点击停止抓取” item into `docs/TODO.md` 的“已完成” section. Record exact automated counts and the real task IDs without sensitive values.

- [ ] **Step 6: Commit documentation and acceptance evidence**

```bash
git add docs/crawler-design.md docs/api-doc.md docs/TODO.md docs/superpowers/specs/2026-07-20-stop-execution-fence-browser-cleanup-design.md tests/test-stop-execution-fence-browser-cleanup.md
git commit -m "docs: verify stopped crawl cleanup"
```
