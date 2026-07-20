# TODO

本文件是项目待办事项的唯一维护入口。新增需求、后续优化和技术债统一记录在这里；风险及应对措施见 [`risks-todos.md`](risks-todos.md)。

## 使用约定

- 使用 `- [ ]` 表示未完成，使用 `- [x]` 表示已完成。
- 新增事项应写明目标和验收条件，必要时补充关联文档或代码位置。
- 完成后移入"已完成"章节，不直接删除，便于追踪。
- 阶段二事项统一放在"阶段二：全量技术栈"章节。

## 当前待办

- [ ] 写 spec 前先把问题解答清楚，spec 写完后必须过用户审核再开发（流程规则，永久保留）
- [ ] 一次性爬虫模式（生产场景启动一次爬虫 → 跑完 → worker 自动退出）
  - 目标：与 `docs/crawler-design.md` 第 168 行一致，"worker 完成当前单篇笔记... 然后写入 STOPPED 并退出"。
  - 验收：**待写 spec 过审后再列具体验收条件**。
- [ ] 跑任务 #7 重新抓取验证博主笔记 URL 不再缺 xsec_token
  - 目标：验证博主抓取修复后，note 命令能正常打开笔记详情。
  - 验收：选 nb + 博主 1 提交任务，日志 `博主 '从零发现宁波' 命中 N 篇（带 xsec_token 的）`；`downloaded > 0`；无 `xsec_token` 或 `Missing url` 错误。
- [ ] 验证点击"停止抓取"立即 kill 子进程（点一次停止后 5 秒内任务变 STOPPED）
  - 目标：spec 1 已实现；提交一个耗时任务测一下。
  - 验收：日志 `已结束抓取（状态置为 STOPPED, 子进程已 kill=True）`；5s 内任务状态 STOPPED；worker 进程不退。
- [x] 修复worker在opencli阻塞时无法响应停止信号的问题
  - 目标：celery worker在执行opencli调用时（CDP超时115秒），能够及时检测到STOP_REQUESTED状态并退出。
  - 验收：点击停止后，worker在10秒内检测到停止信号并退出当前任务；不再需要手动kill worker进程。
  - 实现：`backend/app/services/opencli_adapter.py` 缩短超时时间（60秒）；`backend/app/services/task_registry.py` kill方法立即发送SIGKILL。
  - 测试：`backend/tests/test_worker_stop_during_block.py` 4个全过。
- [ ] 支持批量上传博主白名单
- [ ] 识别到触发反爬时候，等我扫码或者验证码验证完，不要直接关掉页面
- [ ] 活动列表的摘要，是完整的推文，写推文的文字，是ocr识别出来的，要写ocr识别出的文字，有日期的带上日期
- [ ] 识别到小红书验证时，要停止爬虫，在仪表盘告知，然后打开页面等待扫码
- [x] 点击开始抓取时自动停止上一个任务（不报错 TASK_IN_PROGRESS）
  - 目标：用户点击"开始抓取"时，如果有正在运行的任务，自动停止上一个任务并启动新任务，而非报错。
  - 验收：见 spec `docs/superpowers/specs/2026-07-18-crawl-auto-stop-previous-design.md`。
  - 实现：`backend/app/api/v1/tasks.py` `crawl` 函数；检测到运行中任务时自动调用 `task_registry.kill()` 终止子进程。
  - 测试：`backend/tests/test_crawl_auto_stop_previous.py` 4 个全过。

## 后续优化

<!-- 在此追加产品优化、体验改进、稳定性增强等事项。建议格式如下：
- [ ] 优化项标题
  - 目标：说明要解决的问题。
  - 验收：说明如何判断已完成。
-->

## 阶段二：全量技术栈

- [ ] 将 SQLite 迁移到 PostgreSQL。
- [ ] 将 filesystem broker 迁移到 Redis。
- [ ] 将本地图片存储迁移到 MinIO。
- [ ] 提供 Docker Compose 部署方案。
- [ ] 确认阶段二服务器的 CPU、内存和磁盘资源。
- [ ] 在阶段一现有功能不回退的前提下完成迁移和验收。

## 已完成

- [x] 消除测试环境 JWT 短密钥安全警告
  - 结果：pytest 在导入应用前注入独立的测试专用 JWT 密钥，不读取或暴露本地 `.env` 真实密钥；应用运行时配置逻辑未修改。
  - 验收：专项测试 `2 passed`；后端全量 `199 passed, 1 skipped`；输出不再包含 `InsecureKeyLengthWarning`。
  - 关联 spec：`docs/superpowers/specs/2026-07-20-test-jwt-secret-design.md`；测试案例：`tests/test-test-jwt-secret.md`。
- [x] P0：隔离测试环境与本地运行中的 Celery 队列
  - 结果：pytest 在应用导入前使用 `memory://`；未声明的 Celery 投递会失败；投递测试显式断言 `task_id + run_token`。
  - 验收：后端全量 `197 passed, 1 skipped`；关联 spec `docs/superpowers/specs/2026-07-20-test-celery-isolation-design.md`。
- [x] P0：修复抓取任务安全停止、重复投递和停止后重启的执行权竞争
  - 结果：新增执行令牌、PENDING 原子领取、阶段检查点和令牌级 PID 注册；停止后旧执行与陈旧消息不能继续写入。
  - 验收：执行权/停止定向测试及全量测试通过；关联 spec `docs/superpowers/specs/2026-07-20-crawl-execution-safe-stop-design.md`。
- [x] 推文维度的活动管理、去重审核和本周推文周报
  - 结果：活动管理、详情、审核、删除、模糊去重和周报均以推文为聚合维度；精确去重支持不同 token/URL 形式；Markdown/Excel 包含全部子活动和来源链接。
  - 验收：后端 `197 passed, 1 skipped`、前端 `28 passed`、前端构建和 Playwright 38 个案例退出码均为 0；数据库已迁移到 0010。
  - 关联 spec：`docs/superpowers/specs/2026-07-20-note-centric-management-dedup-report-design.md`。

- [x] 我设置了博主抓取，但是还是依照关键字在搜索，没有按照关联城市的博主进行账号定点抓取
  - 目标：博主列表只抓取绑定到当前城市且启用的博主，按博主 `profile_url` 定点抓取其笔记，不再回退到关键字搜索。
  - 验收：运行 `make crawl-by-city -- city=shanghai` 时只抓取 city_code=shanghai 且 enabled=true 的博主；日志中可见"博主"维度的结果；博主 `profile_url` 为空会被跳过并产生 WARNING。
- [x] 活动管理列表里有城市上海，但是我筛选上海之后没有展示
  - 目标：活动管理列表的城市筛选能够正确返回上海的活动记录。
  - 验收：在活动列表选择"上海"过滤器，列表返回 city_code=shanghai 的活动；URL 参数 `city=shanghai` 与 API 请求参数一致；空结果显示空状态而非报错。
- [x] 博主白名单支持不写小红书id也能保存，支持关联城市配置多个
  - 目标：博主表单允许不填写小红书 ID 即可保存；同一博主可关联到多个城市。
  - 验收：在博主管理新增/编辑博主时留空 `xhs_id` 也能成功保存；同一博主可在多个城市下勾选启用；前端表单提交后端校验通过。
- [x] 所有操作列表，增加宽度不要出现换行
  - 目标：操作列表（活动/博主/任务/重复项等）的操作列加宽，避免按钮文字或图标换行。
  - 验收：在 1280px 及以上分辨率下，操作列按钮单行展示无折行；移动端允许折行但保持可点击；视觉走查无横向溢出。
- [x] 确认阶段一城市配置方式，并支持在配置中心维护城市。
- [x] 初始化关键词配置，并支持按城市维护关键词。
- [x] 准备小红书账号，支持 Chrome 登录态检查与登录后继续抓取。
- [x] 完成阶段一工程搭建：Vue 3、FastAPI、Celery、SQLite、本地文件存储和 filesystem broker。
- [x] 完成 Excel 和 Markdown 导出。
- [x] 完成 OpenCLI `whoami`、`search`、`download` 和 `note` 命令验证。
- [x] 提供 Alembic 数据库迁移脚本。
- [x] 修复 OpenCLI `whoami` 默认 60s 超时：新增 `OPENCLI_BROWSER_COMMAND_TIMEOUT=120`，适配器自动读取并设置 Python 层 `subprocess` 超时为 `inner + 60s` 缓冲。
- [x] 修复 OpenCLI `Missing url` 错误：所有需要 url 的入口（`note`、`blogger_notes`、`download`、`search_recent`）校验非空；`process_note` 与博主循环优雅跳过空 url/空 profile_url 并记录 WARNING。
- [x] 抓取范围完全由"博主管理"和"关键词配置"中 `enabled=true` 的记录驱动
  - 目标：博主列表只抓取绑定到当前城市且启用的博主；关键词列表只取城市启用项；任务参数优先级正确。
  - 验收：`backend/tests/test_crawl_scope.py` 全过；`backend/tests/test_crawl_task_resilience.py` 验证博主 profile_url 为空时跳过 + WARNING；前端仪表盘城市切换时关键词/博主下拉同步更新。
  - 关联：spec `docs/superpowers/specs/2026-07-17-crawl-scope-config-driven-design.md`；E2E `tests/test-crawl-scope-config-driven.md`。
- [x] 仪表盘选择博主时，若信息不全（缺 `profile_url`），给出提示并要求先去配置中心补充
  - 目标：避免博主只填了 username 就提交任务，导致 worker 报 `Missing url` 失败。
  - 验收：选博主时 profile_url 为空的博主标"待补充"；提交任务时若选中有不完整博主，弹出 ElMessage 警告并不发起任务；用户到配置中心点"补充博主信息"按钮后能正常提交。
- [x] FAILED 状态任务显示"结束抓取"按钮
  - 目标：FAILED 任务可能还在跑（worker 自动重试），用户需主动强制停止并清理 Browser tab。
  - 验收：仪表盘 FAILED 任务显示"结束抓取"按钮；点击后调用 `POST /tasks/{id}/stop`，后端允许 RUNNING/FAILED/PAUSED/COMPLETED 状态都强制置为 STOPPED 并写日志；STOPPED/STOP_REQUESTED 状态幂等返回 202。
- [x] 写流程规则到 AGENTS.md
  - 目标：把 AI 协作流程的硬约束持久化到项目里，跨会话可读。
  - 验收：根目录 `AGENTS.md` 存在，含 spec 过审、TDD、提问与回答、撤销不符合规则的代码等约束；流程变更时 AGENTS.md 同步更新。
- [x] 把没有 TDD 测试案例文档的需求补全
  - 目标：之前完成的 4 项需求（抓取范围 / 上海筛选 / 博主白名单 / 操作列宽度）只有 spec 没有对应的 E2E 测试案例文档。
  - 验收：`tests/` 目录下补 4 个 `test-<slug>.md` 测试案例文档：test-crawl-scope-config-driven.md / test-activity-filter-city-code.md / test-blogger-optional-xhs-id.md / test-table-actions-nowrap.md。每个文档描述验收步骤、输入、预期。
- [x] 重启 worker 让 enrich API 生效测试
  - 目标：让博主信息补全 API 端点可被前端调用。
  - 验收：实测 `POST /api/v1/settings/bloggers/{id}/enrich` 返回 200，回填博主 profile_url 与 platform_user_id（enrich API 跑在 uvicorn 进程而非 worker 进程，所以不需要重启 worker 也能生效；这条 TODO 主要是验证 API 可用）。
- [x] 提供博主信息自动补全（enrich）API + 配置中心"补充博主信息"按钮
  - 目标：用户只填博主名字也能保存；配置中心提供按钮用 opencli search 自动回填 user_id 与 profile_url。
  - 验收：`backend/tests/test_blogger_enricher.py` 4 个测试全过；`backend/tests/test_settings_blogger_enrich_api.py` 4 个测试全过；前端 SettingsView 在 profile_url 为空时显示"补充博主信息"按钮；点击成功后 ElMessage 提示 + 重新加载列表。
- [x] 点击"停止抓取"立即停当前任务（spec 1）
  - 目标：解决 worker 跑 STOPPED 任务后还在继续跑剩余 note 的问题。
  - 验收：见 `docs/superpowers/specs/2026-07-17-task-stop-immediate-halt-design.md`。
  - 实现：`backend/app/services/task_registry.py`（跨进程 PID 注册表）；`OpenCLIAdapter.run` 改用 `subprocess.Popen` + `bind_task()`；stop 接口调 `kill_task_pid()` SIGTERM 当前子进程。
  - 测试：`tests/test_task_registry.py` 7 个 + `tests/test_task_stop_immediate.py` 6 个 + `tests/test_adapter_popen_register.py` 5 个 = 18 个全过。
- [x] 博主笔记抓取改用 search 模式（带 xsec_token）（spec 2）
  - 目标：解决博主抓取的笔记 URL 缺 xsec_token 导致 opencli note 失败的问题。
  - 验收：见 `docs/superpowers/specs/2026-07-17-blogger-notes-signed-url-design.md`。
  - 实现：`OpenCLIAdapter.blogger_notes(username, profile_url="")` 改用 `xiaohongshu search <username>` 拿带 token 的 URL；过滤 author 匹配 + URL 含 xsec_token。
  - 测试：`tests/test_blogger_notes_signed_url.py` 6 个全过；`tests/test_opencli_and_dedup_integration.py` 更新 1 个。
- [x] 恢复可重复执行的全量测试基线
  - 目标：修复测试与当前 `subprocess.Popen` 实现不一致导致的真实 OpenCLI 调用和卡死，在不改业务行为、不覆盖现有工作区改动的前提下，恢复后端、前端组件测试与前端构建的稳定验收能力。
  - 验收：后端全量测试、前端组件测试、前端生产构建和 `git diff --check` 均正常结束且退出码为 0；测试过程未启动真实 OpenCLI、Chrome 或网络请求。
  - 实现：修正 `test_run_translates_missing_url_error` 的 `subprocess.Popen` 测试替身，并修正博主补全 API 测试的 `OpenCLIAdapter` patch 路径。
  - 测试：后端 `181 passed, 1 skipped`；前端 `11 files / 28 tests passed`；前端构建成功；关联 spec `docs/superpowers/specs/2026-07-20-test-baseline-recovery-design.md`。
