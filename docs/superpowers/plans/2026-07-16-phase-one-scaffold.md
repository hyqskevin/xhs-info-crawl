# Phase One Frontend and Backend Scaffold Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a locally runnable phase-one scaffold with Vue 3, Element Plus, FastAPI, SQLite, Celery filesystem broker, repeatable commands, and automated smoke tests.

**Architecture:** A monorepo keeps `frontend/` and `backend/` independent while sharing root development commands. FastAPI owns configuration, health endpoints, SQLite initialization, and future REST modules; Celery reuses the same settings and uses a filesystem transport. The Vue shell consumes the health endpoint and uses only Element Plus components and `@element-plus/icons-vue` icons.

**Tech Stack:** Python 3.11+, FastAPI, Pydantic Settings, SQLAlchemy 2, Alembic, Celery 5, SQLite, pytest, Vue 3, TypeScript, Vite, Pinia, Vue Router, Element Plus, Vitest.

## Global Constraints

- Phase one must run locally without Docker, PostgreSQL, Redis, or MinIO.
- Vue 3, FastAPI, Celery Worker, and Celery Beat are phase-one components.
- Celery uses `filesystem://`; SQLite uses `data/app.db`; images and exports use `data/images/` and `data/exports/`.
- UI must use Element Plus and `@element-plus/icons-vue`; Emoji icons are prohibited.
- Prefer official Element Plus components over custom UI implementations.
- Runtime data under `data/` must not be committed.
- The scaffold establishes boundaries only; crawler, OCR, extraction, deduplication, and final report behavior are later feature tasks.

---

### Task 1: Repository and backend configuration foundation

**Files:**
- Create: `.gitignore`, `.editorconfig`, `.env.example`, `README.md`, `Makefile`
- Create: `backend/pyproject.toml`, `backend/app/__init__.py`, `backend/app/core/__init__.py`, `backend/app/core/config.py`
- Test: `backend/tests/test_config.py`

**Interfaces:**
- Produces: `Settings`, `get_settings()`, and `Settings.ensure_runtime_directories()`, used by API, database, storage, and Celery modules.

- [ ] **Step 1: Write a failing configuration test** that constructs `Settings(project_root=tmp_path)` and asserts SQLite, image, export, and broker directories resolve under the temporary project root.
- [ ] **Step 2: Run** `uv run --project backend pytest backend/tests/test_config.py -q` and confirm failure because `backend.app.core.config` does not exist.
- [ ] **Step 3: Implement settings and root project files**, using Pydantic Settings with relative paths derived from `PROJECT_ROOT` and directory creation isolated in `ensure_runtime_directories()`.
- [ ] **Step 4: Re-run the test** and confirm it passes.
- [ ] **Step 5: Commit** with `git commit -m "chore: initialize phase one project foundation"`.

### Task 2: FastAPI health endpoint and SQLite initialization

**Files:**
- Create: `backend/app/api/__init__.py`, `backend/app/api/v1/__init__.py`, `backend/app/api/v1/router.py`, `backend/app/api/v1/health.py`
- Create: `backend/app/core/database.py`, `backend/app/main.py`
- Test: `backend/tests/test_health.py`, `backend/tests/test_database.py`

**Interfaces:**
- Produces: `app: FastAPI`, `GET /api/v1/health`, `engine`, `SessionLocal`, `get_db()`, and `init_database()`.

- [ ] **Step 1: Write failing tests** asserting health returns `{"code": 200, "message": "success", "data": {"status": "ok", "database": "sqlite"}}` and `init_database()` creates the configured SQLite file.
- [ ] **Step 2: Run** `uv run --project backend pytest backend/tests/test_health.py backend/tests/test_database.py -q` and confirm imports fail.
- [ ] **Step 3: Implement the minimal API and database lifecycle**, with a versioned router and startup directory/database initialization.
- [ ] **Step 4: Re-run both test files** and confirm they pass.
- [ ] **Step 5: Commit** with `git commit -m "feat: add FastAPI health and SQLite foundation"`.

### Task 3: Local storage and Celery filesystem transport

**Files:**
- Create: `backend/app/storage/__init__.py`, `backend/app/storage/base.py`, `backend/app/storage/local.py`
- Create: `backend/app/tasks/__init__.py`, `backend/app/tasks/celery_app.py`, `backend/app/tasks/health.py`
- Test: `backend/tests/test_local_storage.py`, `backend/tests/test_celery_config.py`

**Interfaces:**
- Produces: `Storage` protocol, `LocalStorage.save/read/delete`, `celery_app`, and `health.ping` task.

- [ ] **Step 1: Write failing tests** asserting local storage returns relative object keys and blocks traversal, and Celery uses `filesystem://` with Monday 02:00 Asia/Shanghai beat configuration.
- [ ] **Step 2: Run** `uv run --project backend pytest backend/tests/test_local_storage.py backend/tests/test_celery_config.py -q` and confirm missing-module failures.
- [ ] **Step 3: Implement storage and Celery configuration**, sharing `Settings` and creating broker input/output/processed folders.
- [ ] **Step 4: Re-run both test files** and confirm they pass.
- [ ] **Step 5: Commit** with `git commit -m "feat: add local storage and celery filesystem broker"`.

### Task 4: Vue 3 and Element Plus application shell

**Files:**
- Create: `frontend/package.json`, `frontend/tsconfig.json`, `frontend/tsconfig.node.json`, `frontend/vite.config.ts`, `frontend/index.html`
- Create: `frontend/src/main.ts`, `frontend/src/App.vue`, `frontend/src/styles/main.css`
- Create: `frontend/src/router/index.ts`, `frontend/src/api/http.ts`, `frontend/src/api/health.ts`
- Create: `frontend/src/layouts/AppLayout.vue`, `frontend/src/views/DashboardView.vue`, `frontend/src/views/PlaceholderView.vue`
- Test: `frontend/src/views/DashboardView.spec.ts`

**Interfaces:**
- Consumes: `GET /api/v1/health`.
- Produces: routes for `/dashboard`, `/activities`, `/duplicates`, `/settings`, `/tasks`, and `/reports` in an Element Plus navigation shell.

- [ ] **Step 1: Write a failing Vitest component test** asserting the dashboard renders the application title, health status, and Element Plus cards without Emoji text.
- [ ] **Step 2: Run** `npm --prefix frontend test -- --run` and confirm failure because the Vue app does not exist.
- [ ] **Step 3: Implement the Vue shell** using `ElContainer`, `ElMenu`, `ElCard`, `ElTag`, `ElResult`, and icons imported from `@element-plus/icons-vue`.
- [ ] **Step 4: Re-run Vitest** and confirm it passes.
- [ ] **Step 5: Commit** with `git commit -m "feat: add Vue Element Plus application shell"`.

### Task 5: Local developer workflow and scaffold verification

**Files:**
- Create: `scripts/init.sh`, `scripts/dev-api.sh`, `scripts/dev-worker.sh`, `scripts/dev-beat.sh`, `scripts/dev-web.sh`
- Modify: `Makefile`, `README.md`
- Test: `backend/tests/test_scaffold_contract.py`

**Interfaces:**
- Produces: `make init`, `make dev-api`, `make dev-worker`, `make dev-beat`, `make dev-web`, `make test`, and `make build`.

- [ ] **Step 1: Write a failing scaffold contract test** asserting required directories, environment keys, and executable scripts exist.
- [ ] **Step 2: Run** `uv run --project backend pytest backend/tests/test_scaffold_contract.py -q` and confirm missing-file failures.
- [ ] **Step 3: Implement scripts and documentation** with commands that derive the repository root and avoid global package installation.
- [ ] **Step 4: Run complete verification:** `uv run --project backend pytest backend/tests -q`, `npm --prefix frontend test -- --run`, and `npm --prefix frontend run build`.
- [ ] **Step 5: Inspect** `git status --short` and `git diff --check`, then commit with `git commit -m "chore: complete local development scaffold"`.

## Plan Self-Review

- The plan covers the approved scaffold boundary: Git, backend, frontend, SQLite, Celery filesystem broker, local storage, commands, tests, and documentation.
- Phase-two services and business implementation are intentionally excluded and preserved as replaceable interfaces.
- All UI implementation explicitly depends on Element Plus official components and icons; Emoji icons are excluded.
- File and interface names are consistent across tasks.
