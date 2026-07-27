# 测试用例：安全（路径 / 越权 / 凭据 / 资源控制）

维度：安全（后端 + 跨层）。

## 目标

覆盖项目跨层安全约束（除鉴权之外的"安全维度"），不重复 [test-auth-api.md](file:///Users/kevin_w/Documents/github/xhs-info-crawl/tests/test-auth-api.md) 与 [test-test-jwt-secret.md](file:///Users/kevin_w/Documents/github/xhs-info-crawl/tests/test-test-jwt-secret.md)：

- 存储路径穿越（图片 / 报告）
- OpenCLI 进程执行栅栏（PID 注册 + execution fence + 优雅清理）
- 抓取任务执行权（`run_token` + PENDING 原子领取，避免重复投递与陈旧消息执行）
- Celery broker 在测试环境强制隔离，禁用共享 broker
- 抓取频率 / 搜索间隔防止平台风控
- 凭据永不入库：`OPENCLI_CDP_ENDPOINT` 仅内存读取，cookie 不写日志
- 上传尺寸 / MIME 类型 / 行数限制防止 OOM 与脏数据
- 越权：editor 用户访问 admin-only 接口返回 403
- 周报下载 URL 鉴权（无 token 拒绝）

## 可执行测试锚点

- 路径穿越：[backend/tests/test_local_storage.py](file:///Users/kevin_w/Documents/github/xhs-info-crawl/backend/tests/test_local_storage.py)
- 执行栅栏：[backend/tests/test_opencli_execution_fence.py](file:///Users/kevin_w/Documents/github/xhs-info-crawl/backend/tests/test_opencli_execution_fence.py)
- 抓取执行权：[backend/tests/test_crawl_execution_safe_stop.py](file:///Users/kevin_w/Documents/github/xhs-info-crawl/backend/tests/test_crawl_execution_safe_stop.py)
- 抓取 stop：[backend/tests/test_task_stop_immediate.py](file:///Users/kevin_w/Documents/github/xhs-info-crawl/backend/tests/test_task_stop_immediate.py)
- PID 注册表：[backend/tests/test_task_registry.py](file:///Users/kevin_w/Documents/github/xhs-info-crawl/backend/tests/test_task_registry.py)
- 浏览器启动器：[backend/tests/test_browser_launcher.py](file:///Users/kevin_w/Documents/github/xhs-info-crawl/backend/tests/test_browser_launcher.py)
- Celery broker 隔离：[backend/tests/test_test_environment_isolation.py](file:///Users/kevin_w/Documents/github/xhs-info-crawl/backend/tests/test_test_environment_isolation.py)
- 验证码暂停：[backend/tests/test_xhs_verification_pause.py](file:///Users/kevin_w/Documents/github/xhs-info-crawl/backend/tests/test_xhs_verification_pause.py) + [tests/test-xhs-verification-pause.md](file:///Users/kevin_w/Documents/github/xhs-info-crawl/tests/test-xhs-verification-pause.md)
- 抓取频率：[backend/tests/test_pipeline_services.py](file:///Users/kevin_w/Documents/github/xhs-info-crawl/backend/tests/test_pipeline_services.py) 内 `crawler_filters_recent_notes_and_maps_typed_errors` + `recent_search` 系列
- 上传大小/类型：[backend/tests/test_blogger_batch_import.py](file:///Users/kevin_w/Documents/github/xhs-info-crawl/backend/tests/test_blogger_batch_import.py)、[backend/tests/test_poster_template_api.py](file:///Users/kevin_w/Documents/github/xhs-info-crawl/backend/tests/test_poster_template_api.py)
- 越权：[backend/tests/test_auth_api.py](file:///Users/kevin_w/Documents/github/xhs-info-crawl/backend/tests/test_auth_api.py) 内 `test_role_enforced` 等
- 周报下载鉴权：[backend/tests/test_reports.py](file:///Users/kevin_w/Documents/github/xhs-info-crawl/backend/tests/test_reports.py) 内 `test_download_requires_auth`
- 凭据不入库：[backend/tests/test_config.py](file:///Users/kevin_w/Documents/github/xhs-info-crawl/backend/tests/test_config.py)（`SECRET_KEY` / `MINIMAX_API_KEY` 应来自 env）

## 用例编号

| ID | 场景 | 期望 | 锚点 |
|---|---|---|---|
| TC-SEC-001 | `local_storage.save(relative_key='../../etc/passwd')` | 拒绝 / 路径规范化到 `data/images/` | `test_local_storage.py::test_local_storage_rejects_path_traversal` |
| TC-SEC-002 | OpenCLI `search` 进程未注册到任务 PID | 拒绝执行 | `test_opencli_execution_fence.py::test_guard_failure_before_popen_starts_no_process` |
| TC-SEC-003 | OpenCLI 子进程运行中 `STOP_REQUESTED` | 立即 SIGKILL + 写日志 | `test_opencli_execution_fence.py` + `test_task_stop_immediate.py` |
| TC-SEC-004 | OpenCLI 子进程退出后写入后才遇到错误 | fence 错误优先于 killed return code | `test_opencli_execution_fence.py::test_guard_failure_after_process_exit_wins_over_killed_return_code` |
| TC-SEC-005 | `search` 中途被 stop，关闭 CDP session tab | session 被关闭 | `test_search_closes_session_tab_when_middle_command_stops` |
| TC-SEC-006 | 验证信号时保留 session tab | 不关闭 | `test_search_keeps_session_tab_open_when_verification_is_required` |
| TC-SEC-007 | 旧任务 stop 后新 PENDING 消息不能继续写入 | 状态机拒绝 | `test_crawl_execution_safe_stop.py` |
| TC-SEC-008 | `run_token` 不一致 | 拒绝继续 | 同上 |
| TC-SEC-009 | Celery 测试 broker = `memory://` | 本地 broker 不被消费 | `test_test_environment_isolation.py::test_pytest_uses_an_in_memory_celery_broker` |
| TC-SEC-010 | OpenCLI 77 验证码 | 任务 PAUSED + 提示人工 | `test_xhs_verification_pause.py` |
| TC-SEC-011 | OpenCLI 60 秒普通超时 | **不**误判为验证码 | `test_pipeline_services.py` 验证分类器 |
| TC-SEC-012 | 关键词搜索间隔（10-15s） | sleep 落入区间 | `test_pipeline_services.py::test_crawler_filters_recent_notes_and_maps_typed_errors` |
| TC-SEC-013 | 单账号每周搜索 ≤ 500 | 触发后降速 / 暂停 | `test_pipeline_services.py` 频率控制 |
| TC-SEC-014 | 上传 xlsx > 2 MiB | 422 | `test_blogger_batch_import.py` |
| TC-SEC-015 | 上传 xlsx > 500 行 | 422 | 同上 |
| TC-SEC-016 | 上传 MIME 非图像 | 422 | `test_poster_template_api.py::test_parse_from_image_non_image_content_type_rejected` |
| TC-SEC-017 | editor 调 admin-only 接口 | 403 | `test_auth_api.py::test_role_enforced` |
| TC-SEC-018 | 周报下载未携带 token | 401 | `test_reports.py::test_download_requires_auth` |
| TC-SEC-019 | 周报下载 token 篡改 | 401 | 同上 |
| TC-SEC-020 | 日志中无 cookie 明文 | 结构化校验 | OpenCLI adapter 输出断言 |
| TC-SEC-021 | `SECRET_KEY` 不存在 | pytest 注入测试密钥；运行时强制 env | `test_test_jwt_secret.py` |
| TC-SEC-022 | `MINIMAX_API_KEY` 未设 | 接口降级 / 503 | `test_minimax.py` + `test_poster_template_api.py::test_parse_from_image_without_api_key_returns_503` |
| TC-SEC-023 | 路径写入失败的图像对象 | 不抛 500，返回占位 + 状态码 | `test_local_storage.py` |

## 验收

- `uv run --project backend pytest backend/tests/test_local_storage.py backend/tests/test_opencli_execution_fence.py backend/tests/test_crawl_execution_safe_stop.py backend/tests/test_task_stop_immediate.py backend/tests/test_task_registry.py backend/tests/test_browser_launcher.py backend/tests/test_test_environment_isolation.py backend/tests/test_pipeline_services.py backend/tests/test_blogger_batch_import.py backend/tests/test_poster_template_api.py backend/tests/test_auth_api.py backend/tests/test_reports.py backend/tests/test_config.py backend/tests/test_xhs_verification_pause.py -q` 全绿。
- 不与 [tests/test-crawl-execution-safe-stop.md](file:///Users/kevin_w/Documents/github/xhs-info-crawl/tests/test-crawl-execution-safe-stop.md)（业务视角的 stop 验收）、[tests/test-celery-test-isolation.md](file:///Users/kevin_w/Documents/github/xhs-info-crawl/tests/test-celery-test-isolation.md)（Celery 隔离专项）、[tests/test-stop-execution-fence-browser-cleanup.md](file:///Users/kevin_w/Documents/github/xhs-info-crawl/tests/test-stop-execution-fence-browser-cleanup.md)（栅栏+浏览器清理专项）、[tests/test-xhs-verification-pause.md](file:///Users/kevin_w/Documents/github/xhs-info-crawl/tests/test-xhs-verification-pause.md)（验证码暂停业务）、[tests/test-test-jwt-secret.md](file:///Users/kevin_w/Documents/github/xhs-info-crawl/tests/test-test-jwt-secret.md)（测试密钥专项）重复叙述，仅作为指向锚点。
