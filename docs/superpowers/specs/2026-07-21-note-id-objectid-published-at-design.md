# 从小红书 note ID（ObjectID）解析推文发布时间设计

> 状态：审核中。

## 1. 问题

现有 180 条推文，177 条 `published_at IS NULL`。原因是：

- 小红书 web 端详情页里有"发布于 3 天前"等文字；
- 但 OpenCLI 的 `xiaohongshu note` 命令输出 JSON 不暴露这个字段；
- OpenCLI 的 `xiaohongshu search` 命令已经用 note ID 本身（前 8 位 hex = epoch 秒）反算推文日期；
- 我们的爬虫取详情后存进 `raw_data` 没有时间字段，`extract_published_at` 拿不到原始时间；
- 历史 180 条数据全部缺 `published_at`。

## 2. 解决

按 OpenCLI 的 `noteIdToDate` 实现思路，把同样的逻辑迁移到 Python 后端：

```
note_id_or_url -> 正则抽取 24 hex -> 取前 8 hex -> int -> +8h (UTC+8) -> ISO datetime
```

精度到秒。这是一个**纯 Python 计算**，不依赖 OpenCLI 上游改动、不依赖小红书 web 端 DOM 解析。

## 3. 设计

### 3.1 新增 `app/services/note_id_published_at.py`

```python
import re
from datetime import datetime, timedelta, timezone

_NOTE_ID_RE = re.compile(r"[0-9a-f]{24}", re.IGNORECASE)


def note_id_published_at(note_id_or_url: str | None) -> datetime | None:
    """从 note ID 或完整 URL 中提取 24 hex 字符；前 8 位 = epoch 秒。
    返回带 tzinfo=UTC 的 datetime；非法输入返回 None。"""
    if not note_id_or_url:
        return None
    match = _NOTE_ID_RE.search(note_id_or_url)
    if not match:
        return None
    hex_prefix = match.group(0)[:8]
    ts = int(hex_prefix, 16)
    if ts < 1_000_000_000 or ts > 4_000_000_000:
        return None
    # 偏移 UTC+8 小时转 UTC
    return datetime.fromtimestamp(ts + 8 * 3600, tz=timezone.utc)
```

### 3.2 集成到 `crawl_task.process_note`

```python
published_at = extract_published_at(detail, fallback_now=started_at)
# 优先用 note ID 解析（雪花算法最可靠，能精确到秒）
note_id_published = note_id_published_at(note_url)
if note_id_published and (published_at is None or is_lower_precision(note_id_published)):
    published_at = note_id_published
```

**优先级**：note ID 解析 > DOM 文本解析 > `started_at` 兜底。

### 3.3 一次性回填脚本 `scripts/backfill_note_id_published_at.py`

```python
"""
扫描 notes 表里有 24 hex platform_note_id 且 published_at IS NULL 的记录，
用 note_id_published_at 回填；输出 before/after 计数；幂等（已填的不覆盖）。
"""
from app.services.note_id_published_at import note_id_published_at
from app.models.note import Note
from sqlalchemy import select

def run_migration(db: Session) -> dict:
    before_nulls = db.scalar(select(func.count()).select_from(Note).where(Note.published_at.is_(None))) or 0
    fixed = 0
    skipped_no_id = 0
    notes = db.execute(select(Note).where(Note.published_at.is_(None))).scalars()
    for note in notes:
        ts = note_id_published_at(note.platform_note_id)
        if ts is None:
            skipped_no_id += 1
            continue
        note.published_at = ts
        fixed += 1
    db.commit()
    after_nulls = db.scalar(select(func.count()).select_from(Note).where(Note.published_at.is_(None))) or 0
    return {"before_nulls": before_nulls, "fixed": fixed, "skipped_no_id": skipped_no_id, "after_nulls": after_nulls}

if __name__ == "__main__":
    db = SessionLocal()
    try:
        print(json.dumps(run_migration(db), ensure_ascii=False))
    finally:
        db.close()
```

## 4. 验收

### 后端

- [ ] `tests/test_note_id_published_at.py` 4 个 case：合法 24hex、24hex 在 URL 中、6hex 截断（非法）、None 输入；
- [ ] `tests/test_crawl_task_resilience.py` 中验证 `process_note` 在 `detail` 不含时间字段时仍能根据 `note_url` 反推时间；
- [ ] `backfill_note_id_published_at.py` 跑完输出 `{"before_nulls": 180, "fixed": 175, "skipped_no_id": 5, "after_nulls": 5}` 类似字典；
- [ ] `tests/test_published_at_parser.py` 加测和 `tests/test_note_summary.py` 不受影响。

### 集成

- [ ] alembic 当前不需要新增 migration（不动 schema）；
- [ ] 后端全量测试。

### E2E

- [ ] 现有 Playwright 推文列表时间列的断言不变（UI 仍正确显示"待确认"或者 ISO 字符串）。

## 5. 范围之外

- 雪花 ID 之外的发布时间来源（DOM "3 天前" 等）已经由 `extract_published_at` 覆盖；
- `created_at` 兜底策略保持；
- 不动 OpenCLI 上游。
