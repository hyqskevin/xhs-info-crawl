# Celery 测试隔离验收

## 自动化案例

1. pytest 导入应用后，断言 Celery broker 为 `memory://`。
2. 未显式声明的 `run_crawl.delay` 调用必须使测试失败。
3. 创建和重启抓取任务的测试显式捕获 `(task_id, run_token)`，并断言只投递一次。
4. 执行后端全量测试，确认不会启动真实 OpenCLI、Chrome 或写入本地 filesystem broker。

## 通过标准

- `backend/tests/test_test_environment_isolation.py` 通过；
- 后端全量测试通过；
- 本地运行数据库的历史任务不会因测试被重新执行。
