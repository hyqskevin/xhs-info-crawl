# Note Edit and Single Review Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Allow operators to edit a note and approve or reject one note from either the list or detail view while preserving batch approval.

**Architecture:** Extend the existing note aggregate API with a strict update request and a dedicated review transition endpoint. Keep `ActivitiesView.vue` as the orchestration surface, adding one note-edit dialog and shared single-review action used by list and drawer buttons. Existing report queries remain unchanged because they already read current `Note` fields.

**Tech Stack:** FastAPI, Pydantic 2, SQLAlchemy 2, pytest, Vue 3, Element Plus, TypeScript, Vitest, Playwright.

## Global Constraints

- `source_url` remains read-only and is never included in the update payload.
- Editable fields are exactly `title`, `content`, `city_code`, and `published_at`.
- Single-review status is limited to `APPROVED` and `REJECTED`.
- Existing `POST /api/v1/notes/batch/approve` behavior must remain compatible.
- No database migration or historical report rewrite is part of this change.

---

### Task 1: Backend note update and single-review API

**Files:**
- Modify: `backend/tests/test_notes_api.py`
- Modify: `backend/app/api/v1/notes.py`

**Interfaces:**
- Consumes: `Note`, `City`, `_visible_note(db, note_id)` and the existing `_summary()` serializer.
- Produces: `PUT /api/v1/notes/{note_id}` and `POST /api/v1/notes/{note_id}/review`.

- [ ] **Step 1: Write failing API tests**

Add tests that create an enabled `City`, update all editable note fields, send an extra `source_url`, and assert the database/list/detail use the edited values while the original source URL remains. Add validation tests for whitespace-only title and disabled/unknown city. Add parameterized approve/reject tests plus an invalid status test.

- [ ] **Step 2: Run tests to verify RED**

Run: `cd backend && pytest -q tests/test_notes_api.py`

Expected: update/review requests fail with 405 or 422 because the endpoints and request models do not exist.

- [ ] **Step 3: Implement minimal API behavior**

In `notes.py`, import `Literal`, Pydantic `field_validator`, and `City`. Add:

```python
class NoteUpdate(BaseModel):
    title: str = Field(max_length=512)
    content: str
    city_code: str = Field(min_length=1, max_length=32)
    published_at: datetime | None

    @field_validator("title")
    @classmethod
    def validate_title(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("标题不能为空")
        return value


class NoteReviewRequest(BaseModel):
    status: Literal["APPROVED", "REJECTED"]
```

Add an update endpoint that verifies `City.code == payload.city_code` and `City.enabled.is_(True)`, assigns only model fields, commits, refreshes, and returns the full note detail through a shared detail serializer. Add a review endpoint that sets `review_status`, commits, and returns `{id, review_status}`.

- [ ] **Step 4: Run tests to verify GREEN**

Run: `cd backend && pytest -q tests/test_notes_api.py tests/test_note_weekly_reports.py`

Expected: all selected tests pass.

---

### Task 2: Frontend API client and note-management component

**Files:**
- Modify: `frontend/src/api/client.ts`
- Modify: `frontend/src/views/ActivitiesView.spec.ts`
- Modify: `frontend/src/views/ActivitiesView.vue`

**Interfaces:**
- Consumes: backend `PUT /notes/{id}` and `POST /notes/{id}/review`.
- Produces: `api.updateNote(id, data)` and `api.reviewNote(id, status)`; list/detail edit and review controls.

- [ ] **Step 1: Write failing component tests**

Extend the hoisted API mock with `updateNote` and `reviewNote`. Add tests that:

- find list-level “编辑/通过/驳回” actions;
- open edit, verify the source link control is disabled/read-only, fill title/content/city/published time, save, and assert `updateNote` receives only editable fields;
- confirm approve/reject before calling `reviewNote`;
- open detail and use the same edit/review actions, asserting detail and list refresh;
- verify target-state actions are hidden;
- simulate API rejection and assert an error Toast while state is not optimistically changed.

- [ ] **Step 2: Run component tests to verify RED**

Run: `cd frontend && npm run test -- --run src/views/ActivitiesView.spec.ts`

Expected: tests fail because note edit/review methods and controls do not exist.

- [ ] **Step 3: Add API client methods**

Add to the `notes` section:

```ts
updateNote: (id: number, data: object) => http.put(`/notes/${id}`, data),
reviewNote: (id: number, status: 'APPROVED' | 'REJECTED') => http.post(`/notes/${id}/review`, { status }),
```

- [ ] **Step 4: Implement shared edit and review actions**

In `ActivitiesView.vue`:

- maintain `noteEditDialog`, `noteSaving`, `noteForm`, and whether edit was opened from detail;
- populate the form from the row or fetched detail while preserving `source_url` only for display;
- submit `{title, content, city_code, published_at}` and exclude `source_url`;
- share `reviewNote(note, target, fromDetail)` between list and drawer buttons;
- wrap review in `ElMessageBox.confirm`, show success/error Toast, refresh list, and refresh detail when required;
- add required-field validation, a datetime picker, city selector, and disabled original-link input;
- widen the operation column enough to keep actions on one line.

- [ ] **Step 5: Run component tests to verify GREEN**

Run: `cd frontend && npm run test -- --run src/views/ActivitiesView.spec.ts`

Expected: all `ActivitiesView` tests pass.

---

### Task 3: Browser flow and API contract documentation

**Files:**
- Modify: `frontend/e2e/documented-flows.spec.ts`
- Create: `tests/test-note-edit-single-review.md`
- Modify: `docs/api-doc.md`

**Interfaces:**
- Consumes: the completed UI and endpoints from Tasks 1-2.
- Produces: executable browser coverage and human-readable acceptance cases/API contract.

- [ ] **Step 1: Write failing E2E cases**

Add mocked-browser cases under the activity-management suite for list edit, detail approve, list reject, and cancellation without a review request. Assert the edit request does not contain `source_url` and the UI displays success feedback.

- [ ] **Step 2: Run focused E2E to verify RED or expose missing selectors**

Run: `cd frontend && npx playwright test e2e/documented-flows.spec.ts --grep "编辑推文|单篇推文|取消单篇审核"`

Expected before UI completion: missing controls/selectors; after Task 2, use this run to validate the browser contract and adjust only accessibility/selectors if needed.

- [ ] **Step 3: Document the endpoint and acceptance cases**

Document request/response/error behavior for the update and review endpoints in `docs/api-doc.md`. Add `tests/test-note-edit-single-review.md` with backend, component, E2E and report-consistency checks matching the spec.

- [ ] **Step 4: Run focused E2E to verify GREEN**

Run: `cd frontend && npx playwright test e2e/documented-flows.spec.ts --grep "编辑推文|单篇推文|取消单篇审核"`

Expected: all new cases pass.

---

### Task 4: Full verification, TODO closure, and commit

**Files:**
- Modify: `docs/TODO.md`

**Interfaces:**
- Consumes: all completed behavior and fresh verification evidence.
- Produces: closed TODO entry and one implementation commit associated with this TODO.

- [ ] **Step 1: Run full verification**

Run:

```bash
cd backend && pytest -q
cd ../frontend && npm run test -- --run
npm run build
npx playwright test
cd .. && git diff --check
```

Expected: every command exits 0; no backend, component, build, E2E or whitespace failures.

- [ ] **Step 2: Move the TODO to completed**

Move “补全推文编辑与单条审核闭环” from “当前待办” to “已完成”, retain its goal and acceptance text, and add result, verification counts, spec and test-document links.

- [ ] **Step 3: Commit the implementation**

Stage only files belonging to this TODO and commit:

```bash
git commit -m "feat: complete note edit and single review"
```
