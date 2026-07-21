# 解析并使用小红书真实发布时间设计

> 状态：待审核。

## 1. 目标

`Note.published_at` 必须只承载**小红书页面公布的发布时间**，禁止使用 `Note.created_at`（抓取入库时间）冒充发布时间。

- 抽取阶段解析 OpenCLI 详情字段（`raw_data` 与页面正文）得到真实发布时间。
- 解析失败保留空，UI 显"待确认"。
- 周报归周、列表筛选、博主时间筛选只以 `published_at` 为准。
- 未知 `published_at` 的推文不进入周报。

## 2. 用户已确认的产品规则

1. `Note.published_at` 是唯一真实发布时间字段。
2. 入库时间 (`Note.created_at`) 仅用作审计与回填意图，不再参与业务筛选或周报归属。
3. 小红书页面存在三类时间文本：
   - 绝对日期（如 `2025-07-20`、`2025年7月20日`、`2025/7/20 18:30`）；
   - `MM-DD`（如 `07-20`，需结合任务基准日期补年份）；
   - `N天前`/`N小时前`/`N分钟前`（如 `2天前`、`5小时前`），基于任务基准时间回推。
4. 一律按 `Asia/Shanghai`（UTC+8）解析后存 `TIMESTAMP`；不存无时区数据。
5. 解析失败显示"待确认"（UI 文案），周报不收录。
6. `NoteUpdate` 允许用户手动设定/清空 `published_at`；清空后 UI 显示"待确认"。

## 3. 设计

### 3.1 数据模型

`Note.published_at: Mapped[datetime | None]` 沿用既有字段类型；存储统一 `TIMESTAMPTZ`。**不新增列**。

### 3.2 解析服务

新模块 `app/services/published_at.py`：

```python
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import re

SHANGHAI = timezone(timedelta(hours=8))


@dataclass(frozen=True)
class PublishedAtResult:
    value: datetime | None        # 已解析的 UTC datetime；None 表示未解析
    confidence: float             # 0.0 ~ 1.0
    source: str                   # "absolute" | "month_day" | "relative" | "none"


_PATTERNS = [
    ("absolute", re.compile(r"(20\d{2})[-/.年](\d{1,2})[-/.月](\d{1,2})(?:日)?(?:[ T](\d{1,2}):(\d{1,2}))?")),
    ("month_day", re.compile(r"(?<!\d)(\d{1,2})[-/.月](\d{1,2})(?:日)?(?:[ T](\d{1,2}):(\d{1,2}))?")),
    ("relative_day", re.compile(r"(\d{1,2})\s*天前")),
    ("relative_hour", re.compile(r"(\d{1,2})\s*小时前")),
    ("relative_minute", re.compile(r"(\d{1,2})\s*分钟前")),
]


def parse_published_at(raw_text: str, *, now_local: datetime | None = None) -> PublishedAtResult:
    """Parse 真实发布时间 from raw text or detail page snippet.

    `now_local` is the task's基准时间（Asia/Shanghai），用于推断 N天前/月-日。
    """
    text = (raw_text or "").strip()
    if not text:
        return PublishedAtResult(None, 0.0, "none")
    now = (now_local or datetime.now(SHANGHAI)).astimezone(SHANGHAI)
    # 1) 绝对日期
    for name, pattern in _PATTERNS:
        match = pattern.search(text)
        if match and name == "absolute":
            year, month, day = int(match.group(1)), int(match.group(2)), int(match.group(3))
            hour = int(match.group(4) or 0); minute = int(match.group(5) or 0)
            try:
                local = datetime(year, month, day, hour, minute, tzinfo=SHANGHAI)
            except ValueError:
                return PublishedAtResult(None, 0.0, "none")
            return PublishedAtResult(local.astimezone(timezone.utc), 1.0, "absolute")
        if match and name == "month_day":
            # 必须有完整月份 + 日期。无年份，结合 now_local。
            month, day = int(match.group(1)), int(match.group(2))
            year = now.year
            try:
                local = datetime(year, month, day, int(match.group(3) or 0), int(match.group(4) or 0), tzinfo=SHANGHAI)
            except ValueError:
                return PublishedAtResult(None, 0.0, "none")
            if local > now + timedelta(days=2):
                local = local.replace(year=year - 1)
            return PublishedAtResult(local.astimezone(timezone.utc), 0.85, "month_day")
        if match and name == "relative_day":
            days = int(match.group(1))
            return PublishedAtResult((now - timedelta(days=days)).astimezone(timezone.utc), 0.7, "relative_day")
        if match and name == "relative_hour":
            hours = int(match.group(1))
            return PublishedAtResult((now - timedelta(hours=hours)).astimezone(timezone.utc), 0.7, "relative_hour")
        if match and name == "relative_minute":
            minutes = int(match.group(1))
            return PublishedAtResult((now - timedelta(minutes=minutes)).astimezone(timezone.utc), 0.6, "relative_minute")
    return PublishedAtResult(None, 0.0, "none")


def extract_published_at(detail: dict[str, Any], *, fallback_now: datetime) -> datetime | None:
    """Try several keys in the OpenCLI note detail; return UTC datetime or None."""
    candidates = []
    raw = detail or {}
    for key in ("published_at", "publishedAt", "publish_time", "publishTime", "date", "time"):
        value = raw.get(key)
        if value:
            candidates.append(str(value))
    text_fields = []
    for key in ("content", "title", "snippet"):
        value = raw.get(key)
        if isinstance(value, str):
            text_fields.append(value)
    text = " ".join(candidates + text_fields)
    result = parse_published_at(text, now_local=fallback_now.astimezone(SHANGHAI))
    return result.value
```

模块要点：

- 输入来源：OpenCLI `note` 命令返回的 `data` 字段中的 `published_at`/`publishTime`/`date`/`time` 等键。
- 备选来源：详情 `content`/`title`/`snippet` 文本。
- 一律在 Asia/Shanghai 内解析后转 UTC 存储。
- 返回 `None` 代表"无法解析"，调用方不应回退到 `created_at`。

### 3.3 入库时回填 `published_at`

`backend/app/tasks/crawl_task.py::process_note`：

```python
fallback_now = started_at  # 任务级基准时间
note.published_at = extract_published_at(detail, fallback_now=fallback_now)
```

仅在新推文插入时执行；`NoteUpdate` 路径由前端传值决定。

### 3.4 列表筛选与周报归周

`backend/app/api/v1/notes.py::list_notes`：

- `start_date`/`end_date` 过滤条件从 `func.coalesce(Note.published_at, Note.created_at)` 改为仅 `Note.published_at`。
- 推文 `published_at IS NULL` 时不参与日期范围过滤（等价于时间"待确认"）。

`backend/app/api/v1/reports.py::select_notes`：

- 同上，过滤改为 `Note.published_at`，`published_at IS NULL` 的推文不进周报。
- 错误提示：`"所选城市和周次没有已审核推文，请先在活动管理中审核通过"` 保留。

### 3.5 抓取时间范围

`backend/app/services/crawler.py::filter_recent_notes`：

- 当前基于 `note["published_at"]`（OpenCLI 搜索结果），函数签名不变。
- 若 OpenCLI 返回的 `published_at` 是 `None` 或缺失，**视为已抓取**（不丢弃，因为用户在调整过滤后还要看历史）。这一行为与现状保持一致，但需在日志中记录。
- 新增 `parse_published_at` 工具：用详情阶段拿到的 raw 文本回填，不影响搜索过滤。

### 3.6 服务日志

`process_note` 在解析失败时记录：

```
log(db, task.id, "INFO", f"未解析真实发布时间：{note.title or note_url}")
```

### 3.7 报告输出

`backend/app/services/report.py::generate_note_markdown`：

- `note.published_at` 不为空：直接展示。
- 为空：显示 `f"{note.created_at.isoformat()}（发布时间待确认）"`（保持 markdown 行为可见）。**不在周报收录筛选中使用 created_at**，仅在 markdown 文本里用 `created_at` 占位。

### 3.8 前端

`frontend/src/views/ActivitiesView.vue`：

- 列表"发布时间"列：`formatTime(scope.row.published_at)` 而不是 `published_at || created_at`。
- 当 `published_at` 为空：显示"待确认"。
- 编辑表单保留 `ElDatePicker`，支持清空（视为"待确认"）。
- 详情页沿用相同规则。

`frontend/src/views/ReportsView.vue`：无变化。

### 3.9 Schema/API

`NoteUpdate.published_at`：保持 `datetime | None`。

`GET /api/v1/notes`：返回 `published_at`（可能是 null）和 `created_at`，由前端决定展示。

## 4. 验收

### 后端

- [ ] `parse_published_at` 单元测试覆盖：绝对日期（含中英文分隔符）、`MM-DD`、`7天前`、`5小时前`、`30分钟前`、空文本、未来日期拒绝、垃圾文本。
- [ ] `extract_published_at` 在不同 `detail` 键组合下能找到合理时间。
- [ ] `process_note` 把解析结果写入 `note.published_at`；解析失败留空。
- [ ] 解析失败时日志记录。
- [ ] 列表筛选 `start_date/end_date` 仅以 `published_at` 为准。
- [ ] 周报收录仅用 `published_at`；`published_at` 为空的推文不进周报。
- [ ] 数据库迁移：无需新增列；`Note.published_at` 保留 nullable。

### 前端

- [ ] 列表"发布时间"列在没有 `published_at` 时显"待确认"，不再回退到 `created_at`。
- [ ] 编辑对话框允许清空 `published_at`（按"待确认"展示）。
- [ ] 详情保留同样行为。

### 测试案例

- [ ] 后端 `pytest -q` 全过。
- [ ] 新增 `tests/test-parse-real-published-at.md` E2E 文档。

## 5. 风险与回滚

| 风险 | 缓解 |
|---|---|
| 历史脏数据 `published_at` 缺失，导致旧推文不再进周报 | 通过迁移脚本扫描并把 `raw_data` 中的时间字段回填一次；详情见回填任务后续单独处理。 |
| `MM-DD` 解析跨年错误 | 与 `now` 比较，跨年后回退到上一年。 |
| `Asia/Shanghai` 跨夏令时误解 | 国内无夏令时，保持固定 UTC+8。 |
| 解析错误把无关时间当成发布时间 | 优先级：绝对 > MM-DD > relative；并加 confidence，UI 可据此过滤。 |

## 6. 范围之外

- 阶段二：PostgreSQL（`TIMESTAMPTZ` 已经兼容）。
- 已知关联问题"零活动推文"的处理：在 TODO 3 处理。
