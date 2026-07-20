# 停止执行栅栏与浏览器标签页清理测试案例

## 自动化测试

1. 运行 `cd backend && .venv/bin/pytest -q tests/test_opencli_execution_fence.py`。
2. 验证停止状态在 `Popen` 前出现时不创建进程。
3. 验证停止发生在 PID 登记后时，新进程被结束并回收。
4. 验证搜索和详情流程发生异常时都执行 crawler session 标签页清理。
5. 验证清理失败只写 WARNING，不覆盖任务停止状态。
6. 运行任务执行权测试，验证旧 `run_token` 和停止后的旧执行不能继续写入。
7. 验证子进程被外部结束后，退出后的执行检查优先于非零退出码。
8. 验证 stop API 在 kill 子进程前已提交 `STOP_REQUESTED`，并验证 `FAILED`、`PAUSED` 直接结束为 `STOPPED`。

## 真实浏览器验收

1. 保持本地 API、Celery worker、前端和已登录小红书的 Chrome 运行。
2. 从仪表盘发起一个至少包含多篇笔记的抓取任务。
3. 在搜索、滚动或详情处理阶段点击“停止抓取”，记录点击时间。
4. 验证 5 秒内日志不再出现新的业务 `open`、`eval`、`scroll`、`note` 或 `download` 操作。
5. 验证包含标签页清理时最迟 15 秒进入 `STOPPED`。
6. 验证 `/tmp/xhs_task_registry.json` 中没有该 `task_id + run_token`。
7. 验证 crawler session 打开的抓取标签页关闭，用户其他 Chrome 标签页和登录态仍保留。
8. 不重启 worker，发起第二条新任务并验证进入 `RUNNING`。
9. 验证第一条任务的进度、日志和数据不再变化。

## 验收记录

### 2026-07-20 本地真实验收

- 自动化：后端 `210 passed, 1 skipped`；前端组件 `28 passed`；Playwright E2E `38 passed`；`git diff --check` 通过。
- 环境：本地 API、前端、同一个 Celery solo worker、已登录的 Chrome。
- 任务 `#15`：仪表盘发起后在 `SEARCHING` 阶段立即点击安全停止；数据库时间为 `17:21:35.474` 开始、`17:21:35.728` 完成，约 `0.25s` 进入 `STOPPED`。
- 任务 `#15` 停止后：发现/下载/OCR/提取/失败均为 `0`，再次启动任务后这些字段保持不变；任务日志包含“任务已安全停止”，没有被改写为 `FAILED`。
- PID 注册表：停止后 `/tmp/xhs_task_registry.json` 的键列表为空。
- Chrome 标签页：crawler search/session 标签页不存在；原有“小红书创作服务平台”用户标签页仍保留，未读取 Cookie 或本地存储。
- worker 复用：没有重启 worker，任务 `#16` 被同一 worker 接收并进入 `RUNNING / SEARCHING`；随后通过仪表盘安全停止并进入 `STOPPED`。
- 结论：真实“启动 → 中途停止 → 同一 worker 再启动 → 再停止”通过。
