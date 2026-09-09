# 全工程时间统一北京墙钟（东八区）设计

> 状态：已审核（持续授权）。来源：2026-09-07 用户反馈「整个工程的日期有些是用的英国时区，导致任务分析时候时间出错，应该统一改到东部时区」。经确认：目标 = 东八区北京时间（Asia/Shanghai）；深度 = 存储层统一（用户已选）。

## 1. 问题与根因

### 1.1 现状：两套口径并存

`docs/database-design.md` 时间口径章节（L259-262）定义了两套存储口径：

| 数据 | 现行存储口径 |
|---|---|
| 审计字段（created_at / updated_at / started_at / finished_at / deleted_at / resolved_at / cooldown_until 等） | UTC naive（`datetime.now(timezone.utc)` 落库丢 tzinfo） |
| 业务时间（`notes.published_at` / `activities.start_time` / `end_time`） | 北京墙钟 naive（Asia/Shanghai 墙钟数字，不带 tzinfo） |

显示层靠 `formatUtcAsShanghai`（frontend/src/utils/datetime.ts）把 UTC 转东八区；API 出口靠 `UtcJsonResponse`（app/core/json_response.py）给 naive 字符串补 `Z`。

### 1.2 已定位的出错点（8 小时错位的来源）

1. **`UtcJsonResponse` 无差别补 `Z`**（app/core/json_response.py:34）：北京墙钟 naive 的 `published_at` / `start_time` 出口也被标成 UTC。
2. **`published_at` 被二次 +8h**：ActivitiesView.vue:118-119/260 对 `published_at` 调 `formatUtcAsShanghai`，本已是东八区的墙钟再 +8h——北京 16:00 后发布的笔记在活动管理里日期错一天。
3. **活动时间入库偏 8h**：ActivitiesView.vue:148/171-172/210 保存时 `new Date(...).toISOString()` 转真 UTC 后存进北京墙钟列（SQLite 落库为带 `+00:00` 的字符串），与 `week_bounds` 等北京墙钟边界比较错位。
4. **海报默认名用 UTC**：PosterWizardView.vue:71 `new Date().toISOString().slice(0,16)`，名字里的时间慢 8 小时。
5. **跨口径直接比较**：app/api/v1/notes.py:314 用 UTC 的 `datetime.now(tz.utc)` 与北京墙钟 `published_at` 比较，日期窗口边界差 8h。
6. **dashboard 周一起点绕行换算**：app/api/v1/dashboard.py:22 北京周一 → astimezone(UTC) → naive，再与 UTC 存储比较；迁移后可直接用北京 naive，绕行逻辑删除。

### 1.3 为什么选「统一存储」而不是「只修泄漏」

同类 8 小时 bug 已修过三轮（2026-07-25 审计发现口径混用、2026-07-28 显示层修复、2026-08-16 补 `Z` 后缀），根因是「两套口径 + 每个新端点都要记住用哪套」。单口径北京墙钟让约定变成「所有时间列都是北京墙钟 naive」，从结构上消灭这一类错误。

## 2. 设计

### 2.1 目标口径

- **DB 所有时间列**：北京墙钟 naive（`Asia/Shanghai` 墙钟数字，无 tzinfo）。SQLite 仍是 naive 存储，无需改列类型。
- **API 出口**：所有 datetime 一律输出带 `+08:00` 后缀的 ISO8601（JS 在任何机器时区都能解析出正确时刻）。
- **前端**：显示与提交均固定 Asia/Shanghai 墙钟，不依赖本机时区。

### 2.2 时区工具与写侧统一

新增 `backend/app/core/timeutil.py`：

```python
from datetime import datetime
from zoneinfo import ZoneInfo

CN_TZ = ZoneInfo("Asia/Shanghai")

def now_cn() -> datetime:
    """北京墙钟 naive（SQLite 存储口径）。"""
    return datetime.now(CN_TZ).replace(tzinfo=None)

def to_cn_naive(value: datetime) -> datetime:
    """aware → 北京墙钟 naive；naive 视为已是北京墙钟原样返回。"""
    return value.astimezone(CN_TZ).replace(tzinfo=None) if value.tzinfo else value
```

写侧替换：生产代码全部 `datetime.now(timezone.utc)` → `now_cn()`。涉及（以 grep 为准，逐文件过）：

- **models 默认值**（16 文件）：report、note、blogger_city、schedule、blogger_group、keyword_group、group、audit、task、config、xhs_account、duplicate、search_usage、poster、user、activity
- **api 层**：tasks.py、activities.py:72/132/141、duplicates.py:73/88、audit_logs.py:119、notes.py:314（reference_now 改 `now_cn()`）
- **services**：stop_recovery（anchor 比较两侧同改 CN）、maintenance、schedule_service、prune_orphan_duplicates、diagnostics、archive（naive 语义从 UTC 改北京，`replace(tzinfo=ZoneInfo("UTC"))` 处改 `CN_TZ`）
- **tasks**：crawl_task.py、crawl/notes.py、crawl/runtime.py、crawl/accounts.py
- **dashboard.py:22**：删除绕行换算，直接构造北京 naive 周一

**明确不动**（协议内部时间或已正确）：

- `app/core/security.py` JWT `exp`：保持 aware UTC（pyjwt 按 epoch 换算，协议时间非显示时间）
- `app/services/maintenance.py:23` 文件 mtime cutoff：`datetime.now(timezone.utc).timestamp()` 是系统时间域（与文件 mtime 比较），若改 naive 北京墙钟 `.timestamp()` 会按机器时区解释——必须保持 aware UTC
- `activity_validator` 内部 aware 运算（双方 `astimezone(utc)` 再比日期，口径自洽）
- `celery_timezone = "Asia/Shanghai"`（config.py:162）
- `search_rate_limit` ISO 周、`published_at` / `note_id_published_at` 解析、活动窗口（均已按 Asia/Shanghai）
- **历史迁移文件**（0012/0020 的 seed UTC 时间戳不改文件，由 0029 数据迁移统一修正）

### 2.3 数据迁移 `0029_unify_timestamps_to_cn`

Alembic data migration，upgrade 分两步：

**第一步：审计列 UTC → 北京墙钟（naive +8h）**。列清单（表.列）：

- users.created_at；audit_logs.created_at；bloggers.created_at；cities.created_at
- crawl_tasks.created_at / started_at / finished_at；task_logs.created_at
- notes.created_at；activities.created_at / updated_at / deleted_at
- duplicate_candidates.created_at / resolved_at；note_duplicate_candidates.created_at / resolved_at
- xhs_accounts.created_at / updated_at；scheduled_crawls.created_at / updated_at / cooldown_until
- search_usage.updated_at；weekly_reports.created_at / updated_at
- blogger_cities.created_at；blogger_groups.created_at；blogger_group_members.created_at
- keyword_groups.created_at；keyword_group_cities.created_at；keyword_group_words.created_at
- poster_templates.created_at / updated_at；poster_tasks.created_at / updated_at；groups.created_at

实现：Python 逐行读字符串，`s.replace(" ", "T", 1)` 后 `datetime.fromisoformat`（兼容 `Z` 后缀）：
- 带 offset / `Z` → `astimezone(CN_TZ).replace(tzinfo=None)` 写回；
- naive → `+8h` 写回；
- NULL / 解析失败 → 原样保留并 WARNING 日志。

**第二步：业务列防御性归一**。`notes.published_at`、`activities.start_time` / `end_time`：
- 带 offset / `Z`（来源：泄漏点 3 的 `toISOString` 误存）→ 转 Beijing naive（这是修复）；
- naive → **不动**（已是北京墙钟）。

**安全网**：

- upgrade 第一步之前用 `sqlite3` backup API 备份 DB 文件到 `data/backups/pre-0029-<UTC时间戳>.db`（路径经 Settings.data_dir 解析；备份失败则中止迁移抛错）。
- downgrade 仅对称还原审计列（-8h，naive 化 offset 已转的行不可逆，文档标注 downgrade 仅用于刚升级误操作的立即回退）。
- 幂等性由 alembic 版本机制保证（单次执行）。

### 2.4 API 出口契约

`app/core/json_response.py`：`UtcJsonResponse` 改名 **`CnJsonResponse`**（main.py:31/44-45 同步，含测试引用）：

- naive ISO 字符串 → 追加 `+08:00`（不再补 `Z`）；
- naive datetime 对象（防御分支）→ `replace(tzinfo=CN_TZ)`；
- 已带 `Z` / offset 的字符串原样保留。

### 2.5 前端

`frontend/src/utils/datetime.ts`：

- `formatUtcAsShanghai` 改名 **`formatCnDateTime`**：输入预期带 `+08:00` / `Z`（兜底：naive 补 `+08:00` 而非 `Z`）；仍用 `Intl.DateTimeFormat('zh-CN', { timeZone: 'Asia/Shanghai' })` 格式化，输出 `YYYY-MM-DD HH:mm:ss` 不变；空值 `'-'`、非法原样返回的语义不变。
- 新增 `toCnWallString(date: Date): string`：Intl 按 Asia/Shanghai 取各字段拼 `YYYY-MM-DDTHH:mm:ss`（naive 墙钟），供表单提交。
- 新增 `cnWallStamp(): string`：`YYYY-MM-DD-HH-mm` 北京墙钟，供文件命名。
- 调用点替换（grep `formatUtcAsShanghai` 全量）：ActivitiesView、DashboardView、TasksView、CrawlTrendChart 等仅改 import 与函数名，显示逻辑不变。

提交侧修复：

- **ActivitiesView.vue:148/171-172/210**：`new Date(x).toISOString()` → `toCnWallString(new Date(x))`，入库即北京墙钟。
- **PosterWizardView.vue:71**：`new Date().toISOString().slice(0,16)...` → `cnWallStamp()`。
- **DashboardView.vue:285/356/359**：`checked_at: new Date().toISOString()` → `toCnWallString(new Date())`。

### 2.6 文档口径

- `docs/database-design.md` 时间口径章节重写为单口径：所有时间列 = 北京墙钟 naive；API datetime 带 `+08:00`；前端经 `formatCnDateTime` 显示（仅格式化，无时区换算语义）。
- `docs/TODO.md` 登记本条目，完成后 `[x]` 移入已完成区。

## 3. 测试（TDD 先红后绿）

### 3.1 后端新增

| 文件 | 用例 |
|---|---|
| `tests/test_timeutil.py` | `now_cn()` 为 naive 且与 `datetime.now(CN_TZ)` 墙钟差 < 2s；`to_cn_naive` 对 aware/naive 两分支 |
| `tests/test_migration_0029.py` | 临时 DB 造混合数据：naive UTC、带 `+00:00`、带 `Z`、NULL、业务列（published_at naive / start_time 带 offset）→ upgrade → 审计列 +8h 或 offset 归一、业务列 naive 不动而 offset 行归一、备份文件生成；downgrade 审计列 -8h |
| `tests/test_json_response_cn.py` | naive 字符串补 `+08:00`；naive datetime 补 `CN_TZ`；带 `Z`/offset 原样；嵌套 dict/list 递归 |
| `tests/test_notes_reference_now_cn.py` | published_at 北京 16:00+ 场景：reference_now 用北京墙钟，日期窗口判定正确（红：现用 UTC now 错位） |

### 3.2 存量测试更新

- 断言 UTC 值 / `Z` 后缀的测试按新口径改（2026-07-28 spec 的 `datetime.spec.ts`、DashboardView/TasksView 时间断言、diagnostics/stop_recovery/schedule_service/maintenance 等后端断言），红 → 绿。
- `formatUtcAsShanghai` → `formatCnDateTime` 重命名波及的 import 与 spec。

### 3.3 前端

- `src/utils/datetime.spec.ts` 重写：`+08:00` 输入原样格式化；`Z` 输入正确转换；naive 兜底补 `+08:00`；`toCnWallString`（构造非东八区 UTC 时刻断言墙钟正确）；`cnWallStamp` 格式。
- `ActivitiesView.spec.ts`：保存 payload 断言为 `YYYY-MM-DDTHH:mm:ss` 墙钟字符串（不再 `toISOString` 的 `Z` 串）。

## 4. 验收

- 后端全量 pytest、前端 `npm run test -- --run`、`make test` 不新增失败（当前基线失败维持原数）；
- **重启 worker / beat**（tasks/services/models 变更）；
- 真实页面验证（chrome-devtools MCP）：仪表盘日志时间 = 本机东八区时钟；活动管理「发布时间」与小红书卡片时间一致（不再 +8h）；活动抽屉保存的时间重开不偏移；趋势图 x 轴正确；
- 生成的周报内容时间口径正确；
- 迁移在真实 `data/app.db` 上执行成功，`data/backups/` 出现备份文件，任务列表/日志历史时间整体 +8h 后与事实相符；
- TODO.md 打勾移入已完成区，独立 commit。

## 5. 风险

| 风险 | 对策 |
|---|---|
| 迁移批量改历史数据，出错不可逆 | 迁移前自动 backup（2.3 安全网）；alembic 单次执行；迁移测试覆盖混合数据形态后再上真实库 |
| 存量 `start_time` 混有带 offset 的错行 | 2.3 第二步专门归一；naive 行视为已正确不动 |
| downgrade 不完全对称 | 文档标注仅用于误升级立即回退；backup 是最终兜底 |
| 机器时区非东八区 | 后端 `now_cn` 显式 ZoneInfo 不依赖 TZ env；前端 Intl 固定 Asia/Shanghai |
| JWT exp 若误改成 naive 会引入登录时长漂移 | 2.2 明确不动清单含 security.py，实现时 grep 复核 |
| 并发会话同改一工作区 | Edit 前重读文件；pytest 全量输出不截断；提交仅 stage 本条目文件 |
