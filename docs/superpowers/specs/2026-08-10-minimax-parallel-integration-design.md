# MiniMax 批量并行集成到 crawl_task

## 1. 背景

`MiniMaxClient.extract_many_parallel` 方法已实现并测试通过（默认 `minimax_concurrency=1` 串行，最高 4 并行），但 `crawl_task.py` 仍保持逐篇 `extract_many` 调用。需把"逐篇下载→OCR→MiniMax→写DB"重构为"批量下载+OCR → 批量并行 MiniMax → 写DB"两阶段流水线。

## 2. 目标

让 MiniMax 真正并行起来，降低多篇笔记的总处理时间。

## 3. 设计

### 3.1 当前架构（逐篇串行）

```
for entry in results:
    process_note(entry):
        1. 下载笔记详情 + 图片
        2. OCR 每张图片（已并行，OCR_PARALLEL_WORKERS）
        3. MiniMax extract_many（单篇，串行）
        4. 写 DB（Note + NoteImage + Activity）
```

### 3.2 目标架构（两阶段流水线）

```
阶段 1：逐篇下载 + OCR（保持串行，因 opencli 不支持并发）
    for entry in results:
        下载笔记 + 图片
        OCR 图片（已并行）
        暂存 (note, combined_text, reference_now) 到内存列表

阶段 2：批量并行 MiniMax + 写 DB
    texts = [item.combined_text for item in staged]
    results = client.extract_many_parallel(texts, reference)
    for item, extracted in zip(staged, results):
        写 DB（Activity + 更新 Note 状态）
```

### 3.3 实现方案

**crawl_task.py 改造**：

1. 把 `process_note` 拆为两个函数：
   - `download_and_ocr(db, task, run_token, city, item, adapter, settings) -> StagedNote | None`
     - 下载笔记详情 + 图片
     - OCR 图片
     - 返回 `StagedNote(note, combined_text, reference_now, image_rows)`
     - 失败/跳过时返回 None
   - `extract_and_save(db, task, run_token, staged: StagedNote, extracted: dict, settings) -> None`
     - validate_activities + classify_zero_activity
     - 写 Activity + 更新 Note 状态

2. `run_crawl` 主循环改为两阶段：
```python
# 阶段 1：逐篇下载 + OCR
staged_notes: list[StagedNote] = []
for entry in results:
    if finish_stop_if_requested(...): return
    try:
        staged = download_and_ocr(db, task, run_token, entry[0], entry[1], adapter, settings)
        if staged:
            staged_notes.append(staged)
        consecutive_failures = 0
    except Exception as exc:
        on_failure(entry, exc)
        # ... 熔断逻辑

# 阶段 2：批量并行 MiniMax + 写 DB
if staged_notes and settings.minimax_api_key:
    client = MiniMaxClient(settings)
    texts = [s.combined_text for s in staged_notes]
    references = [s.reference_now for s in staged_notes]
    # extract_many_parallel 用单一 reference（取第一个），或逐篇调
    # 简化：用第一个 staged 的 reference 作为批量 reference
    extracted_list = run_stage(
        lambda: client.extract_many_parallel(texts, staged_notes[0].reference_now),
        attempts, delay
    )
    for staged, extracted in zip(staged_notes, extracted_list):
        extract_and_save(db, task, run_token, staged, extracted, settings)
else:
    # 无 API key 或无 staged，降级逐篇规则提取
    for staged in staged_notes:
        extracted = extract_activities(staged.combined_text, staged.reference_now, None)
        extract_and_save(db, task, run_token, staged, extracted, settings)
```

3. 新增 `StagedNote` dataclass：
```python
@dataclass
class StagedNote:
    note: Note
    combined_text: str
    reference_now: datetime
    started_at: datetime
```

### 3.4 兼容性

- `minimax_concurrency=1` 时 `extract_many_parallel` 退化为串行，行为与当前一致
- 无 `minimax_api_key` 时降级规则提取，行为不变
- 失败熔断逻辑在阶段 1 保持不变
- `finish_stop_if_requested` 在两个阶段都检查

### 3.5 风险与缓解

- **内存占用**：staged_notes 暂存所有笔记的 combined_text，但单批最多 4 博主 × 10 篇 = 40 篇，文本量可控
- **MiniMax 529 限流**：`extract_many_parallel` 并发数最高 4，`run_stage` 指数退避重试
- **部分失败**：某篇 MiniMax 失败时，`extract_many_parallel` 整体抛异常，`run_stage` 重试；重试耗尽后降级规则提取

## 4. 验收

- [ ] `process_note` 拆为 `download_and_ocr` + `extract_and_save`
- [ ] `run_crawl` 主循环改为两阶段
- [ ] `minimax_concurrency=1` 时行为与当前一致（串行）
- [ ] `minimax_concurrency>1` 时 MiniMax 并行调用
- [ ] 无 API key 时降级规则提取
- [ ] 失败熔断逻辑保持不变
- [ ] TDD 测试覆盖两阶段流水线
- [ ] 后端全量测试通过
- [ ] **worker 重启后实测**单篇处理时间下降

## 5. 部署

- **worker 必须重启**（改动 `app/tasks/crawl_task.py`）
- 无 migration
- 无前端改动
