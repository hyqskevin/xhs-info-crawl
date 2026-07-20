# Blogger Batch Import Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add transactional, idempotent Excel/CSV blogger whitelist import with an Element Plus upload UI.

**Architecture:** Keep file parsing and import planning in a dedicated backend service, expose raw-byte template/import endpoints, and let the existing settings view upload one selected file. Existing Blogger and BloggerCity tables remain the source of truth.

**Tech Stack:** FastAPI, SQLAlchemy, openpyxl, Python csv, Vue 3, Element Plus, Vitest, Playwright.

## Global Constraints

- Accept only `.xlsx` and UTF-8 `.csv`, maximum 2 MiB and 500 effective rows.
- Use configured city names in the file; never require or display city codes.
- Validate the whole file before a single transaction writes data.
- Use Element Plus components/icons and no emoji.

---

### Task 1: Backend parser and transactional importer

**Files:**
- Create: `backend/app/services/blogger_import.py`
- Create: `backend/tests/test_blogger_batch_import.py`

**Interfaces:**
- Produces `generate_blogger_template() -> bytes`.
- Produces `import_bloggers(db: Session, content: bytes, filename: str) -> dict[str, int]`.

- [x] Write failing parser tests for xlsx, csv, city separators and enabled values.
- [x] Write failing transaction tests for unknown city, duplicate/ambiguous identity and rollback.
- [x] Write failing idempotency test: first import creates, second import updates without increasing count.
- [x] Implement row dataclasses, parsers, validation plan and one-transaction apply.
- [x] Run `backend/tests/test_blogger_batch_import.py` green.

### Task 2: Template and import API

**Files:**
- Modify: `backend/app/api/v1/settings.py`
- Modify: `backend/tests/test_blogger_batch_import.py`

**Interfaces:**
- `GET /api/v1/settings/bloggers/import-template` returns xlsx attachment.
- `POST /api/v1/settings/bloggers/import?filename=list.xlsx` consumes raw bytes and returns counts.

- [x] Write failing auth, download, success, 422 and 2 MiB limit API tests.
- [x] Add endpoints with admin auth and stable error response containing row numbers.
- [x] Run import API tests and existing settings API tests green.
- [x] Commit backend implementation.

### Task 3: Element Plus import UI

**Files:**
- Modify: `frontend/src/api/client.ts`
- Modify: `frontend/src/views/SettingsView.vue`
- Modify: `frontend/src/views/SettingsView.spec.ts`

- [ ] Write failing component tests for blogger-only controls, raw file upload, loading, success refresh and row-error Toast.
- [ ] Add `downloadBloggerTemplate()` and `importBloggers(file)` API methods.
- [ ] Add Element Plus upload/template controls with `UploadFilled` and `Download` icons.
- [ ] Run SettingsView component tests green.

### Task 4: Browser flow, docs and closure

**Files:**
- Modify: `frontend/e2e/documented-flows.spec.ts`
- Create: `tests/test-blogger-batch-import.md`
- Modify: `docs/TODO.md`
- Modify: `docs/superpowers/specs/2026-07-20-blogger-batch-import-design.md`

- [ ] Add Playwright case for template download and successful batch import refresh.
- [ ] Run backend, frontend component and E2E full suites plus `git diff --check`.
- [ ] Record evidence, move TODO to completed and commit.
