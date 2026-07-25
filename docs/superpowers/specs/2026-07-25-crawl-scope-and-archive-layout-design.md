# 抓取范围语义修复 + 归档按城市/周分目录 — 设计

日期：2026-07-25
关联 TODO：当前待办第 1 条（核查报告 `docs/superpowers/qa/2026-07-25-project-audit.md` 问题 1）
关联既有 spec：`2026-07-21-city-and-keyword-groups-design.md`、`2026-07-17-crawl-scope-config-driven-design.md`

## 1. 背景与目标

### 1.1 已实证的断链

前端 `DashboardView.vue` 提交 `{ type, city, keyword_group_ids, recent_filter, blogger_ids }`，但后端 `CrawlIn` 无 `keyword_group_ids` 字段，pydantic 默认丢弃：

- 只选关键词组 → `payload.keywords` 与 `payload.blogger_ids` 均为空 → 422「请至少启用一个关键词或博主」；
- 组 + 博主 → 任务能跑，但 `resolve_effective_keywords` 因 `model_dump()` 恒含 `keywords` 键，组分支不可达，实际只抓博主。

### 1.2 用户确认的需求语义（2026-07-25）

1. 只选城市 + 关键词（组）→ 只按关键词抓取；
2. 只选博主 → 只按博主抓取；
3. 都选 → 关键词与博主都抓；
4. 城市、抓取周期（`recent_filter`）为每次任务的必填项；
5. 抓取归档按「城市 + 周」分目录。

### 1.3 目标

- 修复 `keyword_group_ids` 在 API 边界被丢弃的问题，打通"组 → 关键词并集"端到端链路；
- 明确并测试上述三条选择语义；
- `recent_filter` 改为必填（无默认值）；
- 归档目录从 `archive/{YYYY-MM-DD}/task-{id}/` 改为 `archive/{city_code}/{ISO 年-W 周}/task-{id}/`，旧目录不迁移、仍可解析。

## 2. 设计

### 2.1 API 层（`app/api/v1/tasks.py`）

`CrawlIn` 调整：

```python
class CrawlIn(BaseModel):
    type: str = 'mixed'
    city: str                                    # 必填（已有）
    keywords: list[str] = []                     # 兼容旧字段
    keyword_group_ids: list[int] = []            # 新增
    recent_filter: Literal['不限','一天内','一周内','半年内']   # 改为必填，去掉默认值
    blogger_ids: list[int] = []
```

入口校验调整（`crawl` 端点）：

1. 城市必须存在且启用（已有）；
2. 显式 `keywords` 必须属于该城市启用关键词（已有）；
3. 新增：`keyword_group_ids` 每个组必须存在、`enabled=true`、且通过 `KeywordGroupCity(enabled=true)` 挂在当前城市，否则 422「关键词组不属于所选城市或已停用」；
4. `blogger_ids` 校验（已有）；
5. effective 范围校验：`resolve_crawl_scope` 结果 keywords 与 bloggers 均为空 → 422「请至少启用一个关键词或博主」（已有逻辑，覆盖"组存在但该城市下无词"的边界）。

### 2.2 范围解析（`app/services/crawl_scope.py`）

`resolve_effective_keywords` 改为：

```
"keywords" 键存在 → 显式词（去空白去重）；空列表 = 显式禁用关键词
"keyword_group_ids" 键存在 → 叠加组并集（显式词 ∪ 组词，都选都抓）
两个键都不存在（老任务 params）→ 回退城市 enabled 关键词表（兼容老调用）
```

- pydantic `model_dump()` 恒含这两个键，所以"键存在"即表达了用户选择意图；旧实现以 `"keywords" in task_params` 直接返回，导致组分支不可达；
- 显式词与组词取**并集**去重（保持顺序，dict.fromkeys），符合"都选都抓"的语义；
- 显式空列表保留旧语义"禁用该维度"（例如只选博主时 `keywords=[]` 不会意外回退到城市关键词表）；
- 组解析逻辑 `_resolve_from_keyword_groups` 不变（仍限定挂在当前城市的组）。

选择语义天然满足：

| 输入 | keywords | bloggers |
|---|---|---|
| 只选组 | 组并集 | [] |
| 只选博主 | [] | 所选博主 |
| 都选 | 组并集（∪显式词） | 所选博主 |
| 都不选 | 回退城市配置 | 城市配置博主 |

`resolve_effective_bloggers` 不变。

### 2.3 归档目录（`app/services/archive.py`）

`archive_task_folder` 增加 `city_code` 参数：

```python
def archive_task_folder(root: Path, started_at: datetime, task_id: int, city_code: str) -> Path:
    iso_year, iso_week, _ = started_at.astimezone(ZoneInfo("Asia/Shanghai")).isocalendar()
    folder = root / city_code / f"{iso_year}-W{iso_week:02d}" / f"task-{task_id}"
```

- 周按任务 `started_at`（Asia/Shanghai）的 ISO 周；
- `archive_task_result` 同步增加 `city_code` 参数；`image.storage_key` 仍取相对 `archive_dir.parent`（即 `data/`）的路径，图片读取端点（`data_dir / storage_key`）无需改动；
- 调用点：`crawl_task.process_note`（两处，传入当前笔记的 city）、`activity_cleanup.rebuild_task_activity_exports`（从 `task.params['city']` 取）；
- `rebuild_task_activity_exports` 的遗留目录 glob 兼容两种深度：`*/task-{id}`（旧）与 `*/*/task-{id}`（新）；
- 旧目录数据不迁移：DB 中既有 `storage_key` 指向旧路径，文件原位保留，读取不受影响。

### 2.4 前端

`DashboardView` 无需改动（已在提交 `keyword_group_ids` 与 `recent_filter`）。本次不改前端代码，只跑回归。

## 3. TDD 计划（先写测试，看红）

新增 `backend/tests/test_crawl_keyword_groups_api.py`：

1. `test_crawl_accepts_only_keyword_groups`：只传组 → 202，`params` 保留 `keyword_group_ids`，断言 Celery 投递参数；
2. `test_crawl_group_not_attached_to_city_422`：组挂在别的城市 → 422；
3. `test_crawl_group_disabled_or_missing_422`：组不存在或 `enabled=false` → 422；
4. `test_crawl_requires_recent_filter`：不传 `recent_filter` → 422；
5. `test_resolve_keywords_union_of_explicit_and_groups`：显式词 + 组 → 并集去重；
6. `test_resolve_keywords_groups_only`：只传组 → 组并集（不落入旧字段空列表陷阱）；
7. `test_archive_folder_uses_city_and_iso_week`：目录形如 `{root}/shanghai/2026-W30/task-9`；
8. `test_archive_result_writes_city_week_layout_and_storage_key`：图片落新目录且 `storage_key` 以 `archive/{city}/{week}/` 开头。

既有测试需同步（签名/行为变化）：

- `tests/test_tasks_api_scope.py`：两处 crawl 调用补 `recent_filter`；
- `tests/test_config_task_duplicate_api.py:74`：`params` 断言加入 `keyword_group_ids: []`；
- `tests/test_activity_cleanup.py`、`tests/test_multi_activity_archive.py`：归档函数签名加 `city_code`；
- `tests/test_crawl_scope_unit.py`：`{"keywords": [...], "keyword_group_ids": [...]}` 用例从"keywords 覆盖组"改为"并集"。

## 4. 验收

- 新增 8 个测试先失败后通过；后端全量测试绿（含既有用例同步）；
- 前端 57 个组件测试与 `npm run build` 绿（无前端改动，回归验证）；
- 真实链路：仪表盘只选城市 + 关键词组提交 → 202，任务 params 含 `keyword_group_ids`，日志出现 `抓取范围生效：keywords=N (override=任务参数)`；
- 新任务归档目录为 `data/archive/{city}/{YYYY}-W{ww}/task-{id}/`，旧目录数据仍可经 API 读取；
- 涉及 `app/tasks/*.py` 与 `app/services/*.py` 改动，验收含"提示重启 celery worker / beat"（重启动作由待办"重启 celery beat 与 worker"条目统一执行）。

## 5. 非目标

- 不改 Celery Beat 调度内容（待办第 2 条）；
- 不改频率控制（待办第 3 条）；
- 不迁移旧归档目录；
- 不改前端交互。
