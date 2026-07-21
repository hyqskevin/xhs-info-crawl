# Install & Run xhs-info-crawl

This document describes how to bring up the project on a fresh Linux/macOS machine for **development / local use**. For production-grade deployment with Docker, see [docs/superpowers/specs/2026-07-21-deployment-design.md](docs/superpowers/specs/2026-07-21-deployment-design.md) (stage two TODO).

## 1. System Requirements

| Tool | Version | Used by |
|------|---------|---------|
| Python | ≥ 3.11 | backend |
| Node.js | ≥ 18 LTS | frontend |
| npm | bundled with Node | frontend |
| Git | any recent | source |
| macOS / Linux | OS | host |
| OpenCLI | latest | xhs crawler |
| Chrome | any recent | xhs login / opencli |
| (Optional) Make | any | shortcut targets |

> Windows users: install WSL2 and follow the Linux steps inside it.

## 2. Clone

```bash
git clone https://github.com/hyqskevin/xhs-info-crawl.git
cd xhs-info-crawl
# pick a release tag, e.g.
git checkout v0.2.0
```

## 3. Backend (FastAPI + Celery + SQLite)

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[ocr]"           # ocr extra installs paddleocr / paddlepaddle
```

### 3.1 Initial database

```bash
export INITIAL_ADMIN_PASSWORD="ChangeMe123!"      # OPTIONAL: override default admin password
alembic upgrade head                                # apply all migrations
```

> Migration `0012_seed_admin` (TODO, not yet committed) inserts an `admin` user when none exists.
> Without that migration you must create the admin via the SQL insert described in [docs/database-design.md](docs/database-design.md).

### 3.2 Environment variables (optional)

| Variable | Default | Purpose |
|---|---|---|
| `XHS_BACKEND_HOST` | `0.0.0.0` | uvicorn bind |
| `XHS_BACKEND_PORT` | `8000` | uvicorn port |
| `INITIAL_ADMIN_PASSWORD` | `Admin@123` | seed admin password (production must override) |
| `OPENCLI_BROWSER_COMMAND_TIMEOUT` | `120` | seconds |
| `CELERY_BROKER_URL` | `filesystem:///abs/path/to/celery_broker` | phase one uses filesystem broker; stage two switches to Redis |
| `CELERY_RESULT_BACKEND` | `filesystem:///abs/path/to/celery_results` | phase one |

### 3.3 Start

In **three** terminals:

```bash
# terminal 1 — API
cd backend && source .venv/bin/activate
uvicorn app.main:app --host 0.0.0.0 --port 8000

# terminal 2 — celery worker
cd backend && source .venv/bin/activate
celery -A app.tasks.crawl_task worker --loglevel=info --concurrency=1

# terminal 3 — celery beat (for scheduled jobs)
cd backend && source .venv/bin/activate
celery -A app.tasks.crawl_task beat --loglevel=info
```

## 4. Frontend (Vue 3 + Vite)

```bash
cd frontend
npm ci
npm run dev          # http://localhost:5173 (dev with HMR)
# OR for production build:
npm run build
npm run preview      # http://localhost:4173
```

The frontend `.env` or its `vite.config.ts` must point at the backend URL. The default is `http://localhost:8000`.

## 5. First Use

1. Open `http://localhost:5173` (dev) or `http://localhost:4173` (preview).
2. Log in with username `admin` and password `Admin@123` (or whatever you set).
3. Configuration Center → add a city, keywords, bloggers.
4. Dashboard → start a crawl. Make sure Chrome is logged in to xhs.

## 6. Tests (optional, recommended before opening PRs)

```bash
# backend
cd backend && source .venv/bin/activate
pytest -q

# frontend
cd frontend
npm run test -- --run
npm run build
```

## 7. Troubleshooting

| Symptom | Fix |
|---|---|
| `ModuleNotFoundError: app.xxx` | make sure you are in `backend/` and the venv is active |
| Celery task never runs | check broker dir is writable; check `celery beat` is also running |
| OpenCLI error `Missing url` | some bloggers need their `profile_url` filled; "补充博主信息" on Settings |
| Frontend can't reach backend | verify CORS / `VITE_API_BASE` / proxy config |

## 8. Where Next

- `docs/TODO.md` — open issues
- `AGENTS.md` — AI agent flow
- `docs/superpowers/specs/` — design specs
- `tests/*.md` — E2E specs
