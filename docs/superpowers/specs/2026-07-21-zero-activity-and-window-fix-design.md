# 零活动推文处理 + 活动日期窗口改为"≥推文发布时间"

> 状态：待审核。

## 1. 目标

把当前的"零活动推文标记处理完成"问题拆清楚，并且**修正活动日期窗口为"活动 ≥ 推文发布时间"**（不再用"任务开始后 60 天"窗口）。

- 不再有"未来 60 天"窗口：仅判 `activity.start_time >= note.published_at`。
- `MiniMax` 返回空数组时区分"页面有活动信号但未识别出"和"页面真没信号"。
- 降级解析 `7.18`、`7/18`、`7.18 18:00`、`7/18` 等无年份月日格式。
- 0 活动的推文不能审核通过、不能进周报。
- 已有脏数据可重新处理并补齐子活动。

## 2. 已确认的产品规则

1. 活动进入推文数据库 **当且仅当**：`activity.start_time >= note.published_at`。早于推文发布时间的视为 OCR 错识，必须跳过。
2. 推文 `published_at` 为空时（"待确认"）：
   - 不做时间过滤，全部接收推文页面提取到的活动；
   - 但用户审核/周报时仍要看到"发布时间待确认"标识。
3. 抓取阶段（`search_recent_notes`、`blogger_notes`）**不做** 单条活动时间过滤；只按小红书原生时间筛选"近一周"等。
4. 任务日志要显示零活动的具体原因：
   - `全早于发布时间`：所有识别活动都早于 `note.published_at`；
   - `MiniMax 返回空`：LLM 无抽取能力或网络失败，重试即可恢复；
   - `无可识别活动`：OCR/正文都没信号（如纯图片但识别无文字）。
5. 异常空结果不影响其他推文继续处理。
6. 没有有效子活动的推文：
   - 不能审核通过；
   - 不能进入周报；
   - 重处理时可补齐。
7. 降级解析：`7.18`、`7/18`、`7月18日` 等无年份格式，结合 `Note.published_at` 推断年份（同年或下一月跨年时回退）。
8. 历史脏数据：
   - 保留全部已有活动；
   - 提供一次性重处理入口（不破坏其它 TODO）。

## 3. 设计

### 3.1 数据模型

无新增列。`Note.published_at`、`Note.activities`、OCR 字段沿用。

#### `Note` 状态（process_stage）

调整 `Note.status` 状态机：

| 旧状态 | 新状态 | 说明 |
|---|---|---|
| DOWNLOADED | DOWNLOADED | 已抓到详情 |
| OCR_DONE | OCR_DONE | OCR 完成 |
| EXTRACTING | EXTRACTING | 提取中（瞬时） |
| PROCESSED | PROCESSED | ≥1 个通过校验的活动已入库 |
| FAILED | FAILED | 任何阶段不可恢复错误 |
| OCR_DONE + 0 活动 | NO_ACTIVITIES | OCR 完成但 0 活动通过校验，可重处理 |
| DOWNLOADED + 0 详情 | DOWNLOAD_FAILED | 抓取详情失败，可重试 |

具体值定义：

- `NO_ACTIVITIES`：OCR/正文识别到活动，但全部因为"早于发布时间"被过滤，或完全没有活动信号；
- `EMPTY_RESULT_RETRYABLE`：MiniMax 返回空，OCR/正文有信号，可重试。

### 3.2 校验函数

新建 `app/services/activity_validator.py`：

```python
@dataclass(frozen=True)
class ActivityDecision:
    activity: dict                  # 校验通过的活动
    reason: str | None = None       # 跳过原因


def classify_zero_activity(note: Note, extracted: list[dict]) -> str:
    """返回 0 活动原因:
        'all_before_publish'  - 全部早于发布时间
        'minimax_empty_retryable' - MiniMax 空但正文存在活动信号
        'no_activity_signals'  - 无任何活动信号
    """
    body = (note.content or "").strip()
    has_signals = _has_activity_signal(body, note.raw_data or {})
    if not extracted:
        if has_signals:
            return "minimax_empty_retryable"
        return "no_activity_signals"
    if all(_is_before_publish(activity, note.published_at) for activity in extracted):
        return "all_before_publish"
    return "ok"


def validate_activities(
    note: Note,
    activities: list[dict],
    *,
    future_window_days: int = 60,   # 仅作"距推文发布时间太远"提示用
) -> tuple[list[dict], list[str]]:
    """返回通过校验的活动列表 + 全部跳过原因文本。"""
    if note.published_at is None:
        return activities, []   # 待确认推文全部接收
    accepted: list[dict] = []
    rejected: list[str] = []
    for activity in activities:
        start = activity.get("start_time")
        if not start:
            accepted.append(activity)
            continue
        try:
            start_dt = datetime.fromisoformat(str(start).replace("Z", "+00:00"))
        except ValueError:
            rejected.append(f"无法解析 start_time={start!r}")
            continue
        if start_dt.astimezone(timezone.utc) < note.published_at.astimezone(timezone.utc):
            rejected.append(f"活动 {activity.get('name')!r} 日期 {start} 早于推文发布时间 {note.published_at.isoformat()}")
            continue
        if (start_dt - note.published_at).days > future_window_days:
            # 不再硬过滤，仅提示（产品要求：不卡上限）
            pass
        accepted.append(activity)
    return accepted, rejected
```

### 3.3 解析降级

`app/services/extraction.py::normalize_activity_datetime`：

- 现有正则 `(?:(20\\d{2})[-/.年])?(\\d{1,2})(?:[-/.]|月)(\\d{1,2})(?:日)?...`
- 缺年份时，使用 **`note.published_at`** 当基准（不再是任务 `started_at`）。
- 新增匹配：`7.18`、`7.18 18:00`、`7.18 18:30`（分隔符为 `.`）。
- 跨年规则：解析出的"月-日" > `note.published_at` 的"月-日"+ 2 天 → 回退 1 年。

### 3.4 process_note 改造

`backend/app/tasks/crawl_task.py`：

```python
from app.services.activity_validator import classify_zero_activity, validate_activities

# 替换原 ActivityWindow 逻辑
window_status = classify_zero_activity(note, extracted)
if window_status in {"all_before_publish", "minimax_empty_retryable", "no_activity_signals"}:
    # 0 活动
    note.status = "NO_ACTIVITIES" if window_status in {"all_before_publish", "no_activity_signals"} else "EMPTY_RESULT_RETRYABLE"
    log(db, task.id, "INFO", f"未提取到有效活动 原因={window_status} url={note.source_url}")
    task.success_notes += 0  # 不计入成功
    db.commit()
    return False

accepted, rejected = validate_activities(note, extracted)
for reason in rejected:
    log(db, task.id, "INFO", f"跳过活动 原因={reason}")
if not accepted:
    note.status = "NO_ACTIVITIES"
    log(db, task.id, "INFO", f"全部活动被过滤 url={note.source_url}")
    db.commit()
    return False

for fields in accepted:
    activity = Activity(note_id=note.id, **fields_without_status)
    db.add(activity)
    db.flush()
    create_duplicate_candidates(db, activity)

note.status = "PROCESSED"
```

### 3.5 周报收录

`backend/app/api/v1/reports.py`：

- 增加"零活动推文跳过"：只有 `note.activities` 至少 1 条且未软删才入选周报。
- `_visible_note` 调整为：

```python
def _visible_note(db, note_id):
    note = db.scalar(select(Note).where(Note.id == note_id, Note.review_status.notin_(["DELETED", "MERGED"])))
    if note is None:
        raise HTTPException(404, "推文不存在")
    if note.review_status == "APPROVED":
        # 已审核通过的推文必须至少 1 条有效子活动
        has_activity = db.scalar(select(func.count(Activity.id)).where(
            Activity.note_id == note.id, Activity.deleted_at.is_(None))) or 0
        if has_activity == 0:
            raise HTTPException(422, "推文无有效子活动，请重新处理后再审核")
    return note
```

### 3.6 重处理入口

新增 `POST /api/v1/notes/{id}/reprocess`：

- 接受 ID；
- 仅当 `note.status in ("NO_ACTIVITIES", "EMPTY_RESULT_RETRYABLE")` 时可调用；
- 调 `process_note` 走完整流程，再次尝试 OCR/提取；
- 不影响 `review_status`。

### 3.7 文档

- `docs/api-doc.md`：补 `POST /api/v1/notes/{id}/reprocess` 接口定义；
- `docs/database-design.md`：`Note.status` 增加新枚举；
- `docs/TODO.md`：完成后移到已完成区。

## 4. 验收

### 行为

- [ ] `activity.start_time >= note.published_at`：通过；
- [ ] `activity.start_time < note.published_at`：跳过并记录原因；
- [ ] `note.published_at IS NULL`：全部接收；
- [ ] MiniMax 空数组 + 正文有信号：`note.status = EMPTY_RESULT_RETRYABLE`；
- [ ] MiniMax 空 + 正文无信号：`note.status = NO_ACTIVITIES`；
- [ ] 全部活动早于推文：`note.status = NO_ACTIVITIES`；
- [ ] `7.18`、`7/18`、`7.18 18:30`、`7月18日` 能解析到 `note.published_at` 的年份；
- [ ] 跨年回退（如 12 月在发布月之后，回退 1 年）；
- [ ] 异常空结果不影响其他推文。

### 业务

- [ ] 0 活动的已审核推文被重置为 `PENDING` 或保持 `NO_ACTIVITIES` 时不能审核通过；
- [ ] 0 活动的推文不进周报（即使本周发布）；
- [ ] `POST /api/v1/notes/{id}/reprocess` 可重处理零活动推文，补齐活动。

### 任务日志

- [ ] 抓取阶段日志区分三个 0 活动原因；
- [ ] 任务汇总显示成功/零活动推文数。

### 前端

- [ ] 推文编辑表单：状态为 `NO_ACTIVITIES` 时显示"未识别到活动，请重新处理"；
- [ ] 推文详情页展示"重新处理"按钮（仅 NO_ACTIVITIES 状态时可见）。

### 测试

- [ ] 后端全量 `pytest -q` 通过；
- [ ] 新增 `backend/tests/test_activity_validator.py`；
- [ ] 新增 `tests/test-note-zero-activity-and-window.md` E2E 文档。

## 5. 风险与回滚

| 风险 | 缓解 |
|---|---|
| 历史脏数据无 `published_at` 时全部接收 → 0 活动的脏数据可能很多 | 一次性回填脚本：扫描 `Note.raw_data` 抽 `published_at`；本 TODO 不强制执行，可作为下条 TODO。 |
| 0 活动推文"积压"不让审核 | 提供 `reprocess` 入口 + 状态可视化。 |
| 解析降级可能误把"7.18"识别为某年某月 | 与 `note.published_at` 严格绑定，跨年回退；confidence 由调用方判断。 |

## 6. 范围之外

- TODO 1（移除子活动审核状态）独立；
- TODO 2（真实发布时间解析）独立；
- TODO 4（OCR 摘要展示）独立；
- 历史数据回填脚本另立；
- 阶段二（PostgreSQL / Redis / MinIO）独立。
