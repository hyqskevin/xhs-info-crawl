# TODO

本文件是项目待办事项的唯一维护入口。新增需求、后续优化和技术债统一记录在这里；风险及应对措施见 [`risks-todos.md`](risks-todos.md)。

## 使用约定

- 使用 `- [ ]` 表示未完成，使用 `- [x]` 表示已完成。
- 新增事项应写明目标和验收条件，必要时补充关联文档或代码位置。
- 完成后移入"已完成"章节，不直接删除，便于追踪。
- 阶段二事项统一放在"阶段二：全量技术栈"章节。
- 用户已持续授权按本文件顺序自动推进：每项仍需 spec、TDD、验证和独立提交，但无需逐项等待 spec 确认；新增权限、敏感登录、不可逆操作或实质歧义除外。

## 当前待办

> 以下为 2026-07-25 全项目核查新增（证据归档：`docs/superpowers/qa/2026-07-25-project-audit.md`），按列表顺序依次讨论修复。

- [x] 推文 ID 雪花算法服务是什么，整个项目有用到算法的都整理出来写一份文档md
  - 结果：`docs/superpowers/qa/algorithms.md` 梳理项目所有算法位置（含 XHS 雪花、UUID v4、JWT HS256、Argon2、SequenceMatcher、Celery 文件 broker 等），每一项给出文件 / 触发点 / 入参出参 / 强度评估 / 阶段二待替换路径。
- [ ] 多账号体系 + RBAC（分组 + 权限）
  - 目标：当前只有 admin。升级为多账号平等（`Administrator` 组默认有全部权限），新增"账号管理"左侧 nav；账号可以分组、分组关联权限集；`sub` 角色划分保留为未来"子账号"扩展。
  - 验收：新 `users/groups/permissions/group_permissions/user_groups` 表；新 `AccountsView.vue`（左 nav 新增），含账号 / 分组 / 权限 三 tab；后端 `require_permission(code)` 替换 `require_admin`；前端 49+ 测试，build 通过；实操：用 admin 新建 editor 账号 → 限定权限 → editor 登录验证无权页面 403。
  - 关联：spec `docs/superpowers/specs/2026-07-21-multi-account-rbac-design.md`（已写）。
- [x] 一次性数据库迁移 `seed_admin` 启动后兜底管理员
  - 目标：当数据库完全为空（首次部署/重置）时，没有 admin 用户无法登录。当前 admin 凭据是手工 sql 新增。
  - 验收：迁移 `0012_seed_admin.py` 在 upgrade 时若 `users` 表为空则插入 admin 用户；密码来自环境变量 `INITIAL_ADMIN_PASSWORD`，未设置则使用 `Admin@123` 且 WARNING 提示"生产环境必须更改"；脚本幂等：若 admin 已存在则跳过。重置 db（删除数据文件后跑 alembic upgrade head）后能用默认密码登录。
  - 结果：迁移已实现并跑过真实 DB；实测 `alembic_version = 0012`，`users(1, admin, admin, 97-byte Argon2)`，Argon2.verify("Admin@123") → True。后端 316→321 passed（5 个 case：users 空 seed / 已存在跳过 / env 覆盖密码 / WARNING 日志 / downgrade 删除）。不更新 v0.2.0；累积到下个 release cycle。
- [x] OPENCLI_BIN 入配置中心「系统配置」tab（用户 2026-08-08 反馈）
  - 目标：opencli 不在 PATH 时只能在 `.env` 改 `OPENCLI_BIN`，期望配置中心可视化填写自定义绝对路径（已用 nvm 安装：`/Users/kevin_w/.nvm/versions/node/v22.18.0/bin/opencli`）。
  - 验收：复用 2026-08-03 已实现的 `GET/PUT /settings/system-config` 端点，仅补 `opencli_bin` 一项（`_ENV_KEY_MAP` 与 `SystemConfigIn` 加字段）；`SettingsView.vue` 系统配置 tab 新增「抓取工具」分组（ElInput + ElTooltip "支持绝对路径，留空回退 PATH 解析"）；后端 +1 测试（PUT 写 .env + GET 回读），前端 +1 测试（input 渲染 + 保存回传 payload）；后端全量 / 前端 87+ 测试 / build 全绿；用户实操：登录 → 配置中心 → 系统配置 → 抓取工具 → 填路径 → 保存 → 仪表盘系统状态卡 opencli 探测显示 ✓。
  - 结果：spec `docs/superpowers/specs/2026-08-08-system-config-opencli-bin-design.md`；后端 `tests/test_system_config_api.py` +1 用例（PUT → 200 → .env 含 `OPENCLI_BIN=/Users/.../bin/opencli` → GET 回读）；前端 `SettingsView.spec.ts` +1 用例（input 渲染 placeholder="opencli" + setValue 后 updateSystemConfig payload 含字段）；前端全量 88 passed、build 通过；生产端点 `GET /settings/system-config` 实测返回 18 字段含 `opencli_bin`；worker / beat 已重启（PID 见 `data/logs/`）。部署：`app/api/v1/*.py` 与 `app/services/*.py` 都需重启 worker 才能让新 `OPENCLI_BIN` 在抓取流程生效。
- [x] 城市复用 + 关键词组一对多
  - 目标：城市 DB unique 约束；关键词组 `KeywordGroup` 实体（可挂多个城市、可包含多个关键词）；仪表盘关键词下拉改为多选关键词组；`crawl_scope.resolve_crawl_scope` 改写。
  - 验收：新 migration `0013_keyword_groups.py`；新 API `settings/keyword-groups` 与 `tasks/crawl {keyword_group_ids}`；旧字段 `keywords` 兼容保留；前端 `SettingsView` 增加关键词组 tab；后端 308+ 测试，前端 49+ 测试，build 通过。
  - 关联：spec `docs/superpowers/specs/2026-07-21-city-and-keyword-groups-design.md`（已写）。
  - 结果：5 个 commit：
    - `a20a0e5` feat(models): keyword_groups 多对多 + migration 0013
    - `d296f48` feat(api): keyword-groups CRUD API
    - `450d85f` feat(crawl_scope): resolve keyword_group_ids
    - `3c65227` feat(frontend): DashboardView 用 keyword_group_ids
    - `927110a` feat(frontend): SettingsView 增加关键词组 tab
  - 实测：生产 DB alembic 0013 通过；cities 在 0013 前由 dedupe_cities 清理；后端 336 passed（+15 case），前端 48 passed，build OK。
- [ ] 重启 celery beat 与 worker（长期有效，随每次 models/tasks/services 改动执行）
  - 目标：服务进程管理已写进 AGENTS.md；2026-07-25 已随 TODO#2/#3 执行一次（见"已完成"区），后续改动 models/tasks/services 后仍需重启。
  - 验收：改动后检查 `ps aux | grep celery` 进程启动时间不早于代码改动时间。
- [x] 一次性数据库迁移 `seed_admin` 启动后兜底管理员
  - 目标：当数据库完全为空（首次部署/重置）时，没有 admin 用户无法登录。当前 admin 凭据是手工 sql 新增。
  - 验收：迁移 `0012_seed_admin.py` 在 upgrade 时若 `users` 表为空则插入 admin 用户；密码来自环境变量 `INITIAL_ADMIN_PASSWORD`，未设置则使用 `Admin@123` 且 WARNING 提示"生产环境必须更改"；脚本幂等：若 admin 已存在则跳过。重置 db（删除数据文件后跑 alembic upgrade head）后能用默认密码登录。
  - 结果：迁移已实现并跑过真实 DB；实测 `alembic_version = 0012`，`users(1, admin, admin, 97-byte Argon2)`，Argon2.verify("Admin@123") → True。后端 316→321 passed（5 个 case：users 空 seed / 已存在跳过 / env 覆盖密码 / WARNING 日志 / downgrade 删除）。不更新 v0.2.0；累积到下个 release cycle。
- [x] 多小红书账号配置 + 抓取失效自动切换（2026-07-28 新增需求）
  - 目标：支持配置多个**小红书账号**（抓取用的登录态，不是系统登录账号——与上面"多账号体系 + RBAC"是两回事）。配置 navbar 下新开「账号配置」页面：登记多个小红书账号（名称/备注/登录状态/启用），抓取时优先用主账号；当某账号在抓取中失效（未登录/扫码超时/被风控验证）时，自动切换到下一个可用账号继续，全部失效才 PAUSED 等人工处理。
  - 结果：①新模型 `XhsAccount`（name/remark/session_name/login_status/enabled/priority）+ migration `0019_xhs_accounts.py`；②API `/api/v1/xhs-accounts` CRUD + `POST /{id}/check-login`（调 opencli whoami）；③`crawl_task.py` 改造为两阶段流水线（download_and_ocr → extract_and_save），`load_xhs_accounts` 按 priority 排序加载账号，主循环捕获 `AuthenticationRequired`/`VerificationRequired` 时 `account_index += 1` 切换到下一个账号并记 INFO 日志，全部失效抛 `CrawlHalted` 进入 PAUSED；④无账号配置时回退默认 session 'xhs-crawler'，向后兼容；⑤前端 SettingsView 新增「账号配置」tab（CRUD + 检测登录按钮 + 启用开关 + 优先级），DashboardView 发起抓取卡片新增「操作账号」下拉（可选，不选则按 priority 自动）。
  - 验收：后端 `625 passed, 1 skipped`（+20 新 case：XhsAccount 模型/API/CRUD/check-login/笔记级切换/全部失效 PAUSED/无账号回退），前端 `106 passed`（+17 新 case：账号配置 tab CRUD/检测登录/Dashboard 操作账号下拉），build 通过；spec `docs/superpowers/specs/2026-08-10-multi-xhs-account-design.md`。
  - 部署：**worker 必须重启**（改动 `app/tasks/crawl_task.py` + `app/services/opencli_adapter.py`）；执行 `alembic upgrade head`（migration 0019 建 xhs_accounts 表）；uvicorn `--reload` 自动加载 API 层。

- [ ] 抓取详情空值/风控熔断 + adapter 周期性重置 + token 池刷新（2026-08-12 用户反馈）
  - 目标：抓取 200+ 笔记后陆续出现 `EMPTY_RESULT_RETRYABLE`（实测 7/107 = 6.5%），根因是 Chrome profile 累积 + 200+ 独立 `page.goto` 触发小红书 web 风控，部分 `xsec_token` 提前失效，opencli 拿到的 `desc` 为空字符串。需要 ①连续空详情 PAUSED 熔断（连续 5 篇空值 → 抛 `CrawlHalted` 类似 进入 PAUSED）；②每抓 N 条（默认 30）调用 `adapter.close_session()` 重建 CDP 连接，强制 Chrome profile 释放；③**token 池自动刷新**（在 streak = 阈值 - 2 时重新跑 search 拿新 xsec_token，按 `platform_note_id` 替换原 entry URL）。
  - 验收：后端 `download_and_ocr` 暴露 `note.content` 非空计数，连续 5 篇空 → 抛 `CrawlHalted("连续 N 篇笔记详情为空，疑似触发小红书风控...")`；`run_crawl` 主循环在 `staged_notes` 累计 N 条时调 `adapter.close_session()` 重建；streak 达到阈值 - 2（默认 3）时调 `throttled_search` 重新搜索并按 `platform_note_id` 替换 entry URL；`assert_execution_active` 仍可正常停止；新后端测试 8+ 用例（连续空熔断 / 部分空允许 / 周期性重置触发 / 重置后账号不变 / 停止信号仍响应 / token 池刷新 / 配额用尽回退熔断）；后端全量测试 + build 通过；spec `docs/superpowers/specs/2026-08-12-empty-detail-throttling-design.md`。
  - 部署：改动 `app/tasks/crawl_task.py` + `app/services/opencli_adapter.py` + `app/core/config.py`，**worker 必须重启**（新增 Settings 字段不需 alembic 迁移）。

- [x] 仪表盘连接检测面板（opencli 连通 + 小红书号登录 + 浏览器池）
  - 目标：仪表盘目前只有一个"后端服务"健康卡片，看不到 opencli 二进制是否在 PATH、当前 whoami 登录的是哪个小红书号、Chrome 是否能拉起。用户排障常卡在"opencli 找不到""未登录""Chrome 拉不起来"三件事，需要在仪表盘一发即查。
  - 结果：新文件 `app/services/diagnostics.py`（`probe_opencli/probe_xhs_login/probe_xhs_pool/probe_snapshot`，异常隔离）；新路由 `app/api/v1/diagnostics.py` 注册 4 端点（snapshot + 3 单测）；`DashboardView.vue` 加「连接检测」卡片，三段独立检测按钮 + 失败原因文案 + loading 态；入页自动调 `/snapshot` 一次（不轮询）；`api.client.ts` 加 4 个调用方法；`docs/api-doc.md` 补「连接检测接口」章节。
  - 验收：后端 `tests/test_diagnostics_api.py` 6 用例先红后绿（snapshot 三段 / opencli bin 缺失 503 / auth_required 200 / timeout 200 / CDP 不可达 200 / snapshot 隔离失败）；前端 `DashboardView.spec.ts` 3 新用例（卡片三段渲染 / 单按钮只更新一段 / 失败 reason 渲染）；后端 `532 passed, 1 skipped`（基线 526 + 6 新），前端 `79 passed`（基线 76 + 3 新），build 通过。spec `docs/superpowers/specs/2026-08-03-diagnostics-panel-design.md`。
  - 部署：改动 `app/api/v1/*.py` 与 `app/services/*.py`（uvicorn `--reload` 自动加载），前端 Vite HMR 自动刷新；**worker/beat 不需重启**。

- [x] 允许无子活动推文审核通过（用户 2026-08-03 反馈）
  - 目标：推文本身即活动内容，即使 MiniMax 未提取出结构化子活动，也应能审核通过。移除 `review_note` 和 `batch/approve` 的活动数量前置校验。
  - 结果：`notes.py` 的 `review_note` 删 `has_activity` 校验，`approve_notes` 删 `activity_counts` 查询与 `skipped` 跳过逻辑；`test_notes_api.py` 新增 `test_review_single_note_without_activities_succeeds`，`test_review_consistency.py` 的 `test_batch_approve_skips_notes_without_activities` 改为 `test_batch_approve_allows_notes_without_activities`；`docs/api-doc.md` 同步。
  - 验收：后端 `530 passed, 1 skipped`（+2 新 case，-2 旧 case 替换），前端 `79 passed`，build 通过。spec `docs/superpowers/specs/2026-08-03-allow-review-without-activities-design.md`。
  - 部署：改动 `app/api/v1/*.py`，uvicorn `--reload` 自动加载；**worker/beat 不需重启**。

- [x] 推文编辑页展示活动 + 单条重提取 + 手动补充活动（用户 2026-08-03 新增需求）
  - 目标：点击编辑推文后，弹窗/详情页能展示该推文下已有的子活动列表。无活动时提供"重新提取"按钮，对单条推文重新触发 OCR + MiniMax 活动提取（不重抓整篇推文）。同时支持手动新增活动（名称、地点、开始/结束时间、类型、简介）。
  - 验收：推文编辑弹窗增加"识别活动"区域（列表展示已有活动 + 空态提示）；"重新提取"按钮触发后端 `POST /notes/{id}/re-extract` 端点，异步跑 OCR→MiniMax→validator 流程，返回提取结果；"手动添加"按钮弹出活动表单，提交后写入 `activities` 表关联当前推文；spec 先行，后端/前端测试与 build 全绿。

- [x] 仪表盘连接检测与后端健康合并上移 + 配置中心移除 opencli 测试（用户 2026-08-03 新增需求）
  - 目标：仪表盘当前"后端服务"健康卡片和"连接检测"卡片分开，占用空间。合并为一张"系统状态"卡片，放到"发起抓取"卡片上方，整合健康状态 + opencli/登录/Chrome 三项检测。配置中心 SettingsView 的 opencli 测试按钮不再需要（仪表盘已有）。
  - 验收：仪表盘「系统状态」卡片位于抓取卡片上方，含后端健康（绿/红）+ 三项连接检测（opencli/登录/Chrome 池），每项可独立重测；配置中心 SettingsView 移除 opencli 测试按钮及相关代码；spec 先行，后端/前端测试与 build 全绿。

- [x] 配置中心博主白名单支持每个博主抓取数量上限（用户 2026-08-03 新增需求）
  - 目标：博主管理支持为每个博主设置 `max_notes_per_crawl`（每次抓取该博主最多取多少篇笔记），默认 0 表示不限制。抓取时按此值截断博主笔记列表。
  - 验收：`Blogger` 模型新增 `max_notes_per_crawl` 字段（migration 0017）；博主 CRUD API 支持读写该字段；前端 SettingsView 博主表格新增"抓取上限"列（可编辑，默认 0=不限制）；`crawl_task` 博主循环在取到上限后停止该博主；spec 先行，后端/前端测试与 build 全绿；worker/beat 改动后重启。

- [x] 活动管理增加按博主筛选推文（用户 2026-08-03 新增需求）
  - 目标：活动管理（推文列表）页增加"博主"筛选下拉框，选择博主后只显示该博主发布的推文。博主来源为配置中心已录入的博主白名单（按城市过滤）。
  - 验收：后端 `GET /notes` 新增 `blogger_id` 查询参数，通过 `Note.source_url` 匹配博主 `profile_url` 前缀；前端 ActivitiesView 工具栏新增"博主"下拉（ElSelect，按当前城市过滤博主列表，支持搜索）；选择博主后列表刷新，清空博主恢复全部；spec 先行，后端/前端测试与 build 全绿。

- [x] 配置中心 env 级配置可视化 + 定时任务抓取批次配置（用户 2026-08-03 新增需求）
  - 目标：将 `.env` 中的配置项搬到配置中心界面，单开"系统配置"tab，支持可视化配置活动识别模型（MiniMax）、PaddleOCR、单笔记流水线重试、小红书滚动策略、抓取数量。定时任务页新增"抓取批次"tab，展示抓取相关配置。
  - 结果：后端 `GET/PUT /settings/system-config` 端点读写 `.env` 文件，保留注释和空行，支持 17 个配置项；前端 SettingsView 新增"系统配置"RadioButton + 5 组分组表单，SchedulesView 新增"抓取批次"RadioButton + 2 组表单；api/client.ts 新增 `systemConfig`/`updateSystemConfig` 方法。
  - 验收：后端 `tests/test_system_config_api.py` 4 用例（GET 默认值 / PUT 更新 / 保留注释 / 追加新 key），前端 `SettingsView.spec.ts` +3 用例（系统配置 tab 展示 / 保存 / 隐藏新增按钮），`SchedulesView.spec.ts` +2 用例（抓取批次 tab 展示 / 保存）；后端 `544 passed, 1 skipped`（+4 新），前端 `87 passed`（+5 新），build 通过。spec `docs/superpowers/specs/2026-08-03-system-config-and-crawl-batch-design.md`。
  - 部署：改动 `app/api/v1/*.py`，uvicorn `--reload` 自动加载；**worker/beat 不需重启**（仅 API 层改动）。注意：修改配置后需重启 worker/beat 才能让新配置在抓取流程中生效。

- [x] 仪表盘抓取前先选定操作账号 + 扫码登录确认
  - 目标：现在 Dashboard 抓取卡片默认走「当前 Chrome 已登录的小红书账号」，无法指定具体哪个。引入「操作账号」概念：抓取任务启动前用户在 Dashboard 选择本次抓取用哪个 XhsAccount 池（如有，按其内账号轮询；若只有一个账号，自动选中且不可改）；点击「开始抓取」后必须显式调用 whoami 探测，未登录则**阻塞任务发起**，弹「扫码登录」引导并自动打开 Chrome 登录页；用户在前端再次点击「检测登录」→ whoami 通过 → 才把任务真正下发到 Celery。
  - 结果：随「多小红书账号配置 + 抓取失效自动切换」一并实现。①`/api/v1/xhs-accounts` CRUD + `POST /{id}/check-login`（whoami 探测）；②`POST /api/v1/tasks/crawl` 接受 `xhs_account_id`（可选），不传则按 priority 自动选第一个；③DashboardView 发起抓取卡片新增「操作账号」下拉（ElSelect，clearable，不选则自动按优先级）；④前端「检测登录」按钮调 `check-login` 端点，返回登录状态更新 ElTag 三态（unknown/logged_in/logged_out）。
  - 验收：后端 `625 passed, 1 skipped`，前端 `106 passed`，build 通过。
  - 与「多账号 + 自动切换」配套：本条是启动前预检+选定，后者是运行中切换。两者共用同一份 XhsAccount 配置，已合并实现。

## 后续优化

- [x] MiniMax 批量并行集成到 crawl_task（2026-08-10 衔接项）
  - 目标：`MiniMaxClient.extract_many_parallel` 方法已实现并测试通过（默认 `minimax_concurrency=1` 串行，最高 4 并行），但 `crawl_task.py` 仍保持逐篇 `extract_many` 调用。需把"逐篇下载→OCR→MiniMax→写DB"重构为"批量下载+OCR → 批量并行 MiniMax → 写DB"两阶段流水线，让 MiniMax 真正并行起来。
  - 结果：`crawl_task.py` 拆分 `process_note` 为 `download_and_ocr`（阶段1：下载+OCR，产出 `StagedNote`）和 `extract_and_save`（阶段2：MiniMax 提取+写 Activity）；主循环先逐篇 `download_and_ocr` 收集 `staged_notes`，再批量调 `MiniMaxClient.extract_many_parallel(texts, reference)` 并行提取，结果按顺序 `zip` 回写 DB；并发数由 `settings.minimax_concurrency` 控制（默认 1=串行，向后兼容）；`run_stage` 包裹 `extract_many_parallel` 提供指数退避重试。
  - 验收：后端 `625 passed, 1 skipped`（含多篇并行提取 + concurrency=1 串行回退 + 529 重试场景），前端 `106 passed`，build 通过；spec `docs/superpowers/specs/2026-08-10-crawl-pipeline-parallel-speedup-design.md`。
  - 部署：**worker 必须重启**（改动 `app/tasks/crawl_task.py`）。

- [x] 侧边 navbar 折叠收拢 + 子页面 tab 改二级目录（用户 2026-08-10 反馈）
  - 目标：①侧边 navbar 支持向左折叠收拢（Element Plus `ElAside` + `ElMenu :collapse` 自带能力，点击按钮切换）；②配置中心和定时任务的页面内 RadioButton tab 改为 navbar 一级目录下的二级目录（`ElSubMenu` + `ElMenuItem`，组件自带）。
  - 结果：`AppLayout.vue` 新增折叠按钮（`isCollapse` ref + localStorage 持久化），`ElAside :width` 动态切换 64px/220px，`ElMenu :collapse="isCollapse"`；配置中心改为 `ElSubMenu`（`/settings`）下挂 6 个 `ElMenuItem`（城市抓取配置/博主白名单/关键词组/博主组/账号配置/系统配置，各带 `?tab=` query）；定时任务改为 `ElSubMenu`（`/schedules`）下挂 2 个 `ElMenuItem`（定时任务列表/抓取批次配置）；`ElMenu router :default-active="route.fullPath"` 实现二级菜单直接路由。
  - 验收：前端 `106 passed`（含 AppLayout 折叠按钮 + 二级菜单渲染 + localStorage 持久化用例），build 通过。
  - 关联：Element Plus `ElMenu` 支持 `:collapse` 属性；`ElSubMenu` 支持二级目录。

- [ ] 登录接口失败限流
  - 目标：`/auth/login` 无失败限流，内部工具风险低，但可加内存级失败计数 + 指数退避。
  - 验收：连续 5 次失败返回 429；测试覆盖。

## 打包分发（2026-08-10 新增独立工作流）

> 当前工程只能 git clone 安装，需打包成最终用户双击即用的桌面程序。spec `docs/superpowers/specs/2026-08-10-one-click-packaging-design.md`。

- [x] P1 路径修复：废弃死配置 `paddleocr_model_dir` + 在 Python 代码设置 `PADDLE_PDX_CACHE_HOME`/`HF_HOME`
  - 目标：审计发现 `paddleocr_model_dir` 是死配置（`paddleocr_adapter.py` 从未使用），且 `PADDLE_PDX_CACHE_HOME`/`HF_HOME` 只在 `scripts/dev-worker.sh` 里 export，直接跑 uvicorn/celery 会污染 `~/.paddlex/`（违反 AGENTS.md 硬约束）。
  - 结果：删除 `config.py` 的 `paddleocr_model_dir`；新增 `paddle_pdx_cache_home`/`huggingface_cache_home` 字段（`Field` + `validation_alias`）；`get_settings()` 用 `os.environ.setdefault` 设置两个变量 + `mkdir` 创建目录；`.env.example`/`test_scaffold_contract.py`/`conftest.py`/`docs/paddleocr-setup.md` 同步更新；新增 `test_paddleocr_cache_env.py`（4 测试）+ 扩展 `test_config.py`（5 测试）；附带修复开发 DB 遗留的 keywords 表未 drop 问题。
  - 验收：后端 `637 passed, 1 skipped, 0 failed`（含 P1 相关 12 测试 + `test_project_internal_writes` 静态扫描）；grep 确认生产代码无 `paddleocr_model_dir`/`PADDLEOCR_MODEL_DIR` 残留。
  - 部署：**worker 必须重启**（改动 `app/core/config.py` Settings 字段 + `get_settings()`）。重启后 `get_settings()` 自动设置 `PADDLE_PDX_CACHE_HOME`/`HF_HOME`，paddleocr 不再污染 `~/.paddlex/`。
  - spec：`docs/superpowers/specs/2026-08-10-one-click-packaging-design.md` § 7.3
  - plan：`docs/superpowers/plans/2026-08-10-p1-paddleocr-path-fix.md`
- [x] P2 后端静态文件挂载 + OCR 诊断接口
  - 目标：让后端直接服务前端构建产物（打包版需要），并新增 OCR 诊断接口供启动器测试。
  - 结果：`main.py` 新增 `mount_static_frontend_if_exists` 函数(dist 不存在则跳过;存在则挂载 `/assets` + SPA fallback);`lifespan` 启动时调用;Settings 新增 `frontend_dist_path` 字段;新增 `POST /api/v1/diagnostics/ocr` 接口(5 种状态:ocr_disabled/paddleocr_not_installed/model_not_found/inference_failed/ok);新增 `app/services/diagnostics_ocr.py` 服务;生成测试图 `tests/fixtures/ocr_test.png`。
  - 验收：后端 `646 passed, 1 skipped, 0 failed`(含 P2 新增 9 测试 + `test_project_internal_writes` 静态扫描)。
  - 部署：**API 需重启**(改动 `app/main.py` lifespan);worker 不需要重启(没改 worker 代码)。
  - spec：`docs/superpowers/specs/2026-08-10-one-click-packaging-design.md` § 7.1 + § 7.2
  - plan：`docs/superpowers/plans/2026-08-10-p2-static-mount-ocr-diagnostic.md`
- [x] P3 启动器 Python 后端（进程管理 + 状态服务 + env bootstrap）
  - 目标：实现 `launcher/main.py`、`process_manager.py`、`status_server.py`、`env_bootstrap.py`、`port_finder.py`、`opencli_checker.py`、`ocr_installer.py`。
  - 结果：①`port_finder.py` 用 socket bind 探测可用端口；②`env_bootstrap.py` 实现 SECRET_KEY/INITIAL_ADMIN_PASSWORD 自动生成、.env 初始化、API_HOST 强制 127.0.0.1、PADDLE_PDX_CACHE_HOME/HF_HOME 设置；③`opencli_checker.py` 调 `opencli doctor` 解析状态（not_installed/daemon_not_running/extension_not_connected/timeout/unknown_error）；④`ocr_installer.py` 实现 URL 生成、状态检测、下载安装（SHA256 校验 + 解压 + pip 装 wheels）；⑤`process_manager.py` 管理 api/worker/beat 子进程（启停/重启/状态查询/日志写入/退出检测）；⑥`status_server.py` 提供 FastAPI 状态服务（status/restart/stop/opencli test/ocr install 等端点）；⑦`main.py` PyWebView 入口整合所有模块。
  - 验收：`launcher/tests/` 7 个测试文件全绿（48 passed，含 port_finder 4 + env_bootstrap 13 + opencli_checker 7 + ocr_installer 8 + process_manager 7 + status_server 9）。
  - spec：`docs/superpowers/specs/2026-08-10-one-click-packaging-design.md` § 2-5 + § 7.3 + § 13
  - plan：`docs/superpowers/plans/2026-08-10-p3-launcher-backend.md`
- [x] P4 启动器 UI（Vue + Element Plus + Material Design 3）
  - 目标：实现 `launcher/ui/` Vue 项目，遵循 M3 设计语言（暗色主题、语义化 CSS 变量、M3 组件映射、4dp 间距网格）。
  - 结果：①项目脚手架（package.json/vite.config.ts/tsconfig.json/index.html/main.ts）；②M3 设计令牌 `tokens.css`（颜色/排版/间距/圆角/阴影 CSS 变量）；③API 客户端 `client.ts`（封装 10 个状态服务端点）；④4 个子组件：ServiceStatus（服务状态卡片）、OpenCLIPanel（OpenCLI 连接卡片）、OcrPanel（OCR 增强卡片）、LogViewer（日志卡片）；⑤App.vue 整合（Top App Bar + 4 个子组件 + 底部操作栏 + 3s/5s 轮询 + OCR 安装进度轮询 + PyWebView exit API）；⑥构建验证 `npm run build` 产出 `dist/index.html` + `dist/assets/*`。
  - 验收：7 个测试文件 62 passed（design-tokens 8 + client 11 + App 10 + ServiceStatus 9 + OpenCLIPanel 7 + OcrPanel 11 + LogViewer 6）；`npm run build` 成功产出 dist/；vue-tsc 类型检查通过（修复 @types/node 缺失和未使用导入）。
  - spec：`docs/superpowers/specs/2026-08-10-one-click-packaging-design.md` § 4.6 + § 4.3 + § 4.7
  - plan：`docs/superpowers/plans/2026-08-10-p4-launcher-ui.md`
- [x] P5 打包脚本 + GitHub Actions
  - 目标：实现 `scripts/package-macos.sh`、`scripts/package-windows.ps1`、`scripts/package-ocr-addon.sh`、`.github/workflows/release.yml`、`.github/workflows/release-ocr-addon.yml`。
  - 结果：①`backend/requirements-runtime.txt`(不含 ocr extra);②`launcher/requirements.txt`(pywebview/fastapi/httpx);③`.gitattributes`(git archive 排除 .venv/node_modules/data/.env/dist);④`scripts/package-macos.sh`(python-build-standalone cpython-3.11.9 + venv + .app bundle + zip);⑤`scripts/package-windows.ps1`(对应 macOS 版,start.bat 入口);⑥`scripts/package-ocr-addon.sh`(3 平台 paddleocr wheel + 模型下载 + VERSION);⑦`.github/workflows/release.yml`(v*.*.* tag 触发,build-macos + build-windows + release 三 job,含 src.zip);⑧`.github/workflows/release-ocr-addon.yml`(ocr-addon-* tag 触发,3 平台 build + release)。
  - 验收：`backend/tests/test_packaging_scripts.py` 72 项结构验证全绿(8 requirements + 5 gitattributes + 15 macos + 13 windows + 13 ocr-addon + 18 workflows);后端 719 passed(P5 无回归,7 个 opencli_bin 环境变量失败为预先存在)。
  - spec：`docs/superpowers/specs/2026-08-10-one-click-packaging-design.md` § 6.1-6.7
  - plan：`docs/superpowers/plans/2026-08-10-p5-packaging-scripts.md`
- [x] P6 端到端验收 + 文档
  - 目标：在干净环境验证打包版完整流程；补齐用户文档和开发者文档。
  - 结果：①`README-USER.md`(新文件,11 章节用户使用说明,含安装/OpenCLI/OCR/端口冲突/常见问题);②`INSTALL.md` 第 9 章"Packaged Build"(打包版安装、与开发者版差异、升级);③`docs/deployment.md`"打包版部署"章节(架构/GitHub Actions/本地复现/OCR 分发/数据目录/升级策略/进程管理);④`tests/test-launcher-startup.md`(8 步骤 + 3 异常案例);⑤`tests/test-opencli-connection.md`(5 步骤 + 5 异常案例);⑥`tests/test-ocr-install.md`(5 步骤 + 5 异常案例 + 平台差异表)。
  - 验收(文档):6 个产物全部创建,内容覆盖 spec §3 所有章节。
  - 验收(真实环境,待推 tag):macOS 解压双击 → 三进程运行;OCR 一键安装;端口冲突自动处理——需推 `v*.*.*` tag 触发 GitHub Actions 构建后下载验证。
  - spec：`docs/superpowers/specs/2026-08-12-p6-acceptance-and-docs-design.md`


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

- [x] 废弃 legacy keywords 表 + 修复关键词组管理 bug + 配置入口去重（用户 2026-08-10 反馈）
  - 目标：①legacy `keywords` 表与关键词组功能重复，废弃方案 A 彻底清理；②关键词组名称无法修改；③关键词输入后不展示；④定时任务"分组管理"tab 与配置中心重复。
  - 结果：①后端新增 `PATCH /keyword-groups/{id}` 端点（更新 name/description/enabled，重名 409）；②删除 `Keyword` 模型、`_resolve_from_legacy_keyword_table`、`sync_keywords`、`normalize_keywords`、`KeywordIn`、`MODELS/SCHEMAS` 中的 keywords 项；③`CityIn` 移除 `keywords` 字段，`dump_city` 不再返回 keywords；④`/{kind}` 路由 Literal 从 `["keywords","bloggers"]` 改为 `["bloggers"]`；⑤migration `0018_drop_keywords_table.py` drop keywords 表；⑥前端 `KeywordGroupSettings.vue` 修复名称编辑（解除 disabled）+ 关键词输入（改用 `newWord` ref + `v-model`）+ save() 编辑时调 `patchKeywordGroup`；⑦`SettingsView.vue` 移除城市 tab 的关键词列和输入框；⑧`SchedulesView.vue` 移除"分组管理"tab（关键词组+博主组管理统一到配置中心）；⑨`SettingsView.vue` 新增"博主组"tab（内嵌 `BloggerGroupSettings` 组件）；⑩`api/client.ts` 新增 `patchKeywordGroup` 方法。
  - 验收：新增 `tests/test_keyword_group_patch_and_legacy_cleanup.py` 9 用例（PATCH name/desc/enabled + 重名 409 + 不存在 404 + Keyword 模型删除 + legacy 函数删除 + 无兜底返回空 + 表已 drop），先红后绿；后端 `605 passed, 1 skipped`（+9 新，修复 15 个测试文件的 Keyword import），前端 `89 passed`，build 通过；spec `docs/superpowers/specs/2026-08-10-keyword-group-cleanup-and-bugfix-design.md`。
  - 部署：**worker 必须重启**（改动 `app/services/crawl_scope.py` + `app/api/v1/tasks.py`）；执行 `alembic upgrade head`（migration 0018 drop keywords 表）；uvicorn `--reload` 自动加载 API 层。

- [x] 修复 extract_activity_fields 非法日期导致 "day is out of range for month" 笔记处理崩溃（用户 2026-08-10 反馈抓取报错）
  - 目标：抓取某笔记时报 `ValueError: day is out of range for month`，整篇笔记处理失败。
  - 根因：`backend/app/services/extraction.py` 的 `extract_activity_fields` 函数三个 `datetime()` 构造（原第 69/71/73 行）未包 try/except。当文本/MiniMax 返回非法日期（如 "2月30日"、"11月31日"、"2026-02-30"、"13月1日"）时直接抛 ValueError 冒泡到 crawl_task。同文件 `normalize_activity_datetime` 已有 try/except 保护，但 `extract_activity_fields` 在调用 normalize 之前就构造 start_time，缺同样保护。
  - 证据：DB TaskLog task_id=24 记录 `笔记处理失败 [https://...6a72d842000000002500a1de]：day is out of range for month`；复现脚本 `extract_activity_fields("2月30日", now, None)` 直接抛 ValueError。
  - 结果：三个 datetime 构造分支（iso/cn/short_dot）各包 try/except，非法日期时 `start_time = None`，让后续 normalize 流程正常处理其他字段。
  - 验收：`tests/test_pipeline_services.py` 新增 13 用例（12 非法日期参数化 + 1 合法日期无回归），先红后绿；后端 `597 passed, 1 skipped`（+13 新）；spec `docs/superpowers/specs/2026-08-10-extract-activity-fields-invalid-date-design.md`。
  - 部署：改动 `app/services/extraction.py`，**worker 必须重启**才能让修复在抓取流程生效。

- [x] 抓取流水线并行加速：图片并行 OCR + MiniMax 可配置并发（用户 2026-08-10 反馈"如何加快抓取进度"）
  - 目标：单篇笔记流水线 OCR 串行（18 张图逐张识别）和 MiniMax 串行调用是主要瓶颈。实现笔记内图片并行 OCR（本地 PaddleOCR，不占网络带宽）和 MiniMax 可配置并发调用（默认 1，最高 4）。
  - 结果：①`Settings` 新增 `ocr_parallel_workers`（默认 2，1-4）和 `minimax_concurrency`（默认 1，1-4）字段；②`OCRService` 新增 `process_batch` 方法（ThreadPoolExecutor 并行 + 子线程内重试，按输入顺序返回结果）；③`MiniMaxClient` 新增 `extract_many_parallel` 方法（并发数由 settings 控制，方法已就绪供后续 crawl_task 批量集成）；④`crawl_task.py` OCR 部分从串行循环改为 `process_batch` 并行调用；⑤系统配置 API `_ENV_KEY_MAP`/`SystemConfigIn` 新增两个字段；⑥`.env.example` 新增 `OCR_PARALLEL_WORKERS`/`MINIMAX_CONCURRENCY`；⑦前端 `SettingsView.vue` 系统配置 tab 新增"并行线程数"和"并发调用数"两个 ElInputNumber。
  - 验收：新增 `tests/test_crawl_parallel_speedup.py` 11 用例（Settings 字段 4 + MiniMax 并行 3 + OCR 并行 4，先红后绿）；后端 `584 passed, 1 skipped`（+11 新），前端 `90 passed`，build 通过；spec `docs/superpowers/specs/2026-08-10-crawl-pipeline-parallel-speedup-design.md`。
  - 部署：**worker 必须重启**才能让并行 OCR 在抓取流程生效（改动 `app/tasks/crawl_task.py` + `app/services/ocr.py`）；uvicorn `--reload` 已加载 API 层配置项；MiniMax 并行方法已实现但 crawl_task 暂保持逐篇调用（默认 concurrency=1 串行，后续可重构为两阶段流水线）。

- [x] 所有写操作限制在项目内，不污染项目外部目录（用户 2026-08-10 反馈）
  - 目标：整个项目写操作、下载的文件操作都只能放在项目内，不能污染项目外部文件目录。
  - 结果：①`task_registry.py` 从 `/tmp/xhs_task_registry.json` 改为 `Settings.task_registry_path`（默认 `./data/run/task_registry.json`）；②`poster_renderer.py` 从 `tempfile.mkdtemp()` 改为 `Settings.tmp_dir`（默认 `./data/tmp/poster-render-*`）；③`dev-worker.sh` 新增 `HF_HOME=$ROOT_DIR/data/huggingface` 重定向（预防 huggingface_hub 写 `~/.cache/huggingface`）；④测试代码 `test_task_registry.py`/`test_adapter_popen_register.py` 改用 `tmp_path` fixture + monkeypatch；`test_system_config_api.py` 改用 `tmp_path`；⑤测试脚本 `test_poster_*.sh` 从 `/tmp/*` 改为 `$ROOT_DIR/data/tmp/*`；⑥文档 `SPEC.md`/`crawler-design.md` 删除 `$HOME/chrome-debug-profile` 示例；⑦`AGENTS.md` 新增"项目内写操作规范"章节；⑧`.env.example` 新增 `TASK_REGISTRY_PATH`/`TMP_DIR` 配置项。
  - 验收：新增 `tests/test_project_internal_writes.py` 10 用例（Settings 字段 + task_registry 路径 + 静态扫描无硬编码外部路径）；后端 `573 passed, 1 skipped`（+10 新）；spec `docs/superpowers/specs/2026-08-10-project-internal-writes-only-design.md`。
  - 部署：重启 worker 后生效（task_registry 路径变更 + HF_HOME 新增）。

- [x] dev-*.sh 不再 source 全部 .env，配置中心改 .env 后进程自动刷新（用户 2026-08-10 反馈"又回去了"）
  - 目标：配置中心改 OPENCLI_BIN 后，仪表盘先临时生效但 uvicorn --reload 重启后又回退旧值。根因：dev-api/worker/beat/web.sh 用 `set -a; source .env` 全量注入 os.environ，pydantic_settings 优先级 `os.environ > .env`，reload 后新子进程从父进程继承旧 os.environ，.env 新值被覆盖。
  - 结果：四个 dev 脚本改为 `grep` 只读启动参数（API_HOST/API_PORT/CELERY_*/WEB_*），不 source 全部 .env；pydantic_settings 直接读 .env 文件，不受 os.environ 干扰；`update_system_config` 已有的 `os.environ` 同步 + `cache_clear` 保留，让 API 层立即生效。
  - 验收：新增 `tests/test_dev_scripts.py` 3 用例（脚本存在 / 不 source .env / 用 grep 读参数），更新 `test_scaffold_contract.py` 旧测试从"应 source"改为"不应 source"；后端 `563 passed, 1 skipped`；实测 uvicorn 重启后 `/diagnostics/opencli` 返回 `ok: true, bin: /Users/hanamaki_mac_mini/.local/bin/opencli`，`/diagnostics/xhs-pool` 返回 `mode: daemon, daemon_running: true, extension_connected: true`。spec `docs/superpowers/specs/2026-08-10-dev-scripts-no-source-env-design.md`。
  - 部署：重启 uvicorn + worker + beat 后生效。

- [x] 修复同一天合法活动被误判为 `all_before_publish`（用户 2026-08-03 反馈）
  - 目标：note id 337（"在xhs用这招！机票便宜"）正文含"7月27日起"被 MiniMax 解析为 `2026-07-27T00:00/T10:00`，与 published_at `2026-07-27 19:14:25` 同日但早于发布时分，validator 用 `parsed < published_at` 严格小于直接拒绝并归为 `all_before_publish`。改为按"日期"判断：活动 `start_time` 与 `published_at` 同日或之后即视为合法；仅严格更早的日期（含跨日更早）才拒绝。
  - 结果：`activity_validator` 的 `validate_activities` 与 `_is_before_publish` 改为 `parsed.date() < published.date()` 判定（先 `.astimezone(UTC)`），`classify_zero_activity` 同步；`all_before_publish` 分支追加一条 INFO 日志列出被拒绝的 `(name, start_time)` 前 5 条 + 总数，便于后续复盘；既有 `test_validate_skips_activity_before_published_at` 行为不变（前一日仍拒绝）。
  - 验收：`tests/test_activity_validator.py` 新增 6 用例（先红后绿：同日早场接受 / 次日接受 / 前一日拒绝 / 跨时区同日接受 / class 同日早场→ok / class 前一日→all_before_publish）+ `tests/test_activity_window_guard.py` 1 用例（DB fixture 同日早场接受）；后端 `526 passed, 1 skipped`（基线 518 + 7 新），前端 `76 passed`，无回归。spec `docs/superpowers/specs/2026-08-03-same-day-activity-accept-design.md`。
  - 部署：改动 `app/services/*.py` 与 `app/tasks/*.py`，**worker/beat 必须重启**才能生效。

- [x] 配置中心 env 级配置可视化 + 定时任务抓取批次配置（用户 2026-08-03 新增需求）
  - 目标：将 `.env` 中的配置项搬到配置中心界面，单开"系统配置"tab，支持可视化配置活动识别模型（MiniMax）、PaddleOCR、单笔记流水线重试、小红书滚动策略、抓取数量。定时任务页新增"抓取批次"tab，展示抓取相关配置。
  - 结果：后端 `GET/PUT /settings/system-config` 端点读写 `.env` 文件，保留注释和空行，支持 17 个配置项；前端 SettingsView 新增"系统配置"RadioButton + 5 组分组表单，SchedulesView 新增"抓取批次"RadioButton + 2 组表单；api/client.ts 新增 `systemConfig`/`updateSystemConfig` 方法。
  - 验收：后端 `tests/test_system_config_api.py` 4 用例，前端 `SettingsView.spec.ts` +3 用例，`SchedulesView.spec.ts` +2 用例；后端 `544 passed, 1 skipped`（+4 新），前端 `87 passed`（+5 新），build 通过。spec `docs/superpowers/specs/2026-08-03-system-config-and-crawl-batch-design.md`。
  - 部署：改动 `app/api/v1/*.py`，uvicorn `--reload` 自动加载；**worker/beat 不需重启**（仅 API 层改动）。注意：修改配置后需重启 worker/beat 才能让新配置在抓取流程中生效。

- [x] 允许无子活动推文审核通过 + 推文编辑页活动展示/重提取/手动补充 + 仪表盘系统状态合并 + 博主抓取上限 + 活动管理博主筛选（用户 2026-08-03 新增需求包）
  - 目标：①允许无子活动推文审核通过；②推文编辑弹窗展示活动列表 + 单条重提取 + 手动新增活动；③仪表盘"后端服务"和"连接检测"合并为"系统状态"卡片并上移；④配置中心移除 opencli 测试按钮；⑤博主支持 `max_notes_per_crawl` 抓取数量上限；⑥活动管理增加按博主筛选推文。
  - 结果：①`notes.py` 移除审核活动数量校验；②新增 `POST /notes/{id}/re-extract` 和 `POST /notes/{id}/activities` 端点，前端 ActivitiesView 编辑弹窗增加活动区域；③DashboardView 新增"系统状态"卡片整合后端健康 + opencli/登录/Chrome 检测；④SettingsView 移除 opencli 测试按钮；⑤`Blogger` 模型新增 `max_notes_per_crawl` 字段（migration 0017），`crawl_task` 截断超出上限的笔记，前端 SettingsView 新增"抓取上限"列；⑥`GET /notes` 新增 `blogger_id` 参数，前端 ActivitiesView 新增博主下拉筛选。
  - 验收：后端 `540 passed, 1 skipped`（+3 新 case），前端 `82 passed`（+3 新 case），build 通过。spec `docs/superpowers/specs/2026-08-03-note-edit-activities-re-extract-design.md`、`docs/superpowers/specs/2026-08-03-allow-review-without-activities-design.md`、`docs/superpowers/specs/2026-08-03-activities-blogger-filter-design.md`、`docs/superpowers/specs/2026-08-03-diagnostics-panel-design.md`。

- [x] 博主层错误纳入抓取熔断（stale page identity 等 CDP 异常自动停）
  - 目标：博主抓取出现 `Page not found: ... — stale page identity` 等 OpenCLI 异常时，任务不会傻跑下去；按 `consecutive_note_failure_limit` 阈值熔断 PAUSED，提示「CDP session / 浏览器标签页可能已过期」。
  - 验收：[crawl_task.py](file:///Users/kevin_w/Documents/github/xhs-info-crawl/backend/app/tasks/crawl_task.py) 博主循环把异常计入 `consecutive_failures`，达到阈值抛 `CrawlHalted`；成功时清零；`AuthenticationRequired`/`ExecutionStopped`/`ExecutionSuperseded` 不计入。后端 `518 passed, 1 skipped`（4 新 case：博主连续失败熔断/成功重置/`AuthenticationRequired` 不计入/阈值可配）；worker + beat 已重启（2026-08-03 09:19）。
  - 关联 spec：[2026-07-30-blogger-circuit-breaker-design.md](file:///Users/kevin_w/Documents/github/xhs-info-crawl/docs/superpowers/specs/2026-07-30-blogger-circuit-breaker-design.md)；测试 [test_blogger_circuit_breaker.py](file:///Users/kevin_w/Documents/github/xhs-info-crawl/backend/tests/test_blogger_circuit_breaker.py)。

- [x] 修复仪表盘与去重审核列表候选数不一致
  - 目标：`/api/v1/dashboard/summary` 的 `pending_duplicates` 与 `/api/v1/duplicates` 列表对得上；避免悬空 pending 候选（指向已 DELETED/MERGED 推文）让前端 `Promise.all` 整体 reject 导致列表空白。
  - 验收：后端 `/duplicates` 默认 join 过滤两侧 Note 可见（DELETED/MERGED）；`dashboard.summary.pending_duplicates` 同步同口径；新增 `scripts/prune_orphan_duplicates.py` 一次性脚本（已对生产 DB 跑：`scanned=4 pruned=1 kept=3`）；前端 `DuplicatesView.vue` 改用 `Promise.allSettled`，单侧 404 跳过本条而不是全失败；后端 514 passed / 1 skipped，前端 15 文件 / 76 tests。
  - 关联 spec：`docs/superpowers/specs/2026-07-30-duplicates-orphan-candidates-design.md`。
  - 实现：`backend/app/api/v1/duplicates.py`、`backend/app/api/v1/dashboard.py`、`backend/app/services/prune_orphan_duplicates.py`、`backend/scripts/prune_orphan_duplicates.py`、`frontend/src/views/DuplicatesView.vue`。
  - 测试：`backend/tests/test_duplicates_orphan.py`（4 case）、`backend/tests/test_prune_orphan_duplicates.py`（5 case）、`frontend/src/views/DuplicatesView.spec.ts` 加 "skips orphan pair without dropping the rest"。

- [x] 日志时间东八区显示 + 笔记连续失败熔断（2026-07-28 用户反馈）
  - 目标：①仪表盘「最近任务日志」、抓取日志页创建时间、日志抽屉时间显示的是 UTC（差 8h），要按东八区显示；②笔记处理连续失败时系统只记日志继续跑，要捕获这类系统性问题并把「扫码 / 中止」决策权交给用户。
  - 结果：①根因为 `created_at`/`started_at` 是 UTC naive 而前端直接渲染原始字符串；新增 `frontend/src/utils/datetime.ts formatUtcAsShanghai`（无 Z 按 UTC 解析 → Intl 转 Asia/Shanghai 墙钟），应用到仪表盘日志、TasksView 创建时间列、日志抽屉 timestamp、抓取趋势图 x 轴（原 `new Date(value)` 把 UTC 数字当本地时间，同样差 8h）；存储口径不变，`docs/database-design.md` 时间口径章节补显示侧约定。②新异常 `CrawlHalted`；`run_crawl` 主循环连续失败计数（成功含跳过即清零），达阈值 `consecutive_note_failure_limit`（env 可配，默认 3）熔断：任务 PAUSED + error_message 指引「检测登录并继续 / 结束抓取」+ 自动打开登录页（与未登录 PAUSED 同路径）；仪表盘 PAUSED 状态新增「结束抓取」按钮；`.env.example` 同步。
  - 验收：后端 `tests/test_consecutive_failure_halt.py` 4 用例先红后绿（熔断 PAUSED/计数清零/阈值可配/熔断后可停止）；前端 +7 用例（datetime 工具 4、TasksView 时间 2、DashboardView PAUSED 结束按钮 + 日志时间转换）；后端 505 passed、前端 75 passed、build 通过；commit `2e18c09`；spec `docs/superpowers/specs/2026-07-28-log-timezone-and-consecutive-failure-halt-design.md`。
  - 部署：改动 `app/tasks`/`app/services`/config，worker/beat 已于 2026-07-28 09:02 重启（确认无进行中任务后执行）。
- [x] 仪表盘与周报需求偏差对齐（原待办 #11，用户拍板方案 A 轻量版）
  - 目标：仪表盘补本周统计卡片（修正 `weekly_notes_count`/`weekly_activities_count` 口径为本周）+ 最近 5 条任务日志；周报补 `DELETE /reports/{id}` 与 Markdown 渲染预览。4 周趋势明确不做（与现有抓取折线图重合）。
  - 结果：`dashboard.py` summary 加 `_iso_week_start_utc_naive()`（北京周一 00:00 换算 UTC naive），两个 weekly 计数从全量改为 `created_at >= week_start`（原名不副实）；新增 `recent_logs`（TaskLog id desc 取 5）。`reports.py` 新增 `DELETE /{report_id}`（不存在 404，周报无磁盘文件只删 DB 行）。前端：DashboardView 三张统计卡片（本周抓取笔记/本周生成活动/待审核去重）+「最近任务日志」卡片（级别标签+点击跳任务日志页，空态占位）；ReportsView 操作列加删除按钮（ElMessageBox 二次确认）、预览从纯文本改为 marked+DOMPurify 渲染 HTML（`{ async: false }` 同步解析 + sanitize）；新依赖 marked/dompurify/@types/dompurify。
  - 验收：后端 `test_dashboard_alignment.py` 3 用例先红后绿（周口径分流/recent_logs 最新 5 条/DELETE 200→404 幂等）；前端 +4 用例（ReportsView 删除+预览渲染、DashboardView 统计卡片+日志导航+空日志占位）；后端 501 passed、前端 68 passed、build 通过；commit `55d3679`；spec `docs/superpowers/specs/2026-07-27-dashboard-and-report-alignment-design.md`。
- [x] TODO/文档卫生（原待办 #12，含「城市去重」条目核实）
  - 目标：`docs/api-doc.md` 补 keyword-groups、poster、notes 系列端点；`dedupe_cities.py` 位置与 spec 对齐并核实"城市去重"条目的勾选状态。
  - 结果：以 `app.openapi()` 枚举 59 端点做差集，api-doc 补齐 dashboard/analytics、health、tasks/batch DELETE、keyword-groups×6、blogger-groups×5、博主导入/enrich×3、opencli/config、poster-templates×6、poster-tasks×8、posters 图片×2、schedules×4、notes reprocess、settings/{kind} 泛型说明；修正不存在的 `GET/PUT /settings/opencli` 为 `/opencli/config`；`batch/approve`（skipped 明细）与 `merge`（409）语义同步 TODO#7 实现。dedupe spec 位置行更正为 `backend/app/scripts/dedupe_cities.py`（改文档不改码）。「城市去重」条目核实达标并打勾：0013 上线前已跑脚本、生产库重名数 0、`ix_cities_name_unique` 唯一索引（模型层自 #9 同步声明）使重名不可能再产生；`test_dedupe_cities_script.py` 7 用例绿。
  - 验收：覆盖自查脚本确认 59 端点全部可检索（4 个初始缺失中 2 个为 `:id`/`{id}` 归一化误报、已补泛型说明）；后端 498 passed（文档改动无回归）；commit `55b0487`；spec `docs/superpowers/specs/2026-07-27-docs-hygiene-design.md`。
- [x] 测试脆弱性修复（原待办 #10）
  - 目标：`test_render_with_mocked_opencli` 补 mock `shutil.which`（无 opencli 机器不再 503）；`PostersListView.spec` 修 router mock 未捕获错误。
  - 结果：后端用例 `opencli` 返回假路径、`python3` 等透传真实 which（Popen http.server 仍需真解释器），长期唯一失败用例转绿；前端 `factory()` 注入 `$router.push` spy，「navigates to wizard」断言 `push('/posters/new')`，Vitest `Errors 1` 归零。
  - 验收：后端全量 **498 passed 零失败**（该 poster 用例首次不再占坑）；前端 64 passed 零未捕获错误；commit `82a9ec9`；spec `docs/superpowers/specs/2026-07-27-test-fragility-fixes-design.md`。
- [x] 配置与迁移盲区（原待办 #9）
  - 目标：`.env.example` 补 `INITIAL_ADMIN_PASSWORD`、`MINIMAX_VISION_MODEL`；`alembic env.py` 与 `init_database` 的 models import 补 `keyword_group`、`blogger_city`、`poster`。
  - 结果：①`.env.example` 补两项，`ADMIN_USERNAME`/`ADMIN_PASSWORD` 过期条目（全仓库无消费）替换为 `INITIAL_ADMIN_PASSWORD` 说明；②`init_database` import 对齐 env.py 全量 13 模块（env.py 本就完整，TODO 该项过时）；③**测试实证新发现**：0001 用 `Base.metadata.create_all` 按运行时当前模型建表，空库 upgrade head 在 0002 撞列崩溃——0002–0016 全部加幂等守卫（0008 回填 UPDATE / 0011 删 status 列 / 0013 数据迁移按旧 schema 条件执行）；④**autogenerate 实证新发现**：`cities.name` 唯一索引（0013 建、生产库在）模型未声明，`City.__table_args__` 补 `Index("ix_cities_name_unique", unique=True)` 后零 diff；dedupe_cities 测试加 DROP INDEX fixture 模拟旧 schema。
  - 验收：`tests/test_config_migration_blindspots.py` 3 用例先红后绿（子进程裸 init_database 全表 / env 覆盖 / upgrade head 全表）；`alembic revision --autogenerate` 实测 `upgrade(): pass` 零 diff；全量 497 passed（仅剩已知 poster 环境用例）；commit `16cfe7e`；spec `docs/superpowers/specs/2026-07-27-config-and-migration-blindspots-design.md`。
- [x] poster 图片路径校验统一 + notes 列表异常吞噬（原待办 #8）
  - 目标：`poster_tasks.py note_image_by_id` 的 `str.startswith` 校验可被同前缀兄弟目录绕过，统一改 `Path.is_relative_to`；`notes.py` OCR 聚合 try/except 吞异常改为记 WARNING 日志。
  - 结果：`note_image_by_id` 改 `target.is_relative_to(base)`（与 `get_note_image` 口径一致），`/data-evil` 类同前缀逃逸返回 404；OCR 聚合失败记 `logger.warning`（含 note_ids 与异常），响应仍降级 200 不拖垮列表。
  - 验收：`tests/test_poster_path_and_ocr_logging.py` 3 用例（路径穿越 + OCR 日志 2 个先红后绿，正常文件回归 1 个直接绿）；全量 494 passed（仅剩已知 poster 环境用例）；commit `c7b7d1c`；spec `docs/superpowers/specs/2026-07-27-poster-path-and-ocr-logging-design.md`。
- [x] 审核规则/幂等/关联清理一致性修复包（原待办 #7）
  - 目标：①`/notes/batch/approve` 与单条 review 一样校验至少 1 条有效子活动；②`/duplicates/{id}/merge` 对非 pending 候选返回 409；③删除 Blogger 清理 `blogger_cities`、删除 City 清理 `blogger_cities`/`keyword_group_cities`；④统一 `Activity.start_time` 与 `published_at` 时区口径（二选一，写进 `docs/database-design.md`）。
  - 结果：①批量审核按单条同规则校验，无有效子活动的 id 跳过并在响应新增 `skipped` 明细（WARNING 日志），不整批 422；②merge 入口非 pending 即 409「该候选已处理，不能重复合并」；③`delete_city` 级联清 `Keyword`+`BloggerCity`+`KeywordGroupCity`，`delete_setting(bloggers)` 级联清 `BloggerCity`+`BloggerGroupMember`，同事务回滚；④口径定为**北京墙钟 naive**——经任务 #19 真实数据与 SQLite 绑定行为实证：SQLite DateTime 存取均丢 tzinfo 只留墙钟数字，真 bug 只有 DOM 解析路径 `.astimezone(utc)` 落库比雪花路径晚 8h；`parse_published_at` 各分支与 `note_id_published_at` 改返回 Asia/Shanghai（落库值不变，零迁移），`week_bounds` 与 notes/activities 日期过滤边界去 tzinfo 改 naive，口径写入 `docs/database-design.md`「2026-07-27 时间口径约定」。
  - 验收：`tests/test_review_consistency.py` 11 用例（9 先红后绿 + 2 过滤回归）；`test_published_at_parser.py`/`test_note_id_published_at.py` 预期按新口径更新；全量 491 passed（仅剩已知 poster 环境用例，TODO#10 登记）；commit `7d56681`；spec `docs/superpowers/specs/2026-07-27-review-consistency-fixes-design.md`。
- [x] 活动级 `duplicate_candidates` 死数据处置（原待办 #5，方案 A：停写+清理）
  - 目标：`create_duplicate_candidates` 每次抓取写入活动级候选（生产库 1160 行），无任何 API/UI 消费。去重已收敛推文维度，用户 2026-07-27 拍板方案 A：停写 + 一次性清空存量。
  - 结果：crawl_task 删除写入调用；dedup.py 删 `create_duplicate_candidates` 及专用导入；推文级 `create_note_duplicate_candidates` 不变；幂等脚本 `scripts/cleanup_duplicate_candidates.py`；模型与空表保留（避免破坏性迁移，过期活动清理联动仍有效）。
  - 验收：`tests/test_duplicate_candidates_stop.py` 3 用例先红后绿；全量 480 passed；生产库备份 `data/backups/app-20260727-184934.db` 后清零（1160→0），note 级 4 行保留；worker/beat 已重启（18:49）；commit `eeb7482`；spec `docs/superpowers/specs/2026-07-27-stop-activity-duplicate-candidates-design.md`。
- [x] 死代码清理（原待办 #6，含一个潜在 NameError）
  - 目标：清理 `services/crawler.py` 旧函数式实现、`services/report.py` 旧活动级导出（含 `generate_markdown:39` 未导入 `datetime` 的 NameError 地雷）、`pipeline.process_with_isolation`、`services/task_lock.py`、`reports.py select_activities`、未使用导入、`poster_tasks.py` 空 `pass` 块、`tasks.py` 不可达分支、`notes.py` 重复 import；引用它们的测试随之迁移或删除。
  - 结果：crawler.py 仅保留 4 异常类 + `is_verification_required`；pipeline 删 `process_with_isolation`；task_lock.py 整模块删除；report.py 删 `generate_markdown`/`generate_xlsx`/`visible_activities`（保留被 note 级引用的 `format_activity_markdown`/`_activity_lines`，删码阶段实证修正边界）；reports.py 删 `select_activities`；清理 7 处未使用导入 + 3 处杂项；测试删 13 个死代码用例，新增 `test_dead_code_cleanup.py` 静态断言 10 项（先红后绿）。
  - 验收：后端全量 479 passed（仅剩已知 poster 环境用例）；纯删除无行为变化；commit `cee2281`；spec `docs/superpowers/specs/2026-07-27-dead-code-cleanup-design.md`。
  - 部署：worker/beat 已随提交后重启生效。
- [x] 未登录识别 + 任务启动登录预检（原待办 #13）
  - 目标：未扫码登录时 whoami 挂起 60s 被误记为博主抓取失败（任务 #19 实证）。改为：`check_login` 把 whoami 超时归类为 `AuthenticationRequired`；任务启动做真实登录预检，未登录直接 PAUSED 并提示扫码；PAUSED 时自动打开登录页。
  - 结果：`OpenCLIAdapter.check_login` 捕获 `OpenCLITimeout` 改抛 `AuthenticationRequired`（含「扫码」指引）；`crawl_task` 启动真实预检（替换假日志），未登录零发现损耗直接 PAUSED；PAUSED 分支对全部 `AuthenticationRequired` 统一 `open_xhs_login` 自动打开登录页；12 个 FakeAdapter 补 `check_login`。
  - 验收：`tests/test_login_preflight.py` 4 用例先红后绿；后端 479 passed（仅剩已知 poster 环境失败）；commit `91923f3`；spec `docs/superpowers/specs/2026-07-27-login-preflight-auth-pause-design.md`。
  - 部署：2026-07-27 17:43 随 #14 手动执行完成，worker/beat 已重启（新 PID 9839/9840），登录预检已生效。
- [x] 博主链接发布时间解析错误修复（原待办 #14，取了用户 ID 而非笔记 ID）
  - 目标：`note_id_published_at` 对 `/user/profile/<uid>/<noteid>` 链接取第一个 24hex（用户 ID），解出的是博主注册时间（任务 #19 实证：15 篇全是 2021-09-18）。改为取路径中最后一个 24hex（笔记 ID）；存量数据写幂等脚本矫正。
  - 结果：函数剥离 query 后只在 path 中匹配并取最后一个 24hex；新增 profile URL / query 干扰两个定向用例（先红后绿，共 7 用例）；幂等矫正脚本 `scripts/fix_published_at_profile_url.py`（dry-run 66 行待矫正，其余 147 行历史值本就正确）。
  - 验收：后端 481 passed（仅剩已知 poster 环境失败）；commit `4b03d56`；spec `docs/superpowers/specs/2026-07-27-note-id-published-at-profile-url-design.md`。
  - 部署：2026-07-27 17:43 手动执行完成——任务 #19 STOPPED → 备份 `data/backups/app-20260727-174239.db` → worker/beat 重启（新 PID 9839/9840）→ 矫正 104 行（dry-run 与正式一致）→ 验证通过。剩余 3 篇 <2026 为笔记 ID 解码证实的真老笔记（2024-10/2025-08/2025-11），非漏网。守望定时任务 `automation_90d49c7b` 已禁用（用途由手动执行替代）。
- [x] OPENCLI_BIN 配置化 + 任务启动预检（根治 opencli PATH 依赖）
  - 目标：适配器硬编码 'opencli' 依赖 worker PATH；2026-07-27 定时任务因 worker 重启环境缺 nvm bin 导致 17 个博主全部 Errno 2。加 `opencli_bin` 配置、Popen FileNotFoundError 转可读 OpenCLIError、run_crawl 启动预检 fail-fast。
  - 结果：`Settings.opencli_bin`（env `OPENCLI_BIN`，默认 "opencli"）；适配器用 `self._bin` 调 Popen，FileNotFoundError 转成含 bin 路径与修复指引的 `OpenCLIError`；`run_crawl` claim 后预检 `find_opencli`（shutil.which 薄封装），找不到直接 FAILED + 指引报文 + ERROR 日志，不进搜索循环、不消耗配额；conftest 新增 autouse fake 预检 fixture；本机 `.env` 已配置 nvm 绝对路径，此后任何 shell 重启 worker 均可解析。
  - 验收：`tests/test_opencli_bin.py` 5 用例先红后绿；后端 475 passed（仅剩已知 poster 环境失败）；`.env.example` 与 `docs/crawler-design.md` 同步；worker/beat 已重启（PID 93778/93783）。
  - 关联：spec `docs/superpowers/specs/2026-07-27-opencli-bin-config-and-preflight-design.md`。
  - 附带处置：重启时误中断真实任务 #19（RUNNING 孤儿），已标记 STOPPED 并写 WARNING 日志，可在仪表盘"继续抓取"恢复；其博主报错 `user store was not found` 是 opencli 搜不到对应账号的数据问题，与环境无关，待逐个人工核实账号名。
- [x] 4. 抓取频率控制落地（SPEC P1）
  - 目标：`search_interval_min/max`（10-15s）与 `weekly_search_limit`（500/周）配置存在但零引用。关键词搜索之间按随机间隔 sleep；周搜索量超限记录 WARNING 并跳过。
  - 结果：新服务 `app/services/search_rate_limit.py`（`SearchRateLimiter` 任务内首次不等、之后 uniform(min,max)；`iso_week_key` Asia/Shanghai ISO 周；`weekly_search_count`/`increment_weekly_search`）；新表 `search_usage`（migration `0016`，week_key unique 全局跨任务累计，每次 search_recent 成功后 +1）；`crawl_task.rate_limit_sleep` 0.5s 分片可中断（每片过执行栅栏，stop 0.5s 内响应）；`run_crawl` 两个关键词循环统一走 `throttled_search` 闸门：超限 WARNING + 跳过剩余搜索、任务仍 COMPLETED，博主抓取不受限；conftest 新增 autouse fixture 默认把 rate_limit_sleep 置 no-op（既有测试不被真实 sleep 拖慢）；`.env.example` 注释与 `docs/crawler-design.md` 同步语义。
  - 验收：`tests/test_search_rate_limit.py` 5 个 + `tests/test_crawl_rate_limit.py` 3 个（先红后绿）；migration 0016 临时库 upgrade/downgrade 通过；后端 470 passed（仅剩已知 opencli 环境敏感失败）；生产库 stamp 0016（uvicorn create_all 已先行建表）。
  - 关联：spec `docs/superpowers/specs/2026-07-25-crawl-rate-limit-design.md`。
  - 注意：改动 `app/tasks/*.py`、`app/services/*.py` 与 models，worker/beat 已于 2026-07-27 重启（同时修复 opencli PATH 问题）。
- [x] 重启 celery beat 与 worker 加载新代码
  - 目标：beat PID 11974 是 7/17 启动持有旧任务调度；worker PID 50229 是 7/20 启动，早于 0013/0014 迁移（关键词组、海报模型）。服务进程管理已写进 AGENTS.md，beat/worker 都要遵循。
  - 结果（2026-07-25）：确认无进行中任务后停掉旧进程（11970/11974、50225/50229），以相同命令后台重启（日志 `data/logs/celery-worker.log`、`celery-beat.log`）；生产库因 uvicorn create_all 已先行建表，`alembic stamp 0015` 对齐版本；实测 beat 日志 `Scheduler: Sending due task scheduled-crawl-dispatch`、worker 接收并 succeeded。
  - 验收：两进程启动时间为今日；beat 使用最新 dispatcher 代码路径。
- [x] 2. 定时任务调度页 + 博主分组（吸收原"Beat 每周定时抓取真正生效"）
  - 目标：左侧 nav 新增"定时任务"页。子栏位一：定时任务 CRUD——每周几+时间、城市、关键词组、白名单（博主）组；语义：有关键词抓关键词、有白名单抓白名单、都有都抓。子栏位二：关键词组与博主组的配置（博主组为新实体），可被栏位一选择。Beat 由静态 ping 改为 DB 驱动的每分钟 dispatcher。
  - 结果：migration `0015_scheduled_crawls_and_blogger_groups` 建 `blogger_groups`/`blogger_group_members`/`scheduled_crawls`（upgrade/downgrade/re-upgrade 验证通过）；新模型 `models/schedule.py`、`models/blogger_group.py`；`/settings/blogger-groups` CRUD（重名 409、成员全量替换、删除级联）；`/schedules` CRUD（day_of_week 1-7/hour 0-23/minute 0-59 越界 422、城市与组校验、两组皆空 422「请至少选择一个关键词组或博主组」）；`app.tasks.crawl_task.scheduled_dispatch` 每分钟由 beat `scheduled-crawl-dispatch` 触发：slot（%Y-%m-%dT%H:%M）幂等、有 PENDING/RUNNING/STOP_REQUESTED 任务跳过、博主组展开为组内 enabled 博主 ∩ 城市 enabled 博主、recent_filter 缺省回退城市配置；前端 `SchedulesView.vue`（/schedules，nav Timer 图标）两 tab——定时任务表格/对话框 + 分组管理（复用 KeywordGroupSettings + 新 BloggerGroupSettings）；`alembic env.py` 模型 import 补齐。
  - 验收：新增后端测试 25 个（test_blogger_group_api 5 / test_schedules_api 5 / test_scheduled_dispatch 6 / test_dashboard_analytics 7 / test_celery_config 同步）先红后绿；后端 462 passed（仅剩已知 opencli 环境敏感失败）、前端 64 passed、build 通过。
  - 关联：spec `docs/superpowers/specs/2026-07-25-scheduled-crawls-and-dashboard-charts-design.md`。
  - 注意：改动涉及 models、`app/tasks/*.py`，**必须重启 celery worker 与 beat 后生效**（见待办"重启 celery beat 与 worker"）。
- [x] 3. 仪表盘抓取统计（定时任务状态 + 折线图 + 饼图）
  - 目标：仪表盘展示各定时任务最近一次抓取的成功/失败状态；折线图 x=抓取时间、y=抓取数量（发现/成功/失败）；饼图统计抓取成功率。
  - 结果：`GET /dashboard/analytics` 返回 recent_tasks（最近 20 次倒取正排，含 source=scheduled/manual、schedule_name）、status_counts（最近 50 次状态分布，未知状态归 OTHER）、schedules（含 last_task，Python 过滤 params.schedule_id 避免 SQLite json 方言绑定）；前端引入 echarts，新增 `CrawlTrendChart.vue`（发现/成功/失败三线，x=MM-DD HH:mm）与 `CrawlSuccessPie.vue`（环形饼图，成功/部分成功/失败/已停止/其他）封装 init/resize/dispose；DashboardView 新增「定时任务状态」卡（周期、启用、最近状态标签，空态引导）与两图表卡；analytics 随 3s 轮询刷新。
  - 验收：DashboardView.spec 新增 2 个用例（状态卡+图表容器渲染、空态占位），vi.mock('echarts')；前端 64 passed、build 通过。
  - 关联：同上分 spec。

- [x] 1. 修复关键词组在 `/tasks/crawl` 被静默丢弃（端到端断链）+ 归档按城市/周分目录
  - 目标：前端 DashboardView 提交 `keyword_group_ids`，后端 `CrawlIn` 无该字段被 pydantic 丢弃（已实证）：仅选组 → 422；组+博主 → 组被忽略只抓博主。`resolve_effective_keywords` 的组分支因 `model_dump()` 恒含 `keywords` 键不可达。用户补充语义（2026-07-25）：只选城市+关键词组 → 只抓关键词；只选博主 → 只抓博主；都选都抓；city 与 recent_filter 必填；归档按城市和周分目录。
  - 结果：`CrawlIn` 新增 `keyword_group_ids`，`recent_filter` 改必填；入口校验组必须存在/启用/挂在当前城市（422）；`resolve_effective_keywords` 改为"键存在即意图"：显式词 ∪ 组并集，键缺省才回退城市配置（显式空列表 = 禁用该维度的旧语义保留）；归档目录改为 `archive/{city_code}/{ISO 年}-W{周}/task-{id}/`（`archive.py` 新增 `iso_week_folder_name`，`crawl_task`/`activity_cleanup` 同步，清理脚本兼容新旧两种目录深度）；`docs/crawler-design.md` 同步。
  - 验收：新增 `tests/test_crawl_keyword_groups_api.py` 8 个用例（先红后绿）；既有 `test_crawl_scope_unit`/`test_tasks_api_scope`/`test_config_task_duplicate_api`/`test_crawl_auto_stop_previous`/`test_crawl_execution_ownership`/`test_activity_cleanup`/`test_multi_activity_archive` 同步后全绿；后端 439 passed（仅剩已知的 opencli 环境敏感失败）、前端 57 passed、build 通过。
  - 关联：spec `docs/superpowers/specs/2026-07-25-crawl-scope-and-archive-layout-design.md`。
  - 注意：改动涉及 `app/tasks/*.py` 与 `app/services/*.py`，需重启 celery worker 与 beat 后生效（见待办"重启 celery beat 与 worker"）。

- [x] 仪表盘 `last_task.error_message` 仅在任务进行中或失败时显示
  - 结果：`DashboardView.vue` 加 `errorVisibleStatuses = ['RUNNING','STOP_REQUESTED','FAILED','PAUSED','STOPPED']` 与 `shouldShowLastTaskError` computed 属性；`ElAlert` 改 `v-if="shouldShowLastTaskError"`。
  - 验收：前端 48 passed（DashboardView 加 3 测试 case：COMPLETED_WITH_ERRORS 不显示 / FAILED 显示 / RUNNING 显示），`npm run build` 通过。
  - 关联：spec `docs/superpowers/specs/2026-07-21-dashboard-error-message-conditional-design.md`。

- [x] 列表接口 OCR 摘要聚合性能与长度保护
  - 结果：`_summary` 内部先按 OCR 块数截到 `MAX_OCR_BLOCKS=5`，再按 UTF-8 字节截到 `MAX_SUMMARY_BYTES=4096`；保留字符边界；每行返回 `summary_truncated: bool`。详情接口 `_detail_data` 不受影响（详情仍返回全部 OCR）。
  - 验收：后端 309→314 passed（`tests/test_note_summary.py` 5 个 case 含超 4 KiB 截断 + truncated 标志）。
  - 关联：spec `docs/superpowers/specs/2026-07-21-note-summary-length-guard-design.md`。

- [x] 回答"去重是按什么去的"以及给抓取日志页加批量删除
  - 结果：Q&A 文档 `docs/superpowers/qa/dedup-rules.md` 解释当前 dedup 两层（硬键 platform_note_id 自动去重 + 软键 SequenceMatcher 相似度入候选）；后端新增 `DELETE /api/v1/tasks/batch` 接 `{ids:number[]}`，清理对应 `CrawlTask` 与 `TaskLog`；前端 `TasksView.vue` 加 selection 列 + "批量删除 (N)" 按钮 + ElMessageBox 确认 + Toast 反馈；`api.client.ts` 加 `batchDeleteTasks`。
  - 验收：后端 309 passed（新增 4 个 case：删 2 条 / 未知 id 422 / 空列表 422 / 超 100 422）、前端 45 passed（新增 selection-change 触发 + batchDeleteTasks 调用）、前端 build 通过。
  - 关联：spec `docs/superpowers/specs/2026-07-21-tasks-batch-delete-design.md`、测试 `backend/tests/test_tasks_batch_delete.py`。
- [x] 活动管理支持关键字搜索
  - 结果：后端 `list_notes` 加 `keyword: str | None` 参数，对 `Note.title` 与 `Note.content` 做 `ilike` 模糊匹配（strip 后为空不写条件）；前端 `ActivitiesView.vue` 工具栏加 `<ElInput v-model="filters.keyword">`，`queryParams` 透传；resetFilters 也清空 keyword。
  - 验收：后端 305→309 passed（`tests/test_notes_api.py` 加 4 个 keyword case）、前端 44→45 passed（`ActivitiesView.spec.ts` 加 2 个 case）、build 通过。
  - 关联：spec `docs/superpowers/specs/2026-07-21-activities-keyword-search-design.md`。
- [x] 周报 picker 与 ISO 提示及按周排序的改动回滚
  - 结果：`frontend/src/views/ReportsView.vue` 维持 `form.weekDate = new Date()` + `format="YYYY 第 ww 周"`，无 `sortedRows` / `weekRangeLabel`；spec 文件 `2026-07-21-reports-list-order-by-week-design.md` 与 `2026-07-21-reports-picker-expose-iso-week-design.md` 作为存档保留。
  - 验收：ReportsView 与 git HEAD 一致；ReportsView.spec 仅 2 个原始测试；前端 42 passed；build 通过。
- [x] 推文列表"发布时间"列只显示 YYYY-MM-DD（无时分秒）
  - 结果：`ActivitiesView.vue` 新增 `formatDate(value)` 函数（`.toISOString().slice(0, 10)`），"发布时间" 列改用 `formatDate`；详情识别活动表格的 `start_time` / `end_time` 仍用 `formatTime`。
  - 验收：`ActivitiesView.spec.ts` 加 "shows YYYY-MM-DD only" 测试全绿；前后端测试全过、build 通过。
  - 关联：spec `docs/superpowers/specs/2026-07-21-list-publish-time-date-only-design.md`。
- [x] 从小红书 note ID（ObjectID 24 hex）解析推文发布时间
  - 结果：`backend/app/services/note_id_published_at.py` 实现 `note_id_published_at(note_id_or_url)`（正则抽取 24 hex → 前 8 hex → int → +8h → UTC ISO datetime）；`backend/scripts/backfill_note_id_published_at.py` 一次性回填脚本（扫描 `published_at IS NULL` 且 24 hex platform_note_id 的记录）；`crawl_task.process_note` 入库前调 `note_id_published_at(source_url)` 作为最高优先级，回退 DOM 解析。
  - 验收：`backend/tests/test_note_id_published_at.py` 3 个 case 全过；回填脚本输出 before/after 计数且幂等。
- [x] 识别活动表格增加「开始时间」与「结束时间」两列
  - 结果：`ActivitiesView.vue` 详情 dialog 加 `<ElTableColumn label="开始时间">` 与 `label="结束时间">` 两列，使用 `formatTime`；缺值显示 "待确认" 或 '-'。
  - 验收：`ActivitiesView.spec.ts` 表格列断言包含 4 列（名称 / 地点 / 开始时间 / 结束时间 / 操作）。
  - 关联：spec `docs/superpowers/specs/2026-07-21-list-publish-time-date-only-design.md` 中已包含此改动。
- [x] 撤回推文列表的 OCR 摘要列
  - 结果：`ActivitiesView.vue` 推文列表移除"摘要" ElTableColumn；OCR 内容只在详情以"识别活动列表" + 图片 OCR block 呈现；后端 `_summary` 字段保留供详情使用。
  - 验收：`ActivitiesView.spec.ts` 详情断言中保留 `summary` 字段；推文列表断言不再包含 OCR 长文。
  - 关联：spec `docs/superpowers/specs/2026-07-21-note-summary-with-ocr-design.md`（列表调用方变种）。
- [x] 历史 `Note.published_at` 回填
  - 结果：`backend/scripts/backfill_note_id_published_at.py` 已实现并已验证回填效果；按 24 hex note ID 前 8 位 hex = epoch 秒的方案执行，剩余少量未充填由运行时 `app.services.published_at.parse_published_at` 兜底。
  - 验收：脚本已执行；`notes.published_at IS NULL` 计数已从 177 大幅下降。
- [x] 历史 APPROVED 且 0 子活动推文的处理（已由 `POST /notes/{id}/reprocess` + 前端批量重处理入口覆盖）
  - 结果：`backend/app/api/v1/notes.py` 已实现 `/notes/{id}/reprocess` 端点；当前测试环境下无 "0 子活动但 APPROVED" 的历史脏数据；后续人工可以单条触发或通过 `/notes/batch/approve` 取消误改。
- [x] 修复worker在opencli阻塞时无法响应停止信号的问题
  - 结果：缩短 OpenCLI 调用超时（60 秒），`task_registry.kill()` 立即发送 SIGKILL。`backend/tests/test_worker_stop_during_block.py` 4 个全过。
- [x] 点击开始抓取时自动停止上一个任务（不报错 TASK_IN_PROGRESS）
  - 结果：见 spec `docs/superpowers/specs/2026-07-18-crawl-auto-stop-previous-design.md`；`backend/tests/test_crawl_auto_stop_previous.py` 4 个全过。
- [x] 移除推文内子活动的审核状态
  - 结果：删除 `Activity.status` 列与索引，新增 `deleted_at` 表达软删除；周报收录完全基于推文维度（`Note.review_status` + `Note.published_at`），不再过滤子活动状态；`POST /api/v1/activities/batch/approve` 返回 `410 Gone`；前端列表"识别活动"表格移除"状态"列。
  - 验收：后端 `296 passed, 1 skipped`、前端 `40 passed`、前端构建成功、Playwright `42 passed`。
  - 关联 spec：`docs/superpowers/specs/2026-07-21-remove-activity-approval-status-design.md`；迁移：`backend/migrations/versions/0011_activity_soft_delete.py`；E2E：`tests/test-activity-soft-delete-and-report-include.md`。
- [x] 解析并使用小红书真实发布时间
  - 结果：新增 `app/services/published_at.py`，解析 OpenCLI 详情字段与页面文字（绝对日期、`MM-DD`、`N天前/N小时前/分钟前`），统一 Asia/Shanghai 解析后转 UTC；`process_note` 入库时自动回填 `Note.published_at`；列表筛选、周报归周取消 `func.coalesce(published_at, created_at)`；前端"发布时间"列不再回退 created_at；缺少时显示"待确认"且不进周报。
  - 验收：后端、前端、E2E 全绿（同上）。
  - 关联 spec：`docs/superpowers/specs/2026-07-21-parse-real-published-at-design.md`；E2E：`tests/test-parse-real-published-at.md`。
- [x] 修复零活动推文仍标记处理完成并可审核的问题
  - 结果：新增 `app/services/activity_validator.py`，按 `activity.start_time >= note.published_at` 判定（OCR 错识过滤）；区分 `all_before_publish` / `minimax_empty_retryable` / `no_activity_signals` 三态；`process_note` 用 validator 替代旧 ActivityWindow 60 天窗口；`POST /notes/{id}/review` 审批通过校验至少 1 条未删除子活动；新增 `POST /notes/{id}/reprocess` 端点清空子活动重新走抓取。
  - 验收：后端、前端、E2E 全绿（同上）。
  - 关联 spec：`docs/superpowers/specs/2026-07-21-zero-activity-and-window-fix-design.md`；E2E：`tests/test-note-zero-activity-and-window.md`。
- [x] 活动管理列表的摘要列展示 OCR 文字与日期
  - 结果：列表接口 `_summary` 拼接 `Note.content` 与所有图片 OCR 文字（`正文：<content>` + `[图片 N OCR] <text>`），按 `NoteImage.id` 排序；前端 `ActivitiesView` 新增"摘要"列，`show-overflow-tooltip` 悬浮完整内容；缺失部分跳过不写占位。
  - 验收：后端、前端、E2E 全绿（同上）。
  - 关联 spec：`docs/superpowers/specs/2026-07-21-note-summary-with-ocr-design.md`。
- [x] 补全推文编辑与单条审核闭环
  - 结果：新增推文更新与单篇审核 API；活动管理列表和详情均支持编辑标题、正文、城市、发布时间及单篇通过/驳回，原文链接只读，批量通过保持兼容。
  - 验收：后端 `246 passed, 1 skipped`；前端组件串行全量 `11 files / 38 tests passed`；前端构建成功；E2E 完整首轮 `41 passed`，唯一旧选择器回归修正后关联专项 `4 passed`。
  - 关联 spec：`docs/superpowers/specs/2026-07-21-note-edit-single-review-design.md`；实现计划：`docs/superpowers/plans/2026-07-21-note-edit-single-review.md`；测试案例：`tests/test-note-edit-single-review.md`。
- [x] 识别小红书验证码/风控后暂停抓取、保留页面并等待人工验证
  - 结果：明确验证信号映射为 `VerificationRequired` 并进入 PAUSED；crawler 验证页保留，自动唤醒 Chrome；用户结束任务时主动关闭保留 session。
  - 验收：普通超时不误判，仪表盘复用人工恢复按钮；后端 `240 passed, 1 skipped`、前端 `32 passed`、构建成功、E2E `39 passed`。
  - 关联 spec：`docs/superpowers/specs/2026-07-20-xhs-verification-pause-design.md`；测试案例：`tests/test-xhs-verification-pause.md`。
- [x] 支持批量上传博主白名单
  - 结果：配置中心支持下载 Excel 模板并上传 xlsx/UTF-8 csv；按用户 ID、主页、名称幂等更新，只填写城市名称，整批校验后单事务写入。
  - 验收：支持行号错误、2 MiB/500 行限制、Element Plus loading/Toast；后端 `227 passed, 1 skipped`、前端 `31 passed`、构建成功、E2E `39 passed`。
  - 关联 spec：`docs/superpowers/specs/2026-07-20-blogger-batch-import-design.md`；测试案例：`tests/test-blogger-batch-import.md`。
- [x] 修复博主 `user/profile` 笔记 URL 的稳定身份识别与重复抓取唯一键冲突
  - 结果：统一身份函数严格识别 `/user/profile/<user-id>/<note-id>`，不同 token 得到同一 note ID；纯博主主页不误判。已处理笔记会刷新有效 URL 并跳过详情、下载及重复 INSERT。
  - 验收：身份与任务回归 `30 passed`；后端 `215 passed, 1 skipped`、前端 `28 passed`、E2E `38 passed`；任务 #7 真实记录只读核对通过。
  - 关联 spec：`docs/superpowers/specs/2026-07-20-user-profile-note-identity-design.md`；测试案例：`tests/test-user-profile-note-identity.md`。
- [x] 跑任务 #7 验证签名 URL，并隔离单博主发现失败
  - 结果：真实范围 `keywords=0 bloggers=5`；成功博主命中 15、15、15、13 篇，另一个博主解析失败后任务继续进入下载。
  - 验收：安全停止时发现 58、下载 2、OCR 2、提取 2；本轮 `Missing url` 和 `requires a full signed URL` 均为 0；后端 `212 passed, 1 skipped`、前端 `28 passed`、E2E `38 passed`。
  - 关联 spec：`docs/superpowers/specs/2026-07-20-blogger-discovery-resilience-design.md`；测试案例：`tests/test-blogger-discovery-resilience.md`。
- [x] 建立 TODO 持续执行授权
  - 结果：保留“先澄清根因、写 spec、TDD、全量验证、更新 TODO、独立提交”的流程；spec 完成后可按 TODO 顺序自动开发，不再逐项等待确认。
  - 例外：新增外部权限、敏感登录、不可逆操作或会改变产品方向的实质歧义仍需用户确认。
- [x] 停止执行栅栏、浏览器标签页清理与真实停止验收
  - 结果：业务 OpenCLI 命令在进程创建前、PID 登记后和子进程退出后校验执行权；stop API 先提交 `STOP_REQUESTED` 再 kill；crawler session 使用有界 `finally` 清理，Celery worker 保持运行。
  - 验收：后端 `210 passed, 1 skipped`、前端组件 `28 passed`、E2E `38 passed`；真实任务 `#15` 约 `0.25s` 进入 `STOPPED`，PID 注册表为空且 crawler 标签页关闭；不重启 worker，任务 `#16` 正常进入 `RUNNING / SEARCHING` 并可再次安全停止。
  - 关联 spec：`docs/superpowers/specs/2026-07-20-stop-execution-fence-browser-cleanup-design.md`；测试案例：`tests/test-stop-execution-fence-browser-cleanup.md`。
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
