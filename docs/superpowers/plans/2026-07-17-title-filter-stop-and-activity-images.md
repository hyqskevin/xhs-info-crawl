# Title Filter, Safe Stop, and Activity Images Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Filter keyword search results by exact title containment, safely stop and resume crawl tasks, and show authenticated source images in a wider activity detail drawer.

**Architecture:** Add one persisted skip counter and cooperative stop states to `CrawlTask`. Keep title matching as a small pure pipeline service and preserve the matched keyword on each search result before URL deduplication. Enrich activity detail through existing Note/NoteImage relations and stream images through an authenticated, path-confined API; the Vue client loads image blobs and renders them with Element Plus.

**Tech Stack:** Python 3.11, FastAPI, SQLAlchemy, Alembic, Celery filesystem broker, SQLite, Vue 3, TypeScript, Axios, Element Plus, Vitest, Playwright.

## Global Constraints

- Phase one remains directly runnable locally with SQLite and the filesystem Celery broker; do not add Redis, MinIO, or Docker.
- UI components and icons must come from Element Plus and `@element-plus/icons-vue`; do not use Emoji or custom UI controls.
- Keyword search results pass only when the note title contains the exact corresponding keyword; blogger results bypass keyword title filtering.
- Stop is cooperative: finish the current note, retain committed data, then stop before the next note.
- Images remain under the configured data directory and are never exposed through a public static directory.

---

### Task 1: Persist skipped progress

**Files:**
- Create: `backend/migrations/versions/0005_task_skip_progress.py`
- Modify: `backend/app/models/task.py`
- Modify: `backend/app/api/v1/dashboard.py`
- Test: `backend/tests/test_config_task_duplicate_api.py`

**Interfaces:**
- Produces: `CrawlTask.skipped_notes: int` and dashboard `last_task.skipped_notes`.
- Progress formula: `(extracted_notes + failed_notes + skipped_notes) / total_notes * 100`.

- [ ] **Step 1: Write the failing dashboard progress test.**

Create a task with `total_notes=20`, `extracted_notes=5`, `failed_notes=1`, `skipped_notes=4`; assert the summary includes `skipped_notes: 4` and `progress_percent: 50.0`.

- [ ] **Step 2: Run the test and verify RED.**

Run: `backend/.venv/bin/pytest backend/tests/test_config_task_duplicate_api.py::test_dashboard_summary_contains_latest_task_progress -q`

Expected: FAIL because `CrawlTask` does not accept `skipped_notes`.

- [ ] **Step 3: Add the model, migration, and summary field.**

Use migration revision `0005_task_skip_progress`, down revision `0004_crawl_progress`, and:

```python
op.add_column("crawl_tasks", sa.Column("skipped_notes", sa.Integer(), nullable=False, server_default="0"))
```

Add `skipped_notes` to the model with `default=0`. Include it in dashboard serialization and the progress numerator.

- [ ] **Step 4: Run the focused test and migration test.**

Run: `backend/.venv/bin/pytest backend/tests/test_config_task_duplicate_api.py -q`

Expected: PASS.

- [ ] **Step 5: Commit.**

```bash
git add backend/migrations/versions/0005_task_skip_progress.py backend/app/models/task.py backend/app/api/v1/dashboard.py backend/tests/test_config_task_duplicate_api.py
git commit -m "feat: persist skipped crawl progress"
```

### Task 2: Enforce exact keyword containment in search titles

**Files:**
- Modify: `backend/app/services/pipeline.py`
- Modify: `backend/app/tasks/crawl_task.py`
- Test: `backend/tests/test_crawl_task_resilience.py`

**Interfaces:**
- Produces: `title_matches_keywords(title: str, keywords: list[str]) -> bool`.
- Search result metadata: internal key `_matched_keywords: list[str]`; blogger results omit the key.

- [ ] **Step 1: Write failing pure matching and deduplication tests.**

Cover these assertions:

```python
assert title_matches_keywords("宁波周末活动合集", ["活动"])
assert title_matches_keywords("SUMMER EXHIBITION", ["exhibition"])
assert not title_matches_keywords("宁波发票红包过期", ["活动", "展览"])
assert title_matches_keywords("宁波展览", ["活动", "展览"])
```

Also assert URL deduplication merges `_matched_keywords` from duplicate search results instead of discarding the later keyword.

- [ ] **Step 2: Run tests and verify RED.**

Run: `backend/.venv/bin/pytest backend/tests/test_crawl_task_resilience.py -q`

Expected: FAIL because matching and keyword-aware deduplication do not exist.

- [ ] **Step 3: Implement pure matching and keyword-aware deduplication.**

Normalize only with `strip()` and `casefold()`:

```python
def title_matches_keywords(title: str, keywords: list[str]) -> bool:
    normalized = (title or "").strip().casefold()
    return bool(normalized) and any(keyword.strip().casefold() in normalized for keyword in keywords if keyword.strip())
```

When duplicate URLs are encountered, merge unique `_matched_keywords` in search order.

- [ ] **Step 4: Write a failing crawl integration test.**

Use a fake adapter whose search returns one matching title and one unrelated title. Assert the unrelated URL never reaches `adapter.note` or `adapter.download`, while `skipped_notes` becomes 1 and an INFO log contains `标题未包含关键词`.

- [ ] **Step 5: Run the integration test and verify RED.**

Run: `backend/.venv/bin/pytest backend/tests/test_crawl_task_resilience.py -q`

Expected: FAIL because `run_crawl` processes both results.

- [ ] **Step 6: Attach matched keywords and skip before detail download.**

For keyword searches, copy each result and add its originating keyword to `_matched_keywords`. Blogger results remain untagged. Before `process_note`, skip tagged results whose title matches none of the tags, increment `skipped_notes`, commit, and log the URL/title/keywords. Do not call MiniMax or OCR for skipped results.

- [ ] **Step 7: Run focused tests and commit.**

Run: `backend/.venv/bin/pytest backend/tests/test_crawl_task_resilience.py -q`

```bash
git add backend/app/services/pipeline.py backend/app/tasks/crawl_task.py backend/tests/test_crawl_task_resilience.py
git commit -m "feat: filter crawl results by title keyword"
```

### Task 3: Add cooperative safe stop and stopped-task resume

**Files:**
- Modify: `backend/app/api/v1/tasks.py`
- Modify: `backend/app/tasks/crawl_task.py`
- Test: `backend/tests/test_config_task_duplicate_api.py`
- Test: `backend/tests/test_crawl_task_resilience.py`

**Interfaces:**
- Produces: `POST /api/v1/tasks/{task_id}/stop`.
- Adds states: `STOP_REQUESTED`, `STOPPED`.
- Changes restart eligibility from only `FAILED` to `FAILED | STOPPED`.

- [ ] **Step 1: Write failing stop endpoint tests.**

Assert:

```python
PENDING -> STOPPED
RUNNING -> STOP_REQUESTED
STOP_REQUESTED -> STOP_REQUESTED  # idempotent
COMPLETED -> 409
unknown id -> 404
```

- [ ] **Step 2: Run endpoint tests and verify RED.**

Run: `backend/.venv/bin/pytest backend/tests/test_config_task_duplicate_api.py -q`

Expected: FAIL with 404/405 because the endpoint is absent.

- [ ] **Step 3: Implement the endpoint and restart eligibility.**

The endpoint updates state and writes `TaskLog(message="已请求安全停止")`. Restart accepts `FAILED` and `STOPPED`, resets transient error/current-stage fields, and queues the same task ID.

- [ ] **Step 4: Write a failing worker stop-boundary test.**

Use two synthetic results. Make processing the first result set task status to `STOP_REQUESTED`; assert the second processor is not called, the first committed result remains, and the final status is `STOPPED`.

- [ ] **Step 5: Run worker test and verify RED.**

Run: `backend/.venv/bin/pytest backend/tests/test_crawl_task_resilience.py -q`

Expected: FAIL because the loop does not inspect stop state.

- [ ] **Step 6: Implement cooperative checks.**

Refresh the task after search and before each note. On `STOP_REQUESTED`, set `STOPPED`, clear `current_stage/current_note`, set `finished_at`, commit, log `任务已安全停止`, and return without overwriting the state with `COMPLETED`.

- [ ] **Step 7: Run tests and commit.**

Run: `backend/.venv/bin/pytest backend/tests/test_config_task_duplicate_api.py backend/tests/test_crawl_task_resilience.py -q`

```bash
git add backend/app/api/v1/tasks.py backend/app/tasks/crawl_task.py backend/tests/test_config_task_duplicate_api.py backend/tests/test_crawl_task_resilience.py
git commit -m "feat: safely stop and resume crawl tasks"
```

### Task 4: Return activity notes and authenticated source images

**Files:**
- Modify: `backend/app/api/v1/activities.py`
- Test: `backend/tests/test_activities_api.py`

**Interfaces:**
- `GET /api/v1/activities/{activity_id}` returns `note` and `images`.
- `GET /api/v1/activities/{activity_id}/images/{image_id}` returns `FileResponse`.

- [ ] **Step 1: Write failing detail and image tests.**

Create a Note, Activity, and two NoteImage rows with files under a temporary configured data directory. Assert detail returns note fields and two image URLs. Assert an authenticated image request returns the bytes; no token returns 401; a mismatched image ID and a storage key resolving outside `DATA_DIR` return 404.

- [ ] **Step 2: Run tests and verify RED.**

Run: `backend/.venv/bin/pytest backend/tests/test_activities_api.py -q`

Expected: FAIL because detail returns `note: null`, `images: []` and no image route exists.

- [ ] **Step 3: Implement detail serialization.**

Load `Note` by `activity.note_id`, then load `NoteImage` rows ordered by ID. Return:

```python
{"note": {"id": note.id, "title": note.title, "content": note.content,
          "source_url": note.source_url, "status": note.status},
 "images": [{"id": image.id, "ocr_status": image.ocr_status,
              "ocr_text": image.ocr_text,
              "url": f"/activities/{activity.id}/images/{image.id}"}]}
```

- [ ] **Step 4: Implement the protected image response.**

Resolve `(settings.data_dir / image.storage_key).resolve()`, verify it is inside `settings.data_dir.resolve()` with `Path.is_relative_to`, verify the file exists, then return `FileResponse(path)`. Query image by both `image_id` and the activity note ID.

- [ ] **Step 5: Run tests and commit.**

Run: `backend/.venv/bin/pytest backend/tests/test_activities_api.py -q`

```bash
git add backend/app/api/v1/activities.py backend/tests/test_activities_api.py
git commit -m "feat: serve protected activity source images"
```

### Task 5: Add dashboard stop controls and skipped progress

**Files:**
- Modify: `frontend/src/api/client.ts`
- Modify: `frontend/src/views/DashboardView.vue`
- Modify: `frontend/src/views/DashboardView.spec.ts`

**Interfaces:**
- Adds `api.stopTask(id: number)`.
- Consumes `skipped_notes`, `STOP_REQUESTED`, `STOPPED`.

- [ ] **Step 1: Write failing component tests.**

Mock a RUNNING task and assert “停止抓取” is visible. Confirm the Element Plus message box, trigger the button, and assert `stopTask(4)`. Mock STOPPED and assert “已停止” plus “继续抓取”. Assert “已跳过4” is displayed.

- [ ] **Step 2: Run test and verify RED.**

Run: `npm test -- --run src/views/DashboardView.spec.ts`

Expected: FAIL because the controls and API method are absent.

- [ ] **Step 3: Implement API and UI.**

Add `stopTask:(id:number)=>http.post(\`/tasks/${id}/stop\`)`. Use `ElMessageBox.confirm`, a separate `stopping` ref, `STOP_REQUESTED: '正在停止'`, `STOPPED: '已停止'`, and show restart for FAILED/STOPPED. Add “已跳过” to progress summary.

- [ ] **Step 4: Run test and commit.**

Run: `npm test -- --run src/views/DashboardView.spec.ts`

```bash
git add frontend/src/api/client.ts frontend/src/views/DashboardView.vue frontend/src/views/DashboardView.spec.ts
git commit -m "feat: stop crawl tasks from dashboard"
```

### Task 6: Widen activity detail and render authenticated images

**Files:**
- Modify: `frontend/src/api/client.ts`
- Modify: `frontend/src/views/ActivitiesView.vue`
- Modify: `frontend/src/views/ActivitiesView.spec.ts`

**Interfaces:**
- Adds `api.activityImage(activityId: number, imageId: number)` returning a Blob.
- Drawer owns `imageUrls: string[]` and releases each URL on close/reload/unmount.

- [ ] **Step 1: Write failing component tests.**

Mock detail with a note and two images. Assert the drawer has size `70%`, displays source title/link, calls both image requests, renders two `ElImage` components under “来源页面图片”, and calls `URL.revokeObjectURL` when closed. Add a no-image assertion for `ElEmpty`.

- [ ] **Step 2: Run test and verify RED.**

Run: `npm test -- --run src/views/ActivitiesView.spec.ts`

Expected: FAIL because detail width, note fields, and image loading are absent.

- [ ] **Step 3: Implement blob loading and cleanup.**

Add `activityImage` with `responseType:'blob'`. In `show`, fetch detail, then `Promise.all` image blobs and create object URLs. Add `releaseImages()` and call it before reload, on drawer close, and in `onUnmounted`.

- [ ] **Step 4: Implement Element Plus layout.**

Set `:size="detailDrawerSize"`, with a responsive computed value of `70%` desktop and `95%` below 768px. Below `ElDescriptions`, render a CSS grid of `ElImage` with `preview-src-list`, or `ElEmpty description="暂无来源图片"`.

- [ ] **Step 5: Run test and commit.**

Run: `npm test -- --run src/views/ActivitiesView.spec.ts`

```bash
git add frontend/src/api/client.ts frontend/src/views/ActivitiesView.vue frontend/src/views/ActivitiesView.spec.ts
git commit -m "feat: show activity source images"
```

### Task 7: Update specifications, E2E coverage, migrate, and verify

**Files:**
- Modify: `docs/api-doc.md`
- Modify: `docs/crawler-design.md`
- Modify: `docs/database-design.md`
- Modify: `docs/ui-design.md`
- Modify: `tests/test-crawler-engine.md`
- Modify: `tests/test-task-scheduling.md`
- Modify: `tests/test-frontend-ui-e2e.md`
- Modify: `tests/EXECUTION_STATUS.md`
- Modify: `frontend/e2e/business.spec.ts`
- Modify: `frontend/e2e/documented-flows.spec.ts`

**Interfaces:**
- Documents exact-title filtering, `skipped_notes`, stop/restart states, protected images, and drawer layout.

- [ ] **Step 1: Add Playwright scenarios before implementation verification.**

Add browser tests that:

1. show and confirm “停止抓取” for a RUNNING dashboard task and assert `/tasks/4/stop`;
2. show “继续抓取” for STOPPED;
3. open activity detail, assert the wide drawer contains source title and two images, and click one image to open Element Plus preview.

- [ ] **Step 2: Update design and test documentation.**

Record the new endpoint/state/data fields and map each component/browser scenario in `tests/test-frontend-ui-e2e.md`. Update execution counts only after successful runs.

- [ ] **Step 3: Stop the old worker, migrate, and restart local services.**

Run from `backend/`:

```bash
.venv/bin/alembic -c alembic.ini upgrade head
```

Restart `./scripts/dev-worker.sh` so the worker imports the new task code. Keep API and web services available at ports 8000 and 5173.

- [ ] **Step 4: Run full verification.**

```bash
backend/.venv/bin/pytest backend/tests -q
npm --prefix frontend test -- --run
npm --prefix frontend run build
npm --prefix frontend run test:e2e
```

Expected: zero failures; only the documented optional token-refresh test may remain skipped.

- [ ] **Step 5: Perform a real local smoke test.**

Start a keyword crawl whose search result set includes matching and non-matching titles. Confirm skipped count increases without note/download calls for rejected titles. Request safe stop and confirm the current note completes, state becomes STOPPED, counters stop increasing, and the same task can resume. Open an existing activity with stored images and confirm authenticated images load in the wider drawer.

- [ ] **Step 6: Commit.**

```bash
git add docs tests frontend/e2e
git commit -m "test: cover title filtering stop and activity images"
```
