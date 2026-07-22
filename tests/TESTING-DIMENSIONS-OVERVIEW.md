# 测试案例 10 维度全景

> 给 10 个测试维度都编号 / 索引。**每个 md 文件必须能在下面找到对应位置**。
> 关联：`tests/poster-test-cases.md`（海报专属 case 编号 TC-PT/T/PTK/PSH-XXX）

## 维度索引

| # | 维度 | 范围 | 已有 md 文件 |
|---|---|---|---|
| 1 | 接口（后端 API） | FastAPI 端点 + 入参校验 + 鉴权 | `test-cities-api.md` / `test-keyword-groups-api.md` / `test-settings-api.md` / `test-notes-api.md` / `test-duplicates-api.md` / `test-reports-api.md` / `test-tasks-api.md` / `test-auth-api.md` / `test-poster-api.md` |
| 2 | 数据库与迁移 | Alembic + 模型关系 + 一致性 | `test-database.md` / `test-celery-test-isolation.md` |
| 3 | 安全与鉴权 | JWT / cookie / 401 / 403 / Redis | `test-security.md` / `test-test-jwt-secret.md` |
| 4 | 任务调度与 Celery | Celery beat / 任务队列 / 隔离 | `test-task-scheduling.md` / `test-celery-test-isolation.md` |
| 5 | OCR / 图像识别 | NoteImage / PaddleOCR 状态 | `test-ocr.md` |
| 6 | 抓取执行 / 爬虫引擎 | 抓取 / 阶段 / 暂停 / 重启 | `test-crawler-engine.md` / `test-blogger-discovery-resilience.md` / `test-crawl-execution-safe-stop.md` / `test-stop-execution-fence-browser-cleanup.md` / `test-crawl-scope-config-driven.md` / `test-xhs-verification-pause.md` |
| 7 | 字段提取（LLM 管道） | MiniMax 提取 / WindowGuard | `test-extraction-pipeline.md` / `test-activity-window-guard.md`（如有）/ `test-note-zero-activity-and-window.md` / `test-parse-real-published-at.md` |
| 8 | 前端 UI（Vitest + Playwright） | 路由 / 表单 / 组件 | `test-frontend-ui-e2e.md` / `test-table-actions-nowrap.md` / `test-drawer-activities-dates.md` / `test-note-list-no-summary.md` / `test-note-edit-single-review.md` |
| 9 | E2E / 浏览器 | Playwright + opencli 浏览器自动化 | `test-frontend-ui-e2e.md`（含）/ `test-user-profile-note-identity.md` |
| 10 | 海报生成 / AI 视觉 | 模板 / 任务 / 渲染 / minimax vision | `test-poster-api.md` / `tests/poster-test-cases.md` / `tests/poster-generation.md` / `tests/scripts/test_poster_generation.sh` |

## 维度 → 用例编号 速查

| 维度 | 主要 case 文件 |
|---|---|
| 1 接口 | TC-CITIES / TC-KG / TC-SETTINGS / TC-NOTES / TC-DUP / TC-REPORTS / TC-TASKS / TC-AUTH-API / TC-POSTER-API |
| 2 数据库 | TC-DB / TC-CELERY |
| 3 安全 | TC-SEC / TC-JWT |
| 4 调度 | TC-TASK-SCHED / TC-CELERY |
| 5 OCR | TC-OCR |
| 6 抓取 | TC-CRAWLER / TC-BLOGGER / TC-STOP / TC-CRAWL-SCOPE / TC-VERIFY |
| 7 LLM | TC-EXTRACT / TC-WINDOW / TC-PARSE |
| 8 UI | TC-UI-001 ~ TC-UI-0xx |
| 9 E2E | TC-UI 浏览器场景 |
| 10 海报 | TC-PT-001~005 / TC-PTT-001~009 / TC-PTK-001~007 / TC-PSH-001~011（详见 `tests/poster-test-cases.md`） |

## 谁属于哪个维度但还没标

| 维度 | 现有 md 但缺"维度："标 |
|---|---|
| 1 接口 | `test-poster-api.md` 已经标 |
| 2 数据库 | 已经标 |
| 3 安全 | 已经标 |
| 4 调度 | `test-task-scheduling.md` 已经标；但 `test-celery-test-isolation.md` 已有"维度"标（重复？celery 落到 4） |
| 5 OCR | 缺 "维度：" 标头 |
| 6 抓取 | 6 个 md 都缺 "维度：" 标头 |
| 7 LLM 管道 | 多个 md 缺 |
| 8 UI | `test-frontend-ui-e2e.md` 缺 |
| 9 E2E | （同 8） |
| 10 海报 | 已经标 |

## 还差什么

1. **维度 5 / 6 / 7 / 8 / 9** 类 md 几乎都没标注"维度："，**不是缺文件，缺的是统一索引**。本文件已收全。
2. **维度 9 跨域**：单纯"浏览器测试"还没单独文件——是否需要拆？看项目现状，可能由 `test-frontend-ui-e2e.md` 覆盖足够。
3. **维度 4 重复**：`test-celery-test-isolation.md` 与 `test-task-scheduling.md` 边界含糊。
4. **新增维度 11 提示**："配置 / Django settings" 是否单列？项目是 FastAPI 后端，无此。
5. **新增维度 12 提示**："数据迁移 / 001x migration" 是否单列？已归到 2。

## 维度完整性自检

| 维度 | md 数 | 状态 |
|---|---|---|
| 1 接口 | 9 | ✅ 充裕 |
| 2 数据库 | 2 | ✅ |
| 3 安全 | 2 | ✅ |
| 4 调度 | 2 | ⚠️ 重复 |
| 5 OCR | 1 | ⚠️ 偏少 |
| 6 抓取 | 6 | ✅ |
| 7 LLM | ~4 | ✅ |
| 8 UI | 5 | ✅ |
| 9 E2E | 2 | ✅ |
| 10 海报 | 4（含本索引） | ✅ |

---

## 海报相关的"维度 10" 已补全测试案例

`tests/poster-test-cases.md`：32 个 case（TC-PT-xxx / TC-PTT-xxx / TC-PTK-xxx / TC-PSH-xxx）。

**其他维度**已有对应 md 文件及各自独立的 case 编号体系（多以 TC-XXX-XXX 行号、TC-UI-XXX 编号等）。
