# Blogger Discovery Resilience Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Isolate ordinary per-blogger discovery failures so signed notes already found from other bloggers still reach processing, while authentication and execution-control exceptions remain batch-stopping.

**Architecture:** Keep isolation in `run_crawl`, next to the existing blogger iteration and task-state ownership. Track discovery failures separately from `failed_notes`, log the affected blogger, preserve collected results, and select `COMPLETED_WITH_ERRORS` when the task finishes with any discovery failure.

**Tech Stack:** Python 3.11, Celery, SQLAlchemy, pytest, OpenCLI adapter.

## Global Constraints

- Do not catch `AuthenticationRequired`, `ExecutionStopped`, or `ExecutionSuperseded` as ordinary blogger failures.
- Do not increment `failed_notes` for account-discovery errors.
- Do not log signed URLs, Cookie values, JWTs, or complete `xsec_token` values.
- Do not change keyword discovery, note processing, OCR, extraction, deduplication, or reports.

---

### Task 1: Isolate per-blogger discovery failures

**Files:**
- Modify: `backend/tests/test_crawl_task_resilience.py`
- Modify: `backend/app/tasks/crawl_task.py:282-383`

**Interfaces:**
- Consumes: `OpenCLIAdapter.blogger_notes(username: str, profile_url: str) -> list[dict]`.
- Produces: existing `run_crawl(task_id: int, run_token: str | None)` with per-blogger ordinary-error isolation and unchanged external API.

- [x] **Step 1: Write failing ordinary-error isolation test**

Create two enabled bloggers bound to `nb`. Make the first `blogger_notes()` raise `RuntimeError("user store was not found")`, make the second return one signed note, and replace `process_note()` with a recorder. Assert the second blogger is called, the signed note reaches the recorder, the task is `COMPLETED_WITH_ERRORS`, and the failed blogger appears in task logs.

- [x] **Step 2: Write failing authentication-boundary test**

Make the first blogger raise `AuthenticationRequired("login")`. Assert the task becomes `PAUSED` and the second blogger is not called.

- [x] **Step 3: Run the two tests and verify RED**

Run:

```bash
uv run --project backend pytest -q \
  backend/tests/test_crawl_task_resilience.py::test_one_blogger_discovery_failure_does_not_discard_other_results \
  backend/tests/test_crawl_task_resilience.py::test_blogger_authentication_failure_still_pauses_the_batch
```

Expected: the ordinary-error test fails because `run_crawl` currently enters `FAILED`; the authentication test documents the existing boundary.

- [x] **Step 4: Implement minimal blogger isolation**

Before discovery, initialize:

```python
discovery_failures = 0
last_discovery_error: str | None = None
```

Wrap only the `blogger_notes()` call:

```python
try:
    items = adapter.blogger_notes(username, blogger.profile_url or "")
except (AuthenticationRequired, ExecutionStopped, ExecutionSuperseded):
    raise
except Exception as exc:
    discovery_failures += 1
    last_discovery_error = f"博主 {username!r} 抓取失败：{exc}"
    task.error_message = last_discovery_error
    db.commit()
    log(db, task.id, "ERROR", last_discovery_error)
    continue
```

At normal completion, select the final state with both failure sources:

```python
task.status = "COMPLETED_WITH_ERRORS" if task.failed_notes or discovery_failures else "COMPLETED"
if last_discovery_error and not task.error_message:
    task.error_message = last_discovery_error
```

- [x] **Step 5: Run focused regressions**

Run:

```bash
uv run --project backend pytest -q \
  backend/tests/test_crawl_task_resilience.py \
  backend/tests/test_crawl_execution_ownership.py \
  backend/tests/test_crawl_auto_stop_previous.py
```

Expected: all pass; stop and authentication semantics remain unchanged.

- [x] **Step 6: Commit Task 1**

```bash
git add backend/app/tasks/crawl_task.py backend/tests/test_crawl_task_resilience.py
git commit -m "fix: isolate blogger discovery failures"
```

---

### Task 2: Verify task #7 and close the TODO

**Files:**
- Modify: `tests/test-blogger-discovery-resilience.md`
- Modify: `docs/TODO.md`
- Modify: `docs/superpowers/specs/2026-07-20-blogger-discovery-resilience-design.md`

**Interfaces:**
- Consumes: the updated `run_crawl` and existing `POST /tasks/7/restart` behavior.
- Produces: real-run evidence without sensitive signed URLs.

- [x] **Step 1: Run full automated verification**

Run:

```bash
make test
git diff --check
```

Expected: backend and frontend component suites exit 0; formatting check is clean.

- [x] **Step 2: Reload the worker and restart task #7**

Ensure the worker uses the new code, restart task `#7` with its stored parameters, and monitor only sanitized counters and log summaries.

- [x] **Step 3: Verify real acceptance**

Assert:

- `keywords=0 bloggers=5`;
- “从零发现宁波” reports `N > 0` signed notes;
- ordinary blogger snapshot errors are logged but do not make the whole task `FAILED` before processing;
- `downloaded_notes > 0`;
- current-run logs contain neither `Missing url` nor “requires a full signed URL”.

- [x] **Step 4: Update docs and TODO**

Set the spec status to `已通过持续授权审核并实现`, add automated and real task results to the test document, and move the task #7 TODO into `已完成`.

- [ ] **Step 5: Commit acceptance evidence**

```bash
git add docs/TODO.md docs/superpowers/specs/2026-07-20-blogger-discovery-resilience-design.md tests/test-blogger-discovery-resilience.md docs/superpowers/plans/2026-07-20-blogger-discovery-resilience.md
git commit -m "docs: verify resilient blogger discovery"
```
