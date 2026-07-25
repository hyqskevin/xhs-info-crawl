# 2026-07-25 全项目核查报告

> 核查范围：SPEC.md / TODO.md / 各 spec 对照后端（~5200 行）、前端（9 视图）、迁移、脚本与运行进程；含实证验证。
> 本文件是核查证据归档；修复待办见 `docs/TODO.md` 当前待办区。

## 一、严重问题（需求未真正落地）

### 1. 关键词组在 `/tasks/crawl` 被静默丢弃（已实证）

- 前端 `DashboardView.vue:78` 提交 `{ keyword_group_ids: [...] }`；后端 `tasks.py CrawlIn` 无该字段，pydantic 默认丢弃。
- 实证：`CrawlIn.model_validate(payload).model_dump()` 只剩 `type/city/keywords/recent_filter/blogger_ids`。
- 后果：仅选关键词组 → 422「请至少启用一个关键词或博主」；组+博主 → 组被静默忽略，只抓博主。
- `crawl_scope.resolve_effective_keywords` 的 `keyword_group_ids` 分支因 `model_dump()` 恒含 `keywords` 键而不可达。
- 两侧测试各自通过（前端 mock createTask，后端直测 resolve_crawl_scope），接口边界无测试覆盖。

### 2. Celery Beat 每周定时抓取形同虚设

- `celery_app.py` beat_schedule `weekly-crawl` 调度的任务是 `app.tasks.health.ping`（健康检查），不会创建任何 CrawlTask。
- SPEC P0「每周一 02:00 自动抓取」实际不会发生。

### 3. 频率控制（SPEC P1）未实现

- `search_interval_min/max`（10-15s）、`weekly_search_limit`（500/周）在 config 与 `.env.example` 存在，全代码库零引用；`search_recent` 调用间无 sleep。

## 二、需求偏差

- 仪表盘与 SPEC 3.2 不符：无本周统计卡片（API 的 `weekly_notes_count` 实际是全量计数且前端不展示）、无 4 周趋势图、无最近 5 条任务日志。
- 周报管理缺 `DELETE /reports/{id}`（SPEC 3.7 要求删除）；预览为纯文本未渲染 Markdown。
- `docs/api-doc.md` 未文档化 keyword-groups / poster / notes 系列端点。
- 进程状态：celery beat PID 11974 启动于 7/17（TODO 已列未重启）；worker PID 50229 启动于 7/20，早于 0013/0014 迁移，按 AGENTS.md 规则也需重启。

## 三、冗余/死代码

| 位置 | 问题 |
|---|---|
| `services/crawler.py` | 旧函数式实现（`search_recent_notes`/`collect_with_scroll`/`ScrollPolicy`/`map_opencli_error` 等）生产零调用，仅 `test_pipeline_services.py` 引用 |
| `services/report.py` | 旧活动级导出 `generate_markdown`/`generate_xlsx` 无人调用；`generate_markdown:39` 引用未导入的 `datetime`，调用即 NameError |
| `services/pipeline.py` | `process_with_isolation` 仅测试引用 |
| `services/task_lock.py` | `TaskLock` 全项目零引用 |
| `api/v1/reports.py` | `select_activities` 自述"仅调试用"，无调用方 |
| 活动级 `duplicate_candidates` | crawl 持续写入（生产库 702 行），无 API/UI 消费——不可见死数据 |
| 未使用导入 ×10 | `crawl_task.py` 的 `Blogger`/`ActivityWindow`、`poster_tasks.py` 的 `City`、`reports.py` 的 `BytesIO`/`func`、`poster_renderer.py` 的 `json`、`dedupe_cities.py` 的 `defaultdict` |
| 其他 | `notes.py` reprocess 内重复 import NoteImage；`poster_tasks.py` 空 `pass` 块；`tasks.py` 自动顶替中 FAILED/PAUSED 分支不可达 |
| TODO.md | 「OCR 摘要长度保护」重复出现在当前待办与已完成；`dedupe_cities.py` 位置与 spec 不一致（`app/scripts/` vs `scripts/`），脚本与测试已存在但条目未勾选 |

## 四、漏洞与风险

- `poster_tasks.py:127` 路径校验用 `str.startswith`，可被同前缀兄弟目录（`data2/`）绕过；notes/activities 已用 `is_relative_to`。
- 时区混用：`Activity.start_time` 存 naive 本地时间，`published_at` 与筛选参数存 UTC aware；SQLite 字符串比较在边界可能错序。
- `/notes/batch/approve` 不校验"至少 1 条有效子活动"，与单条 `/notes/{id}/review` 规则不一致。
- `/duplicates/{id}/merge` 不校验候选状态，已处理候选可重复 merge。
- 删除 Blogger 不清理 `blogger_cities`；删除 City 不清理 `blogger_cities`/`keyword_group_cities`，notes/activities 的 `city_code` 成悬引用。
- `/auth/login` 无失败限流；token 存 localStorage（内部工具可接受）。
- `.env.example` 缺 `INITIAL_ADMIN_PASSWORD`（0012 迁移读取）与 `MINIMAX_VISION_MODEL`。
- `alembic env.py` 与 `init_database` 的 models import 缺 `keyword_group`/`blogger_city`/`poster`，autogenerate 会漏新表。
- `notes.py` 列表 OCR 聚合 try/except 吞掉全部异常静默降级。

## 五、测试基线（核查时实测）

- 后端：431 passed / 1 failed / 1 skipped。失败项 `test_render_with_mocked_opencli` 为环境敏感测试：mock 了 `subprocess.run` 但未 mock `shutil.which("opencli")`，PATH 无 opencli 必 503（已复现）。测试脆弱性，非产品 bug。
- 前端：57 passed（13 文件）；`PostersListView.spec` 有 1 个 router mock 未捕获错误（噪音，断言通过）；`npm run build` 通过。
