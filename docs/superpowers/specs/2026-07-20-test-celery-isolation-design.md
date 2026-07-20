# 测试环境 Celery 队列隔离设计

> 状态：已审核并实现。

## 1. 目标

确保后端自动化测试只操作测试数据库和测试队列，任何测试都不能向本地运行环境的 filesystem broker 投递真实抓取任务，也不能让常驻 Celery worker 改写 `data/app.db`。

## 2. 已确认的根因

测试数据库虽然由测试夹具隔离，但 Celery broker 配置在应用导入时仍可能指向本地 filesystem broker。部分 `/tasks/crawl` 成功路径测试没有 mock `run_crawl.delay`，因此测试返回 202 的同时把任务 ID 写进真实队列。

本地常驻 worker 会消费这些消息，并按照相同数字 ID 在生产数据库中找到历史任务。当前 worker 又没有严格限制任务只能从 `PENDING` 领取，因此历史任务会被重新执行，造成状态、时间和日志被覆盖。

本次排查确认的高风险测试包括：

- `backend/tests/test_crawl_auto_stop_previous.py` 中的成功提交场景；
- `backend/tests/test_tasks_api_scope.py` 中未声明 mock 的成功提交场景；
- 后续任何新增但忘记 mock `run_crawl.delay` 的 API 测试。

## 3. 设计

### 3.1 双重隔离

采用“独立测试 broker + 默认禁止真实投递”两道保护：

1. 在任何应用模块导入前，为 pytest 设置测试专用 Celery 配置，不读取本地 `.env` 中的 filesystem broker 路径；
2. 增加自动使用的 pytest 夹具，默认将 `run_crawl.delay` 替换为会明确报错的测试替身；
3. 需要验证队列投递的测试必须显式覆盖该替身，记录投递参数并断言；
4. 只测试参数校验、状态码或数据库写入的用例不允许产生 Celery 消息。

默认替身选择“未声明投递即失败”，而不是静默 no-op，避免未来新增测试再次漏掉隔离。

### 3.2 配置加载时序

测试配置必须在 `app.main`、`app.tasks.celery_app` 和 Settings 单例首次导入前生效。测试结束后不得修改或清理本地实际 broker 目录。

### 3.3 与任务执行权修复的关系

本 spec 解决“测试不应投递真实消息”；任务执行权 spec 另行解决“即使出现重复或陈旧消息，worker 也不能重跑历史任务”。两者必须同时完成，不能只依赖其中一道保护。

## 4. TDD 范围

先补失败测试，再修改测试基础设施：

- 未显式 mock 的 `/tasks/crawl` 成功测试触发 `delay` 时必须失败；
- 显式 mock 后能够断言只投递一次且 task ID 正确；
- 运行任务 API 测试前后，测试专用 broker 无残留消息；
- 以只读快照验证本地 broker 目录和 `data/app.db` 的目标任务日志没有变化；
- 后端全量测试不能启动 OpenCLI、Chrome、真实 worker 或网络请求。

## 5. 验收标准

- 后端全量测试通过；
- 所有成功创建/重启抓取任务的测试均显式声明投递行为；
- 测试执行前后本地 filesystem broker 文件数量和修改时间不变；
- 测试执行前后生产数据库中的任务状态、进度、时间和日志不变；
- 测试进程退出后不存在测试启动的 Celery worker 或 OpenCLI 子进程；
- 对应测试案例补充到 `tests/` 下的 Markdown 文档。

## 6. 不在本次范围

- 不迁移 Redis；
- 不改变一期本地 filesystem broker 的正常运行方式；
- 不处理任务安全停止和重复消息领取，后者由独立 spec 负责。
