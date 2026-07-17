# 登录续跑与活动日期窗口实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为暂停抓取任务提供可操作的 Chrome 登录续跑闭环，并保证 SQLite、Markdown、Excel 只保存抓取参考日起未来 60 天内的已知日期活动。

**Architecture:** 日期规则集中在独立的 `activity_window` 服务，MiniMax 负责提示、后端负责最终判定；抓取任务只消费判定结果并维护活动级跳过进度。登录页由本地浏览器启动服务打开，现有 restart 接口对 `PAUSED` 执行 OpenCLI 登录预检后复用原任务续跑。

**Tech Stack:** Python 3.12、FastAPI、SQLAlchemy、Alembic、Celery、SQLite、Vue 3、TypeScript、Element Plus、Vitest、Playwright。

## Global Constraints

- 活动窗口固定为抓取任务第一次开始日（Asia/Shanghai）至未来第 60 天，两端包含。
- 明确位于窗口之外的活动不入库；日期未知的活动保留为 `NEEDS_REVIEW` 且 `start_time=null`。
- 小红书“不限、一天内、一周内、半年内”仍只约束笔记发布时间。
- 登录恢复复用原任务 ID、参数、`started_at` 和全部已有进度。
- 前端只使用 Element Plus 组件和图标，不使用 emoji，不自行实现 UI 控件。
- 新配置全部写入 `.env` 和 `.env.example` 并附中文分类注释。
- 单条活动或单条笔记失败不得中断整批任务。
- 不引入 Redis、MinIO、Docker 或第二阶段组件。

---

### Task 1: 活动日期归一化与 60 天窗口服务

**Files:**
- Create: `backend/app/services/activity_window.py`
- Modify: `backend/app/services/extraction.py`
- Modify: `backend/app/services/minimax.py`
- Modify: `backend/app/core/config.py`
- Modify: `.env`
- Modify: `.env.example`
- Test: `backend/tests/test_activity_window.py`
- Test: `backend/tests/test_multi_activity_archive.py`

**Interfaces:**
- Produces: `ActivityWindow(reference: datetime, days: int, timezone_name: str)`。
- Produces: `ActivityWindow.classify(start_time: str | None, end_time: str | None) -> Literal['valid','unknown','past','future']`。
- Produces: `normalize_activity_datetime(value: Any, reference: datetime, future_window_days: int = 60) -> str | None`。
- Consumes: `Settings.activity_future_window_days: int` 和 `Settings.celery_timezone: str`。

- [ ] **Step 1: 写失败测试覆盖窗口边界和无年份跨年**

```python
def test_window_includes_today_and_day_60_but_rejects_day_61():
    window = ActivityWindow(datetime(2026, 7, 17, tzinfo=timezone.utc), 60, "Asia/Shanghai")
    assert window.classify("2026-07-17T00:00:00", None) == "valid"
    assert window.classify("2026-09-15T23:59:59", None) == "valid"
    assert window.classify("2026-09-16T00:00:00", None) == "future"

def test_yearless_date_uses_next_year_only_when_inside_window():
    reference = datetime(2026, 12, 20)
    assert normalize_activity_datetime("1月5日", reference, 60).startswith("2027-01-05")
    assert normalize_activity_datetime("7月1日", reference, 60) is None
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd backend && ../.venv/bin/pytest tests/test_activity_window.py -q`

Expected: FAIL，`ModuleNotFoundError: app.services.activity_window`。

- [ ] **Step 3: 实现独立窗口服务和归一化签名**

```python
class ActivityWindow:
    def __init__(self, reference: datetime, days: int, timezone_name: str): ...
    def classify(self, start_time: str | None, end_time: str | None) -> str:
        if not start_time:
            return "unknown"
        start = datetime.fromisoformat(start_time)
        end = datetime.fromisoformat(end_time) if end_time else start
        if end < self.start:
            return "past"
        if start > self.end:
            return "future"
        return "valid"
```

`normalize_activity_row` 接收同一参考时间与天数；MiniMax prompt 明确包含参考日期、`Asia/Shanghai` 与 60 天上限，但窗口服务仍为最终校验。

- [ ] **Step 4: 增加并注释配置**

```dotenv
# ==================== 活动日期校验 ====================
# ACTIVITY_FUTURE_WINDOW_DAYS：从任务首次开始日算起，最多保留未来多少天的活动。
ACTIVITY_FUTURE_WINDOW_DAYS=60
```

- [ ] **Step 5: 运行日期与提取测试**

Run: `cd backend && ../.venv/bin/pytest tests/test_activity_window.py tests/test_multi_activity_archive.py tests/test_minimax.py -q`

Expected: PASS。

- [ ] **Step 6: 提交**

```bash
git add .env.example backend/app/core/config.py backend/app/services/activity_window.py backend/app/services/extraction.py backend/app/services/minimax.py backend/tests/test_activity_window.py backend/tests/test_multi_activity_archive.py backend/tests/test_minimax.py
git commit -m "feat: validate activity date window"
```

### Task 2: 可空活动时间和活动级跳过进度

**Files:**
- Create: `backend/migrations/versions/0006_activity_window.py`
- Modify: `backend/app/models/activity.py`
- Modify: `backend/app/models/task.py`
- Modify: `backend/app/schemas/activity.py`
- Modify: `backend/app/api/v1/activities.py`
- Modify: `backend/app/api/v1/dashboard.py`
- Modify: `backend/app/services/report.py`
- Modify: `backend/app/services/archive.py`
- Modify: `backend/app/tasks/crawl_task.py`
- Test: `backend/tests/test_crawl_task_resilience.py`
- Test: `backend/tests/test_activities_api.py`
- Test: `backend/tests/test_reports.py`

**Interfaces:**
- Consumes: `ActivityWindow.classify(...)`。
- Produces: `Activity.start_time: datetime | None`。
- Produces: `CrawlTask.skipped_activities: int`。
- Produces: `filter_activity_rows(rows, window) -> tuple[list[dict], list[tuple[dict,str]]]`。

- [ ] **Step 1: 写失败测试证明越界活动被隔离**

```python
def test_one_note_keeps_valid_and_unknown_but_skips_past_and_future(...):
    extracted = [valid_row, past_row, future_row, unknown_row]
    process_note(...)
    assert activity_names(db) == ["有效活动", "日期待确认"]
    assert task.skipped_activities == 2
    assert unknown_activity.start_time is None
    assert unknown_activity.status == "NEEDS_REVIEW"
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd backend && ../.venv/bin/pytest tests/test_crawl_task_resilience.py -q`

Expected: FAIL，历史和远期活动仍被创建，未知时间仍回填当前时间。

- [ ] **Step 3: 增加迁移和模型字段**

```python
def upgrade():
    with op.batch_alter_table("activities") as batch:
        batch.alter_column("start_time", existing_type=sa.DateTime(), nullable=True)
    op.add_column("crawl_tasks", sa.Column("skipped_activities", sa.Integer(), nullable=False, server_default="0"))
```

- [ ] **Step 4: 在抓取任务中按原始 started_at 判定**

```python
if task.started_at is None:
    task.started_at = datetime.now(timezone.utc)
window = ActivityWindow(task.started_at, settings.activity_future_window_days, settings.celery_timezone)
for fields in extracted:
    reason = window.classify(fields.get("start_time"), fields.get("end_time"))
    if reason in {"past", "future"}:
        task.skipped_activities += 1
        log(...)
        continue
    Activity(start_time=parse_or_none(fields.get("start_time")), ...)
```

- [ ] **Step 5: 让 API、排序、归档和周报支持空日期**

活动列表使用 `nullslast(Activity.start_time.asc())`；Markdown 显示“待确认”；Excel 输出空单元格；周报查询排除 `start_time IS NULL` 和 `status='NEEDS_REVIEW'`。

- [ ] **Step 6: 运行迁移及相关测试**

Run: `cd backend && ../.venv/bin/alembic upgrade head`

Expected: 当前数据库升级至 `0006`。

Run: `cd backend && ../.venv/bin/pytest tests/test_crawl_task_resilience.py tests/test_activities_api.py tests/test_reports.py -q`

Expected: PASS。

- [ ] **Step 7: 提交**

```bash
git add backend/migrations/versions/0006_activity_window.py backend/app/models backend/app/schemas/activity.py backend/app/api/v1/activities.py backend/app/api/v1/dashboard.py backend/app/services/report.py backend/app/services/archive.py backend/app/tasks/crawl_task.py backend/tests
git commit -m "feat: isolate out-of-window activities"
```

### Task 3: 历史脏数据清理与归档重建

**Files:**
- Create: `backend/app/services/activity_cleanup.py`
- Create: `backend/scripts/cleanup_activity_dates.py`
- Modify: `backend/app/services/archive.py`
- Test: `backend/tests/test_activity_cleanup.py`

**Interfaces:**
- Produces: `cleanup_activity_dates(db: Session, settings: Settings, reference: datetime) -> CleanupSummary`。
- Produces: `rebuild_task_activity_exports(db, settings, task_id: int) -> None`。
- `CleanupSummary` 包含 `scanned`, `deleted`, `retained`, `task_ids`。

- [ ] **Step 1: 写失败测试覆盖删除关联候选和保留证据**

```python
def test_cleanup_removes_out_of_window_activities_and_rebuilds_exports(...):
    summary = cleanup_activity_dates(db, settings, datetime(2026, 7, 17, tzinfo=timezone.utc))
    assert summary.deleted == 2
    assert db.get(Note, note.id) is not None
    assert db.scalar(select(func.count()).select_from(NoteImage)) == 1
    assert db.scalar(select(func.count()).select_from(DuplicateCandidate)) == 0
    assert "历史活动" not in activities_md.read_text()
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd backend && ../.venv/bin/pytest tests/test_activity_cleanup.py -q`

Expected: FAIL，清理服务不存在。

- [ ] **Step 3: 实现幂等清理和导出重建**

清理顺序固定为：扫描爬虫活动 → 分类 → 删除涉及目标活动的 `DuplicateCandidate` → 删除活动 → 提交 → 按任务重建 `activities.md/xlsx`。`source.md`、图片和 Note 不修改。

- [ ] **Step 4: 运行测试两次验证幂等**

Run: `cd backend && ../.venv/bin/pytest tests/test_activity_cleanup.py -q`

Expected: PASS，第二次调用 `deleted == 0`。

- [ ] **Step 5: 提交**

```bash
git add backend/app/services/activity_cleanup.py backend/app/services/archive.py backend/scripts/cleanup_activity_dates.py backend/tests/test_activity_cleanup.py
git commit -m "feat: clean expired activity records"
```

### Task 4: Chrome 登录页启动和 PAUSED 任务续跑

**Files:**
- Create: `backend/app/services/browser_launcher.py`
- Modify: `backend/app/core/config.py`
- Modify: `backend/app/api/v1/settings.py`
- Modify: `backend/app/api/v1/tasks.py`
- Modify: `.env`
- Modify: `.env.example`
- Test: `backend/tests/test_browser_launcher.py`
- Test: `backend/tests/test_config_task_duplicate_api.py`

**Interfaces:**
- Produces: `open_xhs_login(settings: Settings) -> str`，返回登录 URL，失败抛 `BrowserLaunchError`。
- Produces: `POST /api/v1/settings/opencli/open-login`。
- 扩展: `POST /api/v1/tasks/{id}/restart` 接受 `PAUSED` 并进行 `OpenCLIAdapter.check_login()`。

- [ ] **Step 1: 写失败测试**

```python
def test_paused_task_stays_paused_when_login_check_fails(...):
    monkeypatch.setattr(OpenCLIAdapter, "check_login", raise_auth_required)
    response = client.post(f"/api/v1/tasks/{task.id}/restart", headers=headers)
    assert response.status_code == 409
    assert db.get(CrawlTask, task.id).status == "PAUSED"

def test_paused_task_reuses_id_and_progress_after_login(...):
    response = client.post(f"/api/v1/tasks/{task.id}/restart", headers=headers)
    assert response.status_code == 202
    assert response.json()["data"]["id"] == task.id
    assert response.json()["data"]["downloaded_notes"] == 19
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd backend && ../.venv/bin/pytest tests/test_browser_launcher.py tests/test_config_task_duplicate_api.py -q`

Expected: FAIL，接口不存在且 PAUSED 不允许 restart。

- [ ] **Step 3: 实现平台浏览器启动服务和配置**

```dotenv
# ==================== 小红书登录页 ====================
XHS_LOGIN_URL=https://www.xiaohongshu.com/explore
XHS_LOGIN_BROWSER=Google Chrome
```

平台命令只接收经过配置验证的浏览器名称和固定 URL，不使用 shell；macOS 使用 `open -a`，Windows 使用 `startfile`，Linux 使用 Chrome 可执行文件或 `xdg-open` 回退。

- [ ] **Step 4: 扩展 restart 登录预检**

仅 `task.status == 'PAUSED'` 时调用 `check_login()`；捕获 `AuthenticationRequired` 后返回 `HTTPException(409, 'AUTH_REQUIRED')`，不修改任务。成功时沿用现有入队逻辑，且不清零任何进度。

- [ ] **Step 5: 运行后端测试**

Run: `cd backend && ../.venv/bin/pytest tests/test_browser_launcher.py tests/test_config_task_duplicate_api.py tests/test_crawl_task_resilience.py -q`

Expected: PASS。

- [ ] **Step 6: 提交**

```bash
git add .env.example backend/app/core/config.py backend/app/services/browser_launcher.py backend/app/api/v1/settings.py backend/app/api/v1/tasks.py backend/tests/test_browser_launcher.py backend/tests/test_config_task_duplicate_api.py
git commit -m "feat: resume paused crawl after login"
```

### Task 5: 仪表盘恢复按钮与空日期 UI

**Files:**
- Modify: `frontend/src/api/client.ts`
- Modify: `frontend/src/views/DashboardView.vue`
- Modify: `frontend/src/views/ActivitiesView.vue`
- Modify: `frontend/src/views/DashboardView.spec.ts`
- Modify: `frontend/src/views/ActivitiesView.spec.ts`

**Interfaces:**
- Produces: `api.openXhsLogin()`。
- Consumes: `api.restartTask(taskId)` 对 PAUSED 的新语义。

- [ ] **Step 1: 写失败组件测试**

```ts
it('opens login and resumes a paused task with independent loading states', async () => {
  lastTask.status = 'PAUSED'
  expect(wrapper.text()).toContain('打开小红书登录')
  expect(wrapper.text()).toContain('检测登录并继续')
  await findButton('打开小红书登录').trigger('click')
  expect(mocks.openXhsLogin).toHaveBeenCalled()
  await findButton('检测登录并继续').trigger('click')
  expect(mocks.restartTask).toHaveBeenCalledWith(4)
})
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd frontend && npm test -- --run src/views/DashboardView.spec.ts src/views/ActivitiesView.spec.ts`

Expected: FAIL，恢复按钮与 API 不存在。

- [ ] **Step 3: 实现 Element Plus 交互**

增加独立 `openingLogin` 与 `restarting` 状态；PAUSED 显示 `Link` 图标的“打开小红书登录”和 `RefreshRight` 图标的“检测登录并继续”。成功/失败均用 `ElMessage`。活动时间空值显示“待确认”，编辑保存时允许 `start_time: null`。

- [ ] **Step 4: 运行组件测试与构建**

Run: `cd frontend && npm test -- --run src/views/DashboardView.spec.ts src/views/ActivitiesView.spec.ts && npm run build`

Expected: 测试 PASS，构建成功。

- [ ] **Step 5: 提交**

```bash
git add frontend/src/api/client.ts frontend/src/views/DashboardView.vue frontend/src/views/ActivitiesView.vue frontend/src/views/DashboardView.spec.ts frontend/src/views/ActivitiesView.spec.ts
git commit -m "feat: add paused task login controls"
```

### Task 6: 规格、测试案例与浏览器 E2E 同步

**Files:**
- Modify: `docs/business-flow.md`
- Modify: `docs/crawler-design.md`
- Modify: `docs/database-design.md`
- Modify: `docs/api-doc.md`
- Modify: `docs/ui-design.md`
- Modify: `tests/test-crawler-engine.md`
- Modify: `tests/test-task-scheduling.md`
- Modify: `tests/test-extraction-pipeline.md`
- Modify: `tests/test-frontend-ui-e2e.md`
- Modify: `frontend/e2e/app.spec.ts`

**Interfaces:**
- Documents: 60 天窗口、空日期待审核、清理命令、打开登录接口、PAUSED restart 语义。

- [ ] **Step 1: 增加 E2E 失败案例**

新增 PAUSED 卡片按钮、打开登录 Toast、登录失败 Toast、登录成功刷新、空日期“待确认”五个浏览器场景；网络请求使用 route stub，不真实打开外部网站。

- [ ] **Step 2: 运行 E2E 确认新案例在实现前失败、实现后通过**

Run: `cd frontend && npm run test:e2e`

Expected: 全部 PASS。

- [ ] **Step 3: 同步设计与测试 Markdown**

每份测试文档同时列出组件测试和浏览器功能测试映射，不保留“仅 FAILED 可重启”等旧描述。

- [ ] **Step 4: 提交**

```bash
git add docs tests frontend/e2e/app.spec.ts
git commit -m "docs: cover login resume and activity window"
```

### Task 7: 执行清理、全量验证和真实登录恢复检查

**Files:**
- Runtime data: `data/app.db`
- Runtime exports: `data/archive/<date>/task-*/activities.md`
- Runtime exports: `data/archive/<date>/task-*/activities.xlsx`

**Interfaces:**
- Consumes: `backend/scripts/cleanup_activity_dates.py`。

- [ ] **Step 1: 备份 SQLite 后执行迁移和清理**

Run: `cp data/app.db data/app.db.before-activity-window && cd backend && ../.venv/bin/alembic upgrade head && ../.venv/bin/python scripts/cleanup_activity_dates.py`

Expected: 输出扫描、删除、保留和受影响任务 ID；数据库中不存在已知日期的窗口外爬虫活动。

- [ ] **Step 2: 运行后端全量测试**

Run: `cd backend && ../.venv/bin/pytest -q`

Expected: 全部 PASS，仅保留项目既有显式 skip。

- [ ] **Step 3: 运行前端全量测试、构建和 E2E**

Run: `cd frontend && npm test -- --run && npm run build && npm run test:e2e`

Expected: 全部 PASS，构建成功。

- [ ] **Step 4: 重启本地 API、Celery 和前端服务**

使用项目既有本地启动命令，确认 8000、5173 和 worker 均加载新代码。

- [ ] **Step 5: 真实检查暂停任务恢复**

在仪表盘点击“打开小红书登录”，用户登录后点击“检测登录并继续”。确认任务 #4 从 `PAUSED` 进入 `PENDING/RUNNING`，原下载/OCR/提取进度不减少。

- [ ] **Step 6: 最终数据核对**

Run: `sqlite3 data/app.db "SELECT MIN(start_time), MAX(start_time), COUNT(*) FROM activities WHERE note_id IS NOT NULL AND start_time IS NOT NULL AND status != 'DELETED';"`

Expected: 最小和最大已知活动时间均位于当前 60 天有效窗口内；Markdown 与 Excel 行数和 SQLite 有效活动数一致。

- [ ] **Step 7: 提交运行结果文档（若仓库已有验证记录）**

将真实验证结果追加到 `tests/EXTERNAL_VALIDATION.md`，提交消息：

```bash
git add tests/EXTERNAL_VALIDATION.md
git commit -m "test: verify login resume and date cleanup"
```
