# 点击开始抓取时自动停止上一个任务

## 目标

用户点击"开始抓取"时，如果有正在运行的任务，系统自动停止上一个任务并启动新任务，而非报错 `TASK_IN_PROGRESS`。

## 问题分析

当前 `POST /api/v1/tasks/crawl` 接口在检测到有运行中任务时直接返回 `409 TASK_IN_PROGRESS`，用户必须手动先停止上一个任务才能开始新任务。这导致：
1. 用户体验不佳，需要多一步操作
2. 操作流程不直观

## 设计

### 接口行为变更

修改 `POST /api/v1/tasks/crawl` 接口：

1. **检测到运行中任务时**：
   - 调用 `task_registry.kill(running.id)` 立即终止上一个任务的子进程
   - 根据上一个任务的当前状态设置新状态：
     - `PENDING` → `STOPPED`（立即终止）
     - `RUNNING` / `FAILED` / `PAUSED` → `STOP_REQUESTED`（等待 worker 检测）
   - 添加任务日志："被新任务顶替停止（子进程已 kill={pid_killed}）"
   - 提交数据库事务

2. **创建并启动新任务**：
   - 继续原有逻辑创建新任务
   - 返回新任务信息

### 状态机

```
原任务：RUNNING → STOP_REQUESTED → STOPPED（worker 检测后）
新任务：PENDING → RUNNING
```

### 验收条件

1. **API 层面**：
   - 当有 `RUNNING` 任务时，调用 `POST /api/v1/tasks/crawl` 返回 202，而非 409
   - 原任务状态变为 `STOP_REQUESTED`
   - 新任务状态为 `PENDING`（等待 worker 消费）

2. **日志层面**：
   - 原任务有日志：`被新任务顶替停止（子进程已 kill=True）`
   - 新任务有日志：`login check`

3. **worker 层面**：
   - 原任务的子进程被终止（PID 在 task_registry 中被 kill）
   - 原任务 worker 检测到 `STOP_REQUESTED` 后安全退出
   - 新任务被 worker 正常消费

## 测试

### 单元测试

```python
def test_crawl_auto_stops_previous_running_task(db):
    """测试有 RUNNING 任务时，crawl 接口自动停止上一个任务"""
    # 前置：创建一个 RUNNING 状态的任务
    task = CrawlTask(...)
    task.status = "RUNNING"
    db.add(task)
    db.commit()

    # 执行：调用 crawl 接口
    response = client.post("/api/v1/tasks/crawl", json={...})

    # 验证：返回 202，原任务状态变为 STOP_REQUESTED
    assert response.status_code == 202
    assert task.status == "STOP_REQUESTED"

    # 验证：创建了新任务
    new_task = db.scalar(select(CrawlTask).order_by(CrawlTask.id.desc()).limit(1))
    assert new_task.id != task.id
    assert new_task.status == "PENDING"
```

### E2E 测试

见 `tests/test-crawl-auto-stop-previous.md`

## 关联文档

- TODO：`docs/TODO.md` 第 28-30 行
- 实现：`backend/app/api/v1/tasks.py` `crawl` 函数
- 依赖：`backend/app/services/task_registry.py`
