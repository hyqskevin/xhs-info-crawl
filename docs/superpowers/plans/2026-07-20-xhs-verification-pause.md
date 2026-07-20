# XHS Verification Pause Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Pause safely on explicit XHS verification signals, keep the verification page open, and reuse the existing manual resume flow.

**Architecture:** Add a verification-specific authentication exception and centralized message classifier. Let OpenCLIAdapter preserve its crawler tab only for this exception, while run_crawl records PAUSED and best-effort launches Chrome.

**Tech Stack:** Python, Celery, OpenCLI, FastAPI, Vue 3, Element Plus, pytest, Vitest, Playwright.

### Task 1: Verification classifier

**Files:** `backend/app/services/crawler.py`, `backend/app/services/opencli_adapter.py`, relevant tests.

- [ ] Write red tests for explicit verification phrases and false-positive exclusions.
- [ ] Add `VerificationRequired` and centralized classifier.
- [ ] Classify command output before generic timeout/error mapping.

### Task 2: Preserve verification page and pause task

**Files:** `backend/app/services/opencli_adapter.py`, `backend/app/tasks/crawl_task.py`, backend tests.

- [ ] Write red tests that verification skips close while ordinary failure/stop still closes.
- [ ] Preserve only verification sessions.
- [ ] Write red task test for PAUSED plus best-effort browser launch warning.
- [ ] Implement task pause and automatic Chrome launch without masking PAUSED.

### Task 3: UI/E2E/docs

**Files:** Dashboard tests/E2E, crawler/API/UI docs, `tests/test-xhs-verification-pause.md`, `docs/TODO.md`.

- [ ] Verify PAUSED verification copy and existing two buttons.
- [ ] Add browser flow for open-login and resume after verification.
- [ ] Run full backend, frontend, build, E2E and formatting checks.
- [ ] Record evidence, close the consolidated TODO and commit.
