# 抓取流水线并行加速 — 设计

**日期**: 2026-08-10
**关联**: 用户反馈"如何加快抓取进度"，确认两个优化方向

## 1. 背景

当前单篇笔记流水线：
```
下载图片 (10-30秒) → OCR 多张图片 (5-30秒，串行) → MiniMax API (30-90秒) → 写DB
```

任务24实测：4 博主 × 15 篇候选 → `recent_filter=一周内` 过滤后 28 篇，37 分钟完成，约 **1.3 分钟/篇**。

瓶颈分析：
- **OCR 串行**：18 张图片逐张识别，累计 10-30 秒
- **MiniMax 串行**：每篇 30-90 秒，占 60-70% 时间

## 2. 设计

### 2.1 笔记内图片并行 OCR

**现状**：[crawl_task.py:298-316](file:///Users/hanamaki_mac_mini/Documents/github/project/xhs-info-crawl/backend/app/tasks/crawl_task.py#L298-L316) for 循环逐张 OCR：

```python
for index, image in enumerate(images, 1):
    result = run_stage(recognize, attempts, delay)
    image_row = NoteImage(...)
    db.add(image_row)
```

**改为**：用 `ThreadPoolExecutor` 并行调用同一 PaddleOCR 单例。

**验证结果**（2026-08-10 实测）：
- PaddleOCR 单例 `predict` 方法线程安全（4 线程并发无异常）
- 4 张图：串行 31 秒 → 并行 19.3 秒，加速 1.61x
- 不占用网络带宽（本地模型），占用 CPU

**配置**：
- `Settings` 新增 `ocr_parallel_workers: int = 2`（默认 2，最高 4）
- 在配置中心「系统配置」tab 可视化调整

**实现要点**：
- 用 `concurrent.futures.ThreadPoolExecutor(max_workers=settings.ocr_parallel_workers)`
- 每张图片的 OCR 仍走 `run_stage` 重试逻辑（但重试在子线程内）
- `assert_execution_active` 检查放在提交任务前
- 结果按图片顺序收集（用 `as_completed` + index 映射）
- DB 写入仍在主线程（SQLite 线程安全需要 `check_same_thread=False`，已配置）

### 2.2 MiniMax 可配置并发调用

**现状**：[crawl_task.py:328](file:///Users/hanamaki_mac_mini/Documents/github/project/xhs-info-crawl/backend/app/tasks/crawl_task.py#L328) 单篇笔记调用一次 MiniMax，串行。

**改为**：**多篇笔记的 MiniMax 调用并行**，不是单篇内并行。

**设计**：
- 在博主笔记循环中，收集已 OCR 完成的笔记，用 `ThreadPoolExecutor` 并行调用 MiniMax
- 并发数可配置，默认 1（向后兼容），最高 4

**但这里有个复杂点**：当前流水线是"下载→OCR→提取"逐篇串行。要并行 MiniMax，需要重构为：
1. 阶段 1：下载 + OCR 所有笔记（仍串行，或部分并行）
2. 阶段 2：MiniMax 批量并行提取

**简化方案**：保持逐篇流水线不变，但 MiniMax 调用用独立线程池异步执行：
- 主线程：下载 → OCR → 提交 MiniMax 任务到线程池 → 继续下一篇
- 线程池：并行执行 MiniMax 调用，结果回写 DB

**风险评估**：
- MiniMax 已出现 529 限流（11:36 日志），并行会加剧
- 需要确保 `MiniMaxClient` 线程安全（`httpx.Client` 是线程安全的）
- 需要 529 限流重试机制（已有 `run_stage` 重试，但并行时多个请求同时重试可能雪崩）

**最终方案**（平衡复杂度与收益）：
- `Settings` 新增 `minimax_concurrency: int = 1`（默认 1，最高 4）
- 当 `minimax_concurrency > 1` 时，MiniMax 调用走 `ThreadPoolExecutor`
- 每个线程独立 `httpx.Client`（避免共享状态的潜在问题）
- 529 限流时指数退避重试（已有 `run_stage` 逻辑）

**实现**：
- `MiniMaxClient` 新增 `extract_many_parallel(texts: list[str], reference_now, started_at) -> list[dict]`
- 内部用 `ThreadPoolExecutor(max_workers=settings.minimax_concurrency)`
- `crawl_task.py` 收集多篇 OCR 结果后批量调用

**但**：这会大幅改变 crawl_task 流程。**更简单的方案**：

**方案 C（推荐）**：保持逐篇流水线，MiniMax 调用本身不变，但 `MiniMaxClient.extract_activities` 内部如果需要多次调用（`extract_many`），用线程池并行。

看 [minimax.py](file:///Users/hanamaki_mac_mini/Documents/github/project/xhs-info-crawl/backend/app/services/minimax.py) 的 `extract_many` 是已有的多次调用方法。把它改成并行即可。

## 3. 配置项

| 配置项 | 默认值 | 范围 | 用途 |
|---|---|---|---|
| `OCR_PARALLEL_WORKERS` | 2 | 1-4 | 笔记内图片并行 OCR 线程数 |
| `MINIMAX_CONCURRENCY` | 1 | 1-4 | MiniMax API 并发调用数 |

## 4. 验收

- [x] `Settings` 有 `ocr_parallel_workers` 和 `minimax_concurrency` 字段
- [x] 图片 OCR 并行执行（ThreadPoolExecutor）
- [x] MiniMax `extract_many_parallel` 并行执行（当 concurrency > 1）
- [x] 配置中心「系统配置」tab 可调整两个参数
- [x] `.env.example` 新增两个配置项
- [x] 后端全量测试通过（584 passed, 1 skipped，+11 新）
- [x] 新增测试：并行 OCR 结果正确、MiniMax 并发调用正确
- [ ] 实测：单篇处理时间下降（需用户重启 worker 后实测）

## 6. 实现说明

### MiniMax 并行 crawl_task 集成

`extract_many_parallel` 方法已实现并测试通过，但 crawl_task 中暂未集成批量并行调用（保持逐篇 `extract_many` 调用）。原因：
- 当前流程是"逐篇下载→OCR→MiniMax→写DB"，MiniMax 批量并行需要重构为两阶段流水线
- 默认 `minimax_concurrency=1`（串行），不影响现有行为
- OCR 并行已集成（主要加速点），MiniMax 并行方法就绪可供后续集成

当用户需要 MiniMax 并行时，可后续重构 crawl_task 为"批量下载+OCR → 批量并行 MiniMax → 写DB"。

## 5. 测试计划

### 单元测试（先红后绿）

1. `test_settings_has_ocr_parallel_workers` — Settings 有 `ocr_parallel_workers` 字段，默认 2
2. `test_settings_has_minimax_concurrency` — Settings 有 `minimax_concurrency` 字段，默认 1
3. `test_ocr_parallel_workers_bounds` — 值限制在 1-4
4. `test_minimax_concurrency_bounds` — 值限制在 1-4
5. `test_ocr_processes_images_in_parallel` — 验证图片 OCR 用 ThreadPoolExecutor（mock 验证并发调用）
6. `test_minimax_extract_many_parallel_when_concurrency_gt_1` — 验证 concurrency>1 时并行调用
