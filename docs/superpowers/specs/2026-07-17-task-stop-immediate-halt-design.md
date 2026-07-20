# 点击"停止抓取"立即停当前任务（2026-07-17）

## 背景

现状：用户在仪表盘点击"停止抓取"后：
1. 后端把任务状态从 `RUNNING` 改为 `STOP_REQUESTED`
2. worker 进程**不知道这个状态变化**，继续跑当前 `xiaohongshu note` 命令（每个 note ~30s）
3. 当前 note 跑完后，下次 `finish_stop_if_requested` 才把状态置为 `STOPPED`
4. **worker 继续把队列里剩下的 note 全部跑完**，每个 note 都失败，任务日志全是 ERROR

证据：任务 #7 13:38 启动 → 13:40:42 用户点停止 → **worker 继续跑到 13:44:49**，又处理了 5+ 个 note 全失败。

## 目标

点击"停止抓取"后：
- **当前正在执行的 opencli 子进程被立即终止**（SIGTERM/SIGKILL）
- **worker 进程退出当前 celery 任务**（raise `Ignore` 或 `Reject`）
- **任务状态立即变为 `STOPPED`**（不是 `STOP_REQUESTED` 等待下次循环检测）
- **worker 进程本身不退出**——其他任务仍可继续接收（避免杀 worker 全局副作用）

## 设计

### 方案对比

| 方案 | 优点 | 缺点 |
|---|---|---|
| **Celery `revoke(task_id, terminate=True, signal='SIGTERM')`** | Celery 内置；自动找到 worker 子进程 | filesystem broker 不支持 revoke；需换 broker |
| **手动维护子进程 PID 映射** | 兼容 filesystem broker | 实现复杂；PID 错乱风险 |
| **每篇 note 前检查 STOP_REQUESTED** | 简单 | 当前 note 仍会跑完（无立即停） |
| **Async subprocess + 信号** | 兼容性好 | 需改适配器 |

### 推荐方案：手动维护运行任务 PID 映射

#### 数据流

```
用户: POST /tasks/{id}/stop
    ↓
后端: 1. 设 status=STOP_REQUESTED 写日志
      2. 找任务对应的 worker 子进程 PID
      3. 发送 SIGTERM 给子进程（最多等 5s）
      4. SIGKILL 兜底
      5. 把 status 立即改为 STOPPED
    ↓
worker: subprocess.run() 因 signal 退出 → 抛异常 → 外层 try/except 把 status 置为 STOPPED
```

#### 实现细节

1. **新增全局任务 PID 映射**（`backend/app/services/task_registry.py`）：
   ```python
   _running: dict[int, dict] = {}  # task_id -> {"pid": int, "started_at": datetime}

   def register(task_id: int, pid: int) -> None: ...
   def unregister(task_id: int) -> None: ...
   def get(task_id: int) -> dict | None: ...
   ```

2. **worker 端 `run_crawl` 改动**：
   - 在跑 `subprocess.run(...)` 之前，把 `proc.pid` 注册到 `task_registry`
   - 异常/退出时反注册
   - 注意：`subprocess.run` 是同步阻塞的，要换 `subprocess.Popen` + `proc.wait()`

3. **后端 stop API 改动**：
   ```python
   def stop(task_id):
       # 原有：设 STOP_REQUESTED
       # 新增：
       proc_info = task_registry.get(task_id)
       if proc_info:
           pid = proc_info["pid"]
           os.kill(pid, signal.SIGTERM)
           # 等最多 5s
           for _ in range(50):
               if not psutil.pid_exists(pid):
                   break
               time.sleep(0.1)
           else:
               os.kill(pid, signal.SIGKILL)
       # 立即设 status=STOPPED
   ```

4. **进程替换为 Popen**：
   ```python
   # 原：
   result = subprocess.run(cmd, ...)
   # 新：
   proc = subprocess.Popen(cmd, ...)
   task_registry.register(task_id, proc.pid)
   try:
       proc.wait(timeout=120)
   finally:
       task_registry.unregister(task_id)
   ```

5. **优雅处理**：worker `run_crawl` 任务捕获 `subprocess.TimeoutExpired` 或信号导致的异常 → DB 状态写 `STOPPED`，不写 `FAILED`。

### 风险

- **filesystem broker 不支持 Celery revoke**——所以不能依赖 Celery 内置 revoke
- **PID 重复利用**：kill 之前要确认 pid 仍属于这个任务（用 `started_at` + `cmdline`）
- **跨进程通信**：后端 FastAPI 进程和 worker Celery 进程需要共享 `task_registry`——用 **SQLite** 或 **共享文件**（`/tmp/xhs_task_registry.json`）

### 简化方案：共享文件

```python
# backend/app/services/task_registry.py
import json, fcntl, os, time
from pathlib import Path

REGISTRY_PATH = Path("/tmp/xhs_task_registry.json")

def register(task_id: int, pid: int) -> None:
    with file_lock(REGISTRY_PATH):
        data = _read()
        data[str(task_id)] = {"pid": pid, "registered_at": time.time()}
        _write(data)

def get(task_id: int) -> dict | None:
    with file_lock(REGISTRY_PATH):
        return _read().get(str(task_id))

def unregister(task_id: int) -> None:
    with file_lock(REGISTRY_PATH):
        data = _read()
        data.pop(str(task_id), None)
        _write(data)
```

`file_lock` 用 `fcntl.flock` 防止并发写。

## 验收

### 自动化测试

- `backend/tests/test_task_registry.py`：
  - `test_register_and_get`：register task 1 后能 get 到 pid
  - `test_unregister`：unregister 后 get 返回 None
  - `test_concurrent_register`：两个进程同时 register 不互相覆盖
- `backend/tests/test_task_stop_immediate.py`：
  - `test_stop_sends_sigterm_to_child_process`：mock subprocess.Popen，启动爬虫→查 PID→调用 stop→验证 PID 被 kill
  - `test_stop_handles_already_finished`：任务已完成时 stop 不报错
  - `test_stop_writes_stopped_status_immediately`：调用 stop 后 DB 立即是 STOPPED

### 手动 E2E

1. 提交一个耗时任务（≥5 个 note）
2. 在第 1 个 note 跑期间点"停止抓取"
3. 5 秒内任务状态变 STOPPED
4. 任务日志只有 0~1 条 ERROR，剩余 note 不再尝试
5. worker 进程仍在（不退出）
6. worker 能正常接收新任务

## 任务

1. 创建 `backend/app/services/task_registry.py`
2. 改 `backend/app/services/opencli_adapter.py`：subprocess.run → subprocess.Popen，注册到 registry
3. 改 `backend/app/api/v1/tasks.py`：stop 接口 kill 子进程
4. 改 `backend/app/tasks/crawl_task.py`：状态判断适配
5. 写测试
6. 更新 `docs/api-doc.md`（stop 端点说明行为）
7. 更新 `docs/TODO.md`

## TODO

`docs/TODO.md` "当前待办"区追加：

```
- [ ] 点击"停止抓取"立即停当前任务
  - 目标：解决 worker 跑 STOPPED 任务后还在继续跑剩余 note 的问题。
  - 验收：见 `docs/superpowers/specs/2026-07-17-task-stop-immediate-halt-design.md`（待审）。
```