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

- [x] Convert TC-AUTH-001 through TC-AUTH-009 into pytest tests; mark optional refresh TC-AUTH-010 skipped.
- [x] Verify RED, then implement users, JWT, password hashing, dependencies, and login API.
- [x] Verify authentication tests and commit.

### Task 2: Activity CRUD API

- [x] Convert TC-ACT-001 through TC-ACT-010 into real SQLite API tests.
- [x] Verify RED, then implement activity model, schemas, filters, state validation, and CRUD routes.
- [x] Verify activity tests and commit.

### Task 3: Markdown and Excel reports

- [x] Convert TC-REPORT-001 through TC-REPORT-009 into service/API tests.
- [x] Verify RED, then implement report persistence, Markdown/XLSX generation, regeneration, and downloads.
- [x] Verify report tests and commit.

### Task 4: Scheduling and deduplication

- [x] Convert phase-one task scheduling and deduplication boundaries into executable service/API tests.
- [x] Implement task records, locking, state transitions, retries, similarity scoring, merge, and ignore behavior.
- [x] Verify and commit.

### Task 5: Extraction, OCR, and crawler adapters

- [x] Convert phase-one extraction, OCR, and crawler specifications into executable deterministic boundary tests.
- [x] Implement rules-first extraction, MiniMax fallback interface, PaddleOCR adapter, and OpenCLI adapter with typed errors and rate limits.
- [x] Verify and commit.

### Task 6: Vue workflows and Playwright E2E

- [x] Implement login, activity CRUD, task, review, report, and settings pages using Element Plus.
- [x] Add Playwright scenarios for login, activities, task submission, duplicate review, reports, and settings.
- [x] Run all backend, frontend, build, and browser suites; produce a case coverage matrix.
