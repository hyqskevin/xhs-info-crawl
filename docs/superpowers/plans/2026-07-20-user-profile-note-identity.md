# `user/profile` Note Identity Implementation Plan

**Goal:** Recognize blogger note URLs by stable note ID so repeated signed URLs reuse completed notes instead of violating the unique constraint.

**Architecture:** Extend the centralized URL identity extractor with one strict `user/profile/<user-id>/<note-id>` pattern. Let existing deduplication and `prepare_existing_note()` behavior consume that identity without adding a second dedup path or a database migration.

**Tech Stack:** Python 3.11, SQLAlchemy, pytest.

### Task 1: Specify the missing identity forms

**Files:**
- Modify: `backend/tests/test_note_identity.py`
- Modify: `backend/tests/test_crawl_task_resilience.py`

- [x] Add different-token `user/profile` URL identity assertions.
- [x] Add a pure profile URL negative assertion.
- [x] Add an existing processed-note assertion that refreshes the signed URL.
- [x] Run the focused tests and confirm RED for the missing path rule.

### Task 2: Add the minimal centralized rule

**Files:**
- Modify: `backend/app/services/note_identity.py`

- [x] Add a strict pattern capturing the second segment after `/user/profile/`.
- [x] Run note identity and crawl resilience tests GREEN.
- [x] Run execution ownership and auto-stop regressions.

### Task 3: Verify and close

**Files:**
- Modify: `tests/test-user-profile-note-identity.md`
- Modify: `docs/TODO.md`
- Modify: `docs/superpowers/specs/2026-07-20-user-profile-note-identity-design.md`

- [x] Run `make test`, `make test-e2e`, and `git diff --check`.
- [x] Record results and move the TODO to completed.
- [x] Commit implementation and acceptance evidence with the TODO association.
