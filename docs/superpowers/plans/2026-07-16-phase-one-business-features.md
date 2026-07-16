# Phase One Business Features Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Convert the 72 documented cases into executable automated tests and implement the phase-one business features in dependency order.

**Architecture:** FastAPI routes use SQLAlchemy repositories against SQLite and share JWT dependencies. Domain services isolate report, deduplication, extraction, OCR, and crawler boundaries so external systems can be replaced or mocked. Browser E2E is added after the API and Vue workflows exist.

**Tech Stack:** FastAPI, SQLAlchemy, SQLite, PyJWT, pwdlib, openpyxl, Celery, pytest, Vue 3, Element Plus, Vitest, Playwright.

## Global Constraints

- All runtime variables live in root `.env` and are documented in `.env.example`.
- UI uses Element Plus and `@element-plus/icons-vue`; no Emoji icons.
- Each documented test case becomes executable or is explicitly marked phase-two/optional with a skip reason.
- External OpenCLI, OCR, and MiniMax boundaries are mocked in deterministic automated tests.

### Task 1: Authentication and database models

- [ ] Convert TC-AUTH-001 through TC-AUTH-009 into pytest tests; mark optional refresh TC-AUTH-010 skipped.
- [ ] Verify RED, then implement users, JWT, password hashing, dependencies, and login API.
- [ ] Verify authentication tests and commit.

### Task 2: Activity CRUD API

- [ ] Convert TC-ACT-001 through TC-ACT-010 into real SQLite API tests.
- [ ] Verify RED, then implement activity model, schemas, filters, state validation, and CRUD routes.
- [ ] Verify activity tests and commit.

### Task 3: Markdown and Excel reports

- [ ] Convert TC-REPORT-001 through TC-REPORT-009 into service/API tests.
- [ ] Verify RED, then implement report persistence, Markdown/XLSX generation, regeneration, and downloads.
- [ ] Verify report tests and commit.

### Task 4: Scheduling and deduplication

- [ ] Convert task scheduling and deduplication specifications into executable tests.
- [ ] Implement task records, locking, state transitions, retries, similarity scoring, merge, and ignore behavior.
- [ ] Verify and commit.

### Task 5: Extraction, OCR, and crawler adapters

- [ ] Convert extraction, OCR, and crawler specifications into executable boundary tests.
- [ ] Implement rules-first extraction, MiniMax fallback interface, PaddleOCR adapter, and OpenCLI adapter with typed errors and rate limits.
- [ ] Verify and commit.

### Task 6: Vue workflows and Playwright E2E

- [ ] Implement login, activity CRUD, task, review, and report pages using Element Plus.
- [ ] Add Playwright scenarios for login, manual activity creation/editing, and Markdown/XLSX report generation/download.
- [ ] Run all backend, frontend, build, and browser suites; produce a case coverage matrix.
