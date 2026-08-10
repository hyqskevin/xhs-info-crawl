# 修复 extract_activity_fields 非法日期导致 "day is out of range for month" 崩溃

## 1. 背景

用户 2026-08-10 反馈抓取报错 "day is out of range for month"。

## 2. 根因（systematic-debugging Phase 1）

`backend/app/services/extraction.py` 的 `extract_activity_fields` 函数第 69/71/73 行三个 `datetime()` 构造**未包 try/except**：

```python
if iso:
    start_time = datetime(int(iso.group(1)), int(iso.group(2)), int(iso.group(3)), ...).isoformat()  # 第69行
elif cn:
    start_time = datetime(now.year, int(cn.group(1)), int(cn.group(2)), ...).isoformat()  # 第71行
elif short_dot:
    candidate = datetime(now.year, int(short_dot.group(1)), int(short_dot.group(2)), ...)  # 第73行
```

当文本/MiniMax 返回非法日期（如 "2月30日"、"11月31日"、"2026-02-30"、"13月1日"）时，`datetime()` 直接抛 `ValueError`，异常冒泡到 crawl_task，导致整个笔记处理失败。

**证据**：
- DB TaskLog task_id=24 记录：`笔记处理失败 [https://...6a72d842000000002500a1de]：day is out of range for month`
- 复现脚本：`extract_activity_fields("2月30日", now, None)` 直接抛 `ValueError: day is out of range for month`

**对比**：同文件 `normalize_activity_datetime`（第 22-45 行）已正确包 try/except，非法日期返回 None。`extract_activity_fields` 缺同样保护。

## 3. 修复方案

在 `extract_activity_fields` 的三个 `datetime()` 构造处加 try/except，非法日期时 `start_time = None`，让后续 `normalize_activity_row` 正常处理（start_time 为 None 不影响其他字段提取）。

## 4. 验收

- [x] 新增测试覆盖非法日期（2月30日、11月31日、2026-02-30、13月1日等）不抛异常，返回 start_time=None
- [x] 原有合法日期提取行为不变
- [x] 后端全量测试通过（597 passed, 1 skipped，+13 新），无回归

## 5. 部署

改动 `app/services/extraction.py`，**worker 必须重启**才能让修复在抓取流程中生效。uvicorn `--reload` 对 API 层无影响（此文件仅在 celery worker 内调用）。
