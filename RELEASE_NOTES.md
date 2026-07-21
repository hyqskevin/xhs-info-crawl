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
