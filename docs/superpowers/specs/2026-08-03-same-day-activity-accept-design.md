# 同一天合法活动不再被误判为 `all_before_publish`

> 状态：待审核（按 TODO 持续授权，可自动进入开发）。

## 1. 背景与目标

note id 337（"在xhs用这招！机票便宜好多✌（大家快去试"）正文出现日期 "7月27日起"。MiniMax 返回的活动 `start_time` 落在 `2026-07-27` 当日的早些时分（如 `T00:00` 或 `T10:00`），而该笔记 `published_at` 是 `2026-07-27 19:14:25`（Asia/Shanghai）。当前 `activity_validator` 用 `parsed_utc < published_utc` 严格小于判定，所有同日早于发布时间的活动都被拒绝并归类为 `all_before_publish`，最终零活动入库。

产品语义上，**同一天发布的活动**应被认可为合法——用户说"7月27日起"，意思是 7 月 27 日（含）开始的活动，发布时间早晚不应一刀切。

目标：

- `validate_activities` 与 `classify_zero_activity` 改为按"日期"判断，活动 `start_time` 与 `published_at` 同日或之后即视为合法。
- 严格更早的日期（含跨日更早）继续拒绝（行为不变）。
- `all_before_publish` 分支顺手把被拒绝的活动 `(name, start_time)` 写入 task log，便于后续复盘（无需改代码就能知道当时 MiniMax 返回了什么）。

## 2. 已确认的产品规则

1. 活动是否合法按"日期"比较：活动 `start_time.date() >= note.published_at.date()` 即视为合法（接收）。
2. 仅当活动 `start_time.date()` 严格早于 `note.published_at.date()` 才拒绝。
3. `note.published_at` 为 NULL 时维持原行为（全部接收）。
4. 跨时区不影响：双方都先 `.astimezone(UTC)` 再取 `.date()`。
5. `classify_zero_activity` 同步改用日期比较；其余状态语义不变（`ok` / `minimax_empty_retryable` / `no_activity_signals`）。
6. `all_before_publish` 触发的 task log 在原有 INFO 后追加一条 INFO，列出被拒绝的活动（最多 5 条 + 总数）。

## 3. 设计

### 3.1 `validate_activities` 改动

文件 [activity_validator.py](file:///Users/kevin_w/Documents/github/xhs-info-crawl/backend/app/services/activity_validator.py)：

```python
def validate_activities(note, activities, *, future_window_days=60) -> tuple[list[dict], list[str]]:
    published_at = getattr(note, "published_at", None)
    if published_at is None:
        return list(activities), []
    accepted, rejected = [], []
    published_utc = published_at.astimezone(timezone.utc)
    published_date = published_utc.date()
    for activity in activities:
        raw = activity.get("start_time")
        if not raw:
            accepted.append(activity)
            continue
        try:
            parsed = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
        except ValueError:
            rejected.append(f"无法解析 start_time={raw!r}")
            continue
        parsed_utc = parsed.astimezone(timezone.utc)
        if parsed_utc.date() < published_date:
            rejected.append(
                f"活动 {activity.get('name')!r} 日期 {parsed_utc.date().isoformat()} "
                f"早于推文发布时间 {published_date.isoformat()}"
            )
            continue
        accepted.append(activity)
    return accepted, rejected
```

`future_window_days` 参数保留但保留兼容（无副作用）。

### 3.2 `classify_zero_activity` 改动

`_is_before_publish` 函数从"时刻"比较改为"日期"比较：

```python
def _is_before_publish(activity, published_at):
    if published_at is None:
        return False
    raw = activity.get("start_time")
    if not raw:
        return False
    try:
        parsed = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except ValueError:
        return False
    return parsed.astimezone(timezone.utc).date() < published_at.astimezone(timezone.utc).date()
```

`classify_zero_activity` 主体不变，复用 `_is_before_publish`。

### 3.3 `crawl_task` 日志增强

文件 [crawl_task.py](file:///Users/kevin_w/Documents/github/xhs-info-crawl/backend/app/tasks/crawl_task.py) 第 339 行附近，`all_before_publish` 分支在原 INFO 后追加一条 INFO：

```python
if classification in {"all_before_publish", "no_activity_signals"}:
    note.status = "NO_ACTIVITIES"
    log(db, task.id, "INFO", f"未提取到有效活动 原因={classification} url={note.source_url}")
    if classification == "all_before_publish":
        preview = "; ".join(
            f"{a.get('name')!r}@{a.get('start_time')}" for a in extracted[:5]
        )
        suffix = "" if len(extracted) <= 5 else f" (共 {len(extracted)} 条)"
        log(db, task.id, "INFO", f"被拒绝活动预览：{preview}{suffix}")
    ...
```

`no_activity_signals` 不写预览（extracted 本就为空）。

### 3.4 数据 / API

无数据模型变更，无 API 变更。

## 4. 验收

- 后端新增 `tests/test_activity_validator.py` 用例（先红后绿）：
  - `test_validate_accepts_activity_same_day_earlier_than_publish`：published=2026-07-27 19:14 +08:00，活动=2026-07-27 10:00 +08:00 → accepted。
  - `test_validate_accepts_activity_next_day`：published=2026-07-27 19:14 +08:00，活动=2026-07-28 10:00 +08:00 → accepted。
  - `test_validate_rejects_activity_previous_day`：published=2026-07-27 19:14 +08:00，活动=2026-07-26 10:00 +08:00 → rejected。
  - `test_validate_rejects_activity_late_night_previous_day`：published=2026-07-27 00:30 +08:00，活动=2026-07-26 23:59 +00:00（同 UTC 日期但本地是前一日）→ rejected。
  - `test_validate_accepts_same_day_across_timezones`：published=2026-07-27 19:14 +08:00 (11:14 UTC)，活动=2026-07-27 03:00 +00:00（同 UTC 日期）→ accepted。
  - `test_classify_returns_ok_when_activity_same_day_earlier`：publish=19:14、活动=10:00 → `ok`。
  - `test_classify_returns_all_before_publish_only_when_date_strictly_earlier`：publish=活动前一天 → `all_before_publish`。
- 既有测试更新：
  - `test_validate_skips_activity_before_published_at`：当前用 `note_at - timedelta(days=1)`，日期严格早于 published，保持拒绝断言不变（绿）。
  - `test_classify_returns_all_before_publish_when_all_skipped`：所有活动都是 `note_at - timedelta(days=N)`，日期严格早于，保持绿。
- 全量后端 `pytest -q` 全绿（仅剩已知 poster 环境敏感失败）；前端测试与 build 不涉及变更但同步确认。
- `crawl_task.py` 改动走 `app/tasks/*.py`，完成后提示用户重启 worker/beat。

## 5. 部署

按 AGENTS.md "服务进程管理" 章节，改动 `app/services/activity_validator.py` 与 `app/tasks/crawl_task.py` 后**必须**手动重启 celery worker 与 beat，否则 worker 持旧版本判定。完成实现后向用户提示重启。

## 6. 回滚

纯逻辑改动，回滚 = `git revert <commit>`。无迁移、无 schema 变更。