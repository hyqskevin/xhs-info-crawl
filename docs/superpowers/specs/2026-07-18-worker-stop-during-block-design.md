# Worker 在 opencli 阻塞时响应停止信号

## 问题描述

当 celery worker 执行 opencli 命令时（如 `note`、`download`），如果小红书触发验证弹窗，CDP 命令会超时（115秒）。在这期间 worker 进程被完全阻塞，无法响应 STOP_REQUESTED 状态。即使 stop 接口调用了 `task_registry.kill()` 终止子进程，worker 仍在等待 subprocess 完成，导致任务无法及时停止。

## 解决方案

1. **缩短 opencli 命令超时时间**：从 120 秒改为 30 秒
2. **在超时后检查任务状态**：如果任务已被标记为 STOP_REQUESTED，立即退出当前任务
3. **增加子进程超时检查**：在等待 subprocess 完成时，定期检查任务状态

## 设计

### 1. 修改 OpenCLIAdapter

在 `OpenCLIAdapter.run()` 方法中，设置较短的超时时间，并在超时后检查任务状态。

### 2. 修改 crawl_task

在每个关键步骤（搜索、下载、处理笔记）前后检查任务状态，如果是 STOP_REQUESTED 则立即退出。

### 3. 修改 task_registry

增加一个方法来检查任务是否被停止，供 worker 在执行期间调用。

## 验收条件

1. 点击停止后，worker 在 10 秒内检测到停止信号并退出当前任务
2. 不再需要手动 kill worker 进程
3. 测试用例验证超时场景下的停止行为

## 相关文件

- `backend/app/services/opencli_adapter.py`
- `backend/app/tasks/crawl_task.py`
- `backend/app/services/task_registry.py`