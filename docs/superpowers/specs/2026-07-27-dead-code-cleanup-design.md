# 死代码清理设计（TODO#6）

- 日期：2026-07-27
- 状态：已审核（持续授权）
- 关联：审计 `docs/superpowers/qa/2026-07-25-project-audit.md` 第三节

## 目标

删除生产零调用、仅测试引用的旧实现与未使用导入，消除一个潜在 NameError 地雷，引用它们的测试随之迁移或删除。行为零变化：后端全量测试与前端 build 保持绿。

## 边界确认（2026-07-27 逐一 grep 实证）

### 删除（生产零引用）

| 对象 | 位置 | 仅存的引用方 |
|---|---|---|
| `ScrollPolicy`/`collect_with_scroll`/`check_login`(函数)/`filter_recent_notes`/`search_recent_notes`/`map_opencli_error`/`search_notes` 别名 | `services/crawler.py` | `test_pipeline_services.py` 6 个用例 |
| `process_with_isolation` | `services/pipeline.py:61` | `test_crawl_task_resilience.py` 2 个用例 |
| `TaskLock`/`TaskAlreadyRunning` 整个模块 | `services/task_lock.py` | `test_pipeline_services.py` 1 个用例 |
| `visible_activities`/`generate_markdown`/`generate_xlsx`（旧活动级导出） | `services/report.py` | `test_reports.py` 4 用例 + `test_activity_status_removal.py` 1 用例 |
| `select_activities` | `api/v1/reports.py` | 无 |
| 未使用导入 ×7 | `crawl_task.py` 的 `Keyword`/`ActivityWindow`；`poster_tasks.py` 的 `City`；`reports.py` 的 `BytesIO`/`func`；`poster_renderer.py` 的 `json`；`dedupe_cities.py` 的 `defaultdict` | — |
| 杂项 | `notes.py:219` 函数内重复 import `NoteImage`；`poster_tasks.py:171-173` 空 `pass` 块；`tasks.py:41` 自动顶替 elif 中 `FAILED`/`PAUSED` 不可达分支（查询只取 PENDING/RUNNING/STOP_REQUESTED/SEARCH_DONE/DOWNLOADING/PROCESSING/DEDUPING） | — |

附带收益：`generate_markdown:39` 引用未导入 `datetime` 的 NameError 地雷随删除消失。

### 保留（生产在用，审计后重新核实）

- `crawler.py`：4 个异常类 + `is_verification_required`（opencli_adapter、crawl_task、tasks、pipeline 在用）
- `pipeline.py`：`title_matches_keywords`/`run_stage`/`deduplicate_results`（crawl_task 在用）
- `report.py`：`NoteReportEntry`/`generate_note_markdown`/`generate_note_xlsx`（reports API 在用），以及被它们引用的 `format_activity_markdown`/`_activity_lines`/`CITY_NAMES`（删码阶段实证，初版边界误列入删除项，已修正）
- `crawl_task.py` 的 `Blogger`（关键词组 join 在用，审计后新增代码）

### 测试调整

- `test_pipeline_services.py`：删 6 个死代码用例（crawler 旧函数 3 + scroll 2 + task_lock 1），保留 dedup/extraction/OCR/验证信号 8 组用例
- `test_crawl_task_resilience.py`：删 `process_with_isolation` 2 用例 + import
- `test_reports.py`：删旧活动级导出 4 用例；保留 API 级 6 用例（现行推文级报表路径）
- `test_activity_status_removal.py`：删 `test_visible_activities_filter_excludes_soft_deleted`（`visible_activities` 随删；软删除过滤行为由 activities API 测试覆盖）

## TDD 方案

新增 `backend/tests/test_dead_code_cleanup.py` 静态断言（先红后绿）：

1. `crawler` 不再暴露 7 个旧符号，仍暴露 4 异常 + `is_verification_required`
2. `pipeline` 不再有 `process_with_isolation`，保留 3 个现行符号
3. `import app.services.task_lock` 抛 `ModuleNotFoundError`
4. `report` 不再暴露 4 个旧符号，保留 `generate_note_markdown`/`generate_note_xlsx`
5. `api.v1.reports` 不再有 `select_activities`
6. 6 个被触及文件不存在指定未使用导入（AST 解析校验）

## 验收

- 静态断言测试先红后绿
- 后端全量测试绿（除已知 poster 环境用例）
- `git diff` 纯删除/测试调整，无行为变化；前端无改动
