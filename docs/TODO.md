# TODO

本文件是项目待办事项的唯一维护入口。新增需求、后续优化和技术债统一记录在这里；风险及应对措施见 [`risks-todos.md`](risks-todos.md)。

## 使用约定

- 使用 `- [ ]` 表示未完成，使用 `- [x]` 表示已完成。
- 新增事项应写明目标和验收条件，必要时补充关联文档或代码位置。
- 完成后移入"已完成"章节，不直接删除，便于追踪。
- 阶段二事项统一放在"阶段二：全量技术栈"章节。
- 用户已持续授权按本文件顺序自动推进：每项仍需 spec、TDD、验证和独立提交，但无需逐项等待 spec 确认；新增权限、敏感登录、不可逆操作或实质歧义除外。

## 当前待办

- [x] 推文 ID 雪花算法服务是什么，整个项目有用到算法的都整理出来写一份文档md
  - 结果：`docs/superpowers/qa/algorithms.md` 梳理项目所有算法位置（含 XHS 雪花、UUID v4、JWT HS256、Argon2、SequenceMatcher、Celery 文件 broker 等），每一项给出文件 / 触发点 / 入参出参 / 强度评估 / 阶段二待替换路径。
- [ ] 多账号体系 + RBAC（分组 + 权限）
  - 目标：当前只有 admin。升级为多账号平等（`Administrator` 组默认有全部权限），新增"账号管理"左侧 nav；账号可以分组、分组关联权限集；`sub` 角色划分保留为未来"子账号"扩展。
  - 验收：新 `users/groups/permissions/group_permissions/user_groups` 表；新 `AccountsView.vue`（左 nav 新增），含账号 / 分组 / 权限 三 tab；后端 `require_permission(code)` 替换 `require_admin`；前端 49+ 测试，build 通过；实操：用 admin 新建 editor 账号 → 限定权限 → editor 登录验证无权页面 403。
  - 关联：spec `docs/superpowers/specs/2026-07-21-multi-account-rbac-design.md`（已写）。
- [ ] 城市复用 + 关键词组一对多
  - 目标：城市 DB unique 约束；关键词组 `KeywordGroup` 实体（可挂多个城市、可包含多个关键词）；仪表盘关键词下拉改为多选关键词组；`crawl_scope.resolve_crawl_scope` 改写。
  - 验收：新 migration `0013_keyword_groups.py`；新 API `settings/keyword-groups` 与 `tasks/crawl {keyword_group_ids}`；旧字段 `keywords` 兼容保留；前端 `SettingsView` 增加关键词组 tab；后端 308+ 测试，前端 49+ 测试，build 通过。
  - 关联：spec `docs/superpowers/specs/2026-07-21-city-and-keyword-groups-design.md`（已写）。
- [ ] 城市去重（修复重复 city 行）
  - 目标：一次性脚本 `backend/scripts/dedupe_cities.py` 选最早启用的 City 为 canonical，把其它重复 name 行的关联迁移过去（notes/blogger_city/keyword_group_cities/crawl_tasks），删除多余行；幂等。
  - 验收：`tests/test_dedupe_cities_script.py` 3 个 case；生产 DB 跑完 `SELECT COUNT(*) FROM cities` 下降，城市下拉不再重复。
  - 关联：spec `docs/superpowers/specs/2026-07-21-dedupe-cities-design.md`（已写）。
- [ ] 重启 celery beat 加载新代码
  - 目标：当前 celery beat PID 11974 是 7/16 启动持有旧任务调度；服务进程管理已写进 AGENTS.md，beat 也要遵循。
  - 验收：检查 `ps aux | grep celery | grep beat` 启动时间 `<= 今日`；beat 日志中 `Scheduler: Sending due task` 使用最新代码路径。本项不需要代码改动，只需要 Agent 在 TODO 完成时主动停掉并重启 beat 进程。
- [ ] 一次性数据库迁移 `seed_admin` 启动后兜底管理员
  - 目标：当数据库完全为空（首次部署/重置）时，没有 admin 用户无法登录。当前 admin 凭据是手工 sql 新增。
  - 验收：迁移 `0012_seed_admin.py` 在 upgrade 时若 `users` 表为空则插入 admin 用户；密码来自环境变量 `INITIAL_ADMIN_PASSWORD`，未设置则使用 `Admin@123` 且 WARNING 提示"生产环境必须更改"；脚本幂等：若 admin 已存在则跳过。重置 db（删除数据文件后跑 alembic upgrade head）后能用默认密码登录。
- [ ] 列表接口 OCR 摘要聚合性能与长度保护
  - 目标：`GET /notes` 一次性 LEFT JOIN `NoteImage` 表所有图片行，单推文 100 张图触发 100 行 SELECT 加字符串拼接，列表渲染大体积下 N+1 不明显但单行体可能 MB 级别。
  - 验收：`tests/test_note_summary.py` 加测：推文有 50 张图片时 summary 字符串 ≤ 4 KiB；超长时省略截断并在 DB 注释/响应里附 `summary_truncated=True`；前端"摘要"列不出现"pre" + 大 body（前端 `show-overflow-tooltip` 兜底）；后台跑脚本性能测试：`SELECT COUNT(*) FROM notes WHERE LENGTH(summary)>4096` 应为 0。

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
