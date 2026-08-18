# v0.6.0 - Launcher UI Hardening & Storage Base-Dir Mode

**Release date:** 2026-08-18
**Predecessor:** v0.5.7 (launcher 子进程清理;v0.5.0 ~ v0.5.7 累计: 18 commits,见 git log v0.3.0..v0.5.7)

## Highlights

This release hardens the launcher UI (relative-path asset bundling, status-port resolution, base-dir storage mode) and the packaging pipeline (OCR deps bundled, fixture copy, build pre/post checks, release-check script). Users who only want to relocate data now edit a single `DATA_DIR` field instead of nine separate path variables.

## New Features

- `feat(storage)`: **base-dir storage mode** — user sets only `DATA_DIR`; `IMAGE_DIR` / `EXPORT_DIR` / `ARCHIVE_DIR` / `BACKUP_DIR` / `CELERY_FOLDER` / `TASK_REGISTRY_PATH` / `TMP_DIR` / `PADDLE_PDX_CACHE_HOME` / `HF_HOME` / `CHROME_USER_DATA_DIR` / `DATABASE_URL` are auto-derived. `.env.example` documents the derived paths. Launcher UI "存储路径" panel shows the data_dir + log_dir fields and 6 read-only subdir previews.
- `feat(launcher-ui)`: **"打开" button** beside data_dir, log_dir, and each of the 6 subdir previews — opens Finder to that directory via PyWebView `api.open_dir(path)`.
- `feat(packaging)`: **`scripts/release-check.sh <version>`** — pre-flight check before tagging (workspace clean, dist built, fixtures present, pytest green, tag not duplicated). Print colored pass/fail per check.
- `feat(launcher-ocr)`: **OCR test goes through direct import, not HTTP** — `/ocr/test` now calls `app.services.diagnostics_ocr.probe_ocr(settings)` directly, eliminating the prior 401 (JWT-required HTTP proxy was wrong for a launcher-side probe).

## Fixes

- `fix(launcher-ui)`: Vite build now always outputs `./assets/...` (relative paths), so PyWebView's `file://` protocol and the static HTTP server at `127.0.0.1:<web_port>/` can both load the assets. Previous default `/assets/...` caused a blank launcher window and broken sub-routes on the business frontend. Hardened in both `frontend/package.json` and `launcher/ui/package.json` (`--base './'` flag).
- `fix(launcher-ui)`: API-key input no longer shows duplicate eye icons (`show-password` prop + manual toggle button conflicted). Removed the redundant Element Plus prop.
- `fix(launcher-ui)`: Subdir-preview rows displayed paths truncated by CSS (e.g. `/Users/.../xhs-info-crawl/images` showed as `~/xhs-info-crawl/images`); forced `word-break: break-all` + monospace font + flex layout so full paths are visible.
- `fix(launcher-ui)`: `initBaseUrlFromLocation` now resolves status_port from `window.pywebview.api.getStatusPort()` (PyWebView JS-API injection) as the primary source, with the `?statusPort=` query-string as fallback. macOS WKWebView does not always propagate the query string into `window.location.search`.
- `fix(packaging)`: OCR dependencies (`paddleocr`, `paddlepaddle`) now installed into the packaged venv — `package-macos.sh` step 2.1. Without this the launcher "已安装 · migrated-from-dev" chip was misleading; OCR would fail at first note.
- `fix(packaging)`: `backend/tests/fixtures/ocr_test.png` now copied into the `.app` (was excluded by the previous blanket `exclude='tests/'`). Without this, launcher "测试 OCR" returns `test_image_missing`.
- `fix(packaging)`: `.env.example` no longer ships the nine relative-path subdir vars (now derived from `DATA_DIR`). One field for users to set; everything else propagates.

## Packaging Pipeline Hardening

- `package-macos.sh` pre-build checks: refuses to proceed if `frontend/dist/index.html` or `launcher/ui/dist/index.html` is missing, or if either contains absolute `/assets/` paths.
- `package-macos.sh` post-build checks: refuses to mark the zip clean if `paddleocr` / `paddlepaddle` / `ocr_test.png` are missing from the `.app` or absolute asset paths slipped through.
- `scripts/release-check.sh` runs the same checks plus `pytest backend` before tagging.

## Documentation

- `docs/superpowers/specs/2026-08-17-launcher-ui-baseurl-pywebview-design.md` — relative-path bundling + status-port resolution design.
- `docs/superpowers/specs/2026-08-17-launcher-storage-base-dir-design.md` — base-dir storage mode.
- `docs/superpowers/specs/2026-08-17-launcher-ocr-direct-design.md` — direct-import OCR probe rationale.

## Tests

| Suite | Count |
|---|---|
| Backend (pytest) | unchanged from v0.3.0 baseline |
| Frontend (vitest) | unchanged from v0.3.0 baseline |
| Launcher UI (vitest) | 78 passed |
| OCR smoke (packaged) | ok=true · "Hello OCR Test 2026" · ~6s |

## Upgrade Notes

Drop-in compatible with v0.5.7. The launcher migrates to the new base-dir mode automatically on first start: any existing `~/.xhs-info-crawl/{images,exports,archive,backups,celery,run,tmp,paddlex,huggingface,chrome-pool}/` data continues to work because `DATA_DIR` defaults to that path. Users moving data to a new location only edit `DATA_DIR` in the launcher UI.

## Install

```bash
git clone https://github.com/hyqskevin/xhs-info-crawl.git
cd xhs-info-crawl
git checkout v0.6.0
# Production (packaged):
#   download xhs-info-crawl-0.6.0-macos-arm64.zip, unzip, double-click .app
# Development (4 terminals):
make init
make dev-api
make dev-worker
make dev-beat
make dev-web
```

See [`INSTALL.md`](INSTALL.md) for full details.

---

# v0.3.0 - Scheduled Crawls, Dashboard Analytics & Hardening

**Release date:** 2026-07-27
**Predecessor:** v0.2.0 (stage-one backlog closure)

## Highlights

This release adds DB-driven scheduled crawling and dashboard analytics, then lands a full-project audit hardening pass (security, timezone consistency, migration chain, dead-code removal).

- Schedule weekly crawls (weekday + time, city, keyword groups, blogger groups) from the new 定时任务 page; Celery beat dispatches them from the DB every minute.
- Dashboard shows per-schedule last-run status, a crawl trend line chart (discovered/success/failed per run), a success-rate pie chart, weekly summary cards and the 5 most recent task logs.
- Keyword groups are first-class entities (many-to-many with cities); crawl scope semantics are explicit: keywords only, bloggers only, or both.
- Crawl archives are organized per city / ISO week folder.

## New Features

- `feat(schedules)`: `scheduled_crawls` + `blogger_groups` tables, `/schedules` and `/settings/blogger-groups` CRUD, beat-driven `scheduled-crawl-dispatch` (slot-idempotent, skips when a task is active).
- `feat(dashboard)`: `GET /dashboard/analytics` (recent tasks, status counts, schedule statuses) + ECharts trend/pie cards.
- `feat(dashboard)`: Weekly summary cards (notes/activities this week, pending duplicates) + recent task logs card.
- `feat(reports)`: `DELETE /api/v1/reports/{id}` and rendered Markdown preview (marked + DOMPurify).
- `feat(crawl)`: Search rate limiting — random 10-15s interval between searches and a 500/week search quota (`search_usage` table).
- `feat(crawl)`: Login preflight at task start; unauthenticated tasks pause immediately with scan-code guidance instead of failing per-blogger.
- `feat(opencli)`: `OPENCLI_BIN` config + startup preflight (fail-fast with actionable message when the binary is missing).
- `feat(models)`: `keyword_groups` many-to-many with cities; `POST /tasks/crawl` accepts `keyword_group_ids`.
- `feat(posters)`: Poster templates/tasks and note-image rendering pipeline.

## Fixes & Hardening

- `fix(security)`: Poster note-image path validation unified to `Path.is_relative_to` (prefix-sibling escape returns 404).
- `fix(crawl)`: `note_id_published_at` took the user id instead of the note id from `/user/profile/<uid>/<noteid>` URLs — publish times were bloggers' registration dates; includes an idempotent backfill script.
- `fix(review)`: Batch approve validates ≥1 valid sub-activity per note (with `skipped` detail); duplicate merge on non-pending candidates returns 409; deleting a blogger/city cascades association rows.
- `fix(time)`: Timezone convention unified to Beijing wall-clock naive datetimes (documented in `docs/database-design.md`); dashboard weekly counts now really mean "this week" (Mon 00:00 Asia/Shanghai).
- `fix(migrations)`: Fresh-database `alembic upgrade head` repaired end-to-end (idempotent guards in 0002–0016); `cities.name` unique index declared in the model.
- `refactor`: Dead code removed (legacy functional crawler, old activity-level report export incl. a latent `NameError`, `task_lock`, unused pipeline paths); activity-level `duplicate_candidates` writes stopped and 1160 stale rows cleaned.
- `chore(config)`: `.env.example` adds `INITIAL_ADMIN_PASSWORD`, `MINIMAX_VISION_MODEL`, `OPENCLI_BIN`; `docs/api-doc.md` covers all 59 endpoints.

## Tests

| Suite | Count |
|---|---|
| Backend (pytest) | 501 passed, 1 skipped |
| Frontend (vitest) | 68 passed |
| Frontend build | green |

## Upgrade Notes

Run `alembic upgrade head` to apply `0012`–`0016` (seed admin, keyword groups, poster models, scheduled crawls + blogger groups, search usage). On an empty database `0012` seeds an `admin` user — set `INITIAL_ADMIN_PASSWORD` before first upgrade in shared environments. After upgrading, restart celery worker and beat (models/tasks changed).

## Install

```bash
git clone https://github.com/hyqskevin/xhs-info-crawl.git
cd xhs-info-crawl
git checkout v0.3.0
make init
# in 4 terminals:
make dev-api
make dev-worker
make dev-beat
make dev-web
```

See [`INSTALL.md`](INSTALL.md) for full details.

---

# v0.2.0 - Stage One Amendments

**Release date:** 2026-07-21
**Predecessor:** v0.1.0 (initial scaffold + first half of stage one features)

## Highlights

This release closes most of the stage-one backlog. The system now:

- Scrapes XHS by city/keyword/blogger, with stop/restart and login-state recovery.
- Performs OCR on each note image and extracts structured activities via LLM.
- Provides a review workflow (single + batch), edit, reprocess.
- Auto-detects near-duplicate notes (`SequenceMatcher` similarity) and lets the user merge / ignore.
- Generates weekly Markdown / Excel reports.
- Allows mass-importing blogger whitelists via Excel/CSV.
- Survives "missing-url", "blogger-info-incomplete", and XHS verification challenges.

## New Features

- `feat(notes)`: Activity list keyword search (`ilike` on title/content).
- `feat(tasks)`: Tasks page batch delete (`DELETE /api/v1/tasks/batch`).
- `feat(notes)`: List summary length guard (`MAX_OCR_BLOCKS=5`, `MAX_SUMMARY_BYTES=4096`, new `summary_truncated` flag).
- `feat(notes)`: Parse `published_at` from XHS note-id ObjectID (first 8 hex = epoch seconds, +8h Asia/Shanghai).
- `feat(notes)`: Backfill historical `published_at` for notes with null date.
- `feat(crawler)`: Pause-on-verification flow that keeps the Chrome page open for manual recovery.
- `feat(notes)`: Re-extract sub-activities endpoint `POST /notes/{id}/reprocess`.

## Changes

- `refactor(activities)`: Remove per-activity `status` column; rely on `Note.review_status` for weekly reports.
- `chore(reports)`: Roll back ISO-week display and per-week sort per user feedback.
- `fix(dashboard)`: Hide the error alert when `last_task.status` is `COMPLETED_WITH_ERRORS`.

## Documentation

- `docs/superpowers/specs/*.md` — 14 design specs covering UI, dedup, RBAC, multi-account, city+keyword groups, dedupe cities.
- `docs/superpowers/qa/dedup-rules.md` — Q&A: how is dedup done?
- `INSTALL.md` — install / run / test instructions for a fresh machine.
- `README.md` — rewritten overview.
- `tests/*.md` — E2E spec docs.

## Tests

| Suite | Count |
|---|---|
| Backend (pytest) | 309 passed, 1 skipped |
| Frontend (vitest) | 48 passed |
| Frontend build | green |

## Known Issues

See `docs/TODO.md` → "当前待办" for stage-two preparations and open follow-ups.

## Upgrade Notes

This tag is **drop-in compatible** with v0.1.0 DB. Run `alembic upgrade head` to apply `0011_activity_soft_delete`. No manual data migration required.

## Install

```bash
git clone https://github.com/hyqskevin/xhs-info-crawl.git
cd xhs-info-crawl
git checkout v0.2.0
make init
# in 4 terminals:
make dev-api
make dev-worker
make dev-beat
make dev-web
```

See [`INSTALL.md`](INSTALL.md) for full details.
