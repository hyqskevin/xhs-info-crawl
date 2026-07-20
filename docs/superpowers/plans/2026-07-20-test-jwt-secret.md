# Test JWT Secret Isolation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give pytest an isolated JWT HMAC secret of at least 32 bytes so backend tests emit no `InsecureKeyLengthWarning` without changing local or production configuration.

**Architecture:** Inject a fixed test-only `SECRET_KEY` in `backend/tests/conftest.py` before importing any application module, matching the existing import-time Celery broker isolation. Add focused regression tests for the loaded key length and PyJWT warning behavior, then document and close the TODO after the full backend suite passes.

**Tech Stack:** Python 3.11, pytest, pydantic-settings, PyJWT HS256.

## Global Constraints

- The pytest JWT key must be at least 32 bytes when UTF-8 encoded.
- Tests must not read, print, copy, or expose the root `.env` secret.
- Do not modify `backend/app/core/config.py`, `backend/app/core/security.py`, `.env`, or `.env.example`.
- Do not suppress `InsecureKeyLengthWarning` with pytest warning filters.
- Local API, Celery worker, and production configuration loading must remain unchanged.

---

### Task 1: Isolate the pytest JWT signing secret

**Files:**
- Create: `backend/tests/test_test_jwt_secret.py`
- Modify: `backend/tests/conftest.py:10-16`
- Create: `tests/test-test-jwt-secret.md`
- Modify: `docs/superpowers/specs/2026-07-20-test-jwt-secret-design.md:3`
- Modify: `docs/TODO.md:15-18`

**Interfaces:**
- Consumes: `app.core.config.get_settings() -> Settings` and `app.core.security.create_access_token(data: dict[str, object], expires_delta: timedelta | None = None) -> str`.
- Produces: a pytest-only `SECRET_KEY` environment value established before `app` imports; no production interface changes.

- [x] **Step 1: Write the failing regression tests**

Create `backend/tests/test_test_jwt_secret.py`:

```python
import warnings

from jwt.warnings import InsecureKeyLengthWarning

from app.core.config import get_settings
from app.core.security import create_access_token


def test_pytest_uses_jwt_secret_of_at_least_32_bytes() -> None:
    assert len(get_settings().secret_key.encode("utf-8")) >= 32


def test_access_token_creation_has_no_short_key_warning() -> None:
    with warnings.catch_warnings():
        warnings.simplefilter("error", InsecureKeyLengthWarning)
        token = create_access_token({"sub": "test-user", "role": "admin"})

    assert token
```

- [x] **Step 2: Run the focused tests and verify the red state**

Run:

```bash
cd backend && .venv/bin/pytest -q tests/test_test_jwt_secret.py
```

Expected: exit code is non-zero. The first test reports that the loaded secret is only 22 bytes, and the second raises `InsecureKeyLengthWarning` as an error.

- [x] **Step 3: Inject the isolated secret before application imports**

Update the environment setup block in `backend/tests/conftest.py`:

```python
# Settings and Celery read environment values while app modules are imported.
# Keep pytest isolated from the developer's JWT secret and filesystem broker.
os.environ["SECRET_KEY"] = "pytest-only-jwt-secret-at-least-32-bytes"
os.environ["CELERY_BROKER_URL"] = "memory://"

from app.core.database import Base, get_db
from app.main import app
```

The assignment must remain above all imports from `app` so the cached `Settings` instance receives the test-only value.

- [x] **Step 4: Run the focused tests and verify the green state**

Run:

```bash
cd backend && .venv/bin/pytest -q tests/test_test_jwt_secret.py
```

Expected: `2 passed`; output contains no `InsecureKeyLengthWarning`.

- [x] **Step 5: Add the test case document and update tracking**

Create `tests/test-test-jwt-secret.md` with these cases:

```markdown
# 测试环境 JWT 密钥隔离测试案例

## 目标

确认 pytest 使用独立的强度合格 JWT 密钥，不读取本地真实密钥，且不再产生 PyJWT 短密钥安全警告。

## 自动化案例

1. 运行 `cd backend && .venv/bin/pytest -q tests/test_test_jwt_secret.py`。
2. 预期 2 个测试通过。
3. 预期测试环境密钥按 UTF-8 计不少于 32 字节。
4. 预期 JWT 签发过程不产生 `InsecureKeyLengthWarning`。

## 全量回归

1. 运行 `cd backend && .venv/bin/pytest -q`。
2. 预期全部测试通过，输出不包含 `InsecureKeyLengthWarning`。
3. 检查 Git 变更，预期 `.env` 未被修改或纳入版本控制。
```

Then update the design status to `已审核并实现`, move the JWT TODO into `docs/TODO.md` 的“已完成”章节, and record the focused and full-suite results without writing the secret value.

- [x] **Step 6: Run full verification**

Run:

```bash
cd backend && .venv/bin/pytest -q
```

Expected: exit code 0 and output contains no `InsecureKeyLengthWarning`.

Run:

```bash
git diff --check
git status --short
```

Expected: `git diff --check` exits 0; only the six files listed in this task and this implementation plan are changed; neither `.env` nor application runtime files appear.

- [x] **Step 7: Commit the completed TODO**

```bash
git add backend/tests/conftest.py backend/tests/test_test_jwt_secret.py tests/test-test-jwt-secret.md docs/TODO.md docs/superpowers/specs/2026-07-20-test-jwt-secret-design.md
git commit -m "test: isolate JWT signing secret"
```
