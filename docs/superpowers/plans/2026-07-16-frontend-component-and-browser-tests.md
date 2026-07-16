# Frontend Component and Browser Tests Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give every front-end page a meaningful component test and a browser feature test, with module tests for layout, routing, and HTTP authentication.

**Architecture:** Vitest mounts Vue components with Element Plus and mocks only API boundaries. Playwright remains the browser-level contract and runs the documented workflows in Google Chrome.

**Tech Stack:** Vue 3, Element Plus, Vitest, Vue Test Utils, jsdom, Playwright, Google Chrome.

## Global Constraints

- Every route page has both component and browser coverage.
- UI continues to use Element Plus and official icons without Emoji.
- Tests run from the root through the existing npm commands.

### Task 1: Shared component test runtime

- [x] Add jsdom polyfills for Element Plus component tests.
- [x] Configure Vitest to load the shared setup.
- [x] Run the existing dashboard test.

### Task 2: Page component tests

- [x] Add LoginView and ActivitiesView component tests.
- [x] Add TasksView and DuplicatesView component tests.
- [x] Add ReportsView and SettingsView component tests.
- [x] Run all component tests and fix only test-environment compatibility issues.

### Task 3: Common module tests

- [x] Add App and AppLayout component coverage.
- [x] Add router guard tests.
- [x] Add HTTP authorization header tests.
- [x] Run all component/module tests.

### Task 4: Browser and documentation verification

- [x] Run all Chrome browser tests.
- [x] Update the tests coverage matrix and execution status.
- [x] Run component tests, production build, and diff checks.
