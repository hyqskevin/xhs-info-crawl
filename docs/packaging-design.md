# 打包设计文档

> **本文档是跨多次打包流程的硬约束总结。** 任何对 `scripts/package-*.sh` / `scripts/package-*.ps1` / `launcher/` / `.app/.env` 写入逻辑的改动，**必须**先对照本文档第 4 节「打包前 TDD 清单」逐项勾选。

## 1. 文档定位

- 顶层设计文档，与 `architecture.md`、`crawler-design.md` 同级
- 跨多次打包的"防回归"基线：每次更新 `.app` 后用户都期望"配置能保留" + "功能可用"，本文档约束这些期望
- 与 `docs/superpowers/specs/2026-08-10-one-click-packaging-design.md` 互补：spec 是单次变更的设计，本文是跨次变更的不变量

## 2. 完整历史问题清单（已发生，禁止重犯）

> 本节是跨多次打包装/启动器改动的真实踩坑全表，每条都来自 `git log` 实证。每条包含：触发 commit、问题描述、根因、防重犯约束、对应 spec（若有）。
>
> 任何人改动 `scripts/package-*.sh/ps1` / `launcher/*` 前，先扫本节相关条目。
>
> 历史 commit hash 路径：`git log --oneline -- scripts/package-* launcher/ docs/superpowers/specs/*packag* docs/superpowers/specs/*launcher*`

### §2.1 打包产物与体积

#### 问题 ①：打包产物冗余（v0.6.0 涨到 1.1G，v0.6.1 错误降到 221M，v0.7.0 修复到 ~1.1G）

- **触发 commit**：`c9e24dc chore(release): v0.6.0` 引入 OCR 选装依赖未排除
- **现象**：
  - v0.6.0：.app 1.1G、zip 338M（paddlepaddle 429M + opencv 171M + pandas 73M + modelscope 63M + numpy 35M ≈ 840M 全塞 venv）
  - v0.6.1：.app 221M、zip 70M（**过度减肥**：误把 paddlepaddle/paddleocr/paddlex 从 venv 移除，让用户点"下载安装 OCR"在线拉 ocr-addon zip——但 ocr-addon-3.7.0 release 从未存在过 → 用户 404 → OCR 完全不可用）
  - v0.7.0：.app 1.1G、zip 354M（**正确路径**：OCR Python 包打进 venv 作为运行时依赖；OCR 模型按需从 GitHub Release 拉）
- **根因（v0.6.1 错误）**：`scripts/package-macos.sh` 第 119-125 行删除 `pip install paddleocr paddlepaddle` + 没补"模型从哪里来"的设计 + `release-ocr-addon.yml` workflow 也没真跑过 → 用户拿到 .app 后 OCR 不可用
- **修复（v0.7.0）**：OCR Python 包必须打进 venv。OCR 模型按需从 GitHub Release `ocr-models-3.7.0-<os>-<arch>.zip` 拉
- **防重犯**：
  - venv 必须装 `requirements-runtime.txt`（含 `paddleocr` / `paddlepaddle` / `paddlex` / `opencv-contrib-python`）+ `launcher/requirements.txt`
  - OCR Python 包**必须**进 venv（不要"省体积"再次犯 v0.6.1 错误）
  - OCR 模型**不**进 .app，由 `launcher.ocr_installer.download_models` 下载到 `DATA_DIR/paddlex`
  - 静态检查：
    - `grep -E 'pip install paddleocr' scripts/package-*.sh scripts/package-*.ps1` 不应有非 -r 形式的 paddleocr 行（用 requirements 文件是允许的）
    - `backend/requirements-runtime.txt` 必须含 `paddleocr` / `paddlepaddle` / `paddlex`
  - 打包后**fail-fast 校验**（step 8.6）：任何 OCR 依赖缺失 → `exit 1`，不发不可用 .app
  - 关联 spec：`docs/superpowers/specs/2026-08-21-ocr-packaging-v0.7-design.md`

#### 问题 ㉙（v0.7.0）：OCR addon release workflow 存在但从未产出

- **触发**：v0.6.1 提交 `.github/workflows/release-ocr-addon.yml` + `scripts/package-ocr-addon.sh`，但用户从未打过 `ocr-addon-*` tag → release 不存在 → launcher UI "下载安装 OCR" 调 `get_addon_url("macos", "arm64", "3.7.0")` → 404
- **根因**：v0.6.1 设计让 ocr-addon release 与主 release 解耦，需要手动再打一个 tag——但流程没人推
- **修复**：v0.7.0 OCR 模型改走 release.yml 的 build-ocr-models job（每次主 release 都自动产出 ocr-models zip）

#### 问题 ㉚（v0.7.0+1）：打包版启动从不跑 alembic 迁移，新部署 / 升 v0.7.0 后业务表缺列导致 500

- **触发**：v0.7.0 发版后用户"4 个列表都没了"——首页报 500（`no such column: blogger_groups.min_likes` / `keyword_groups.excluded_words_json` / `scheduled_crawls.consecutive_failures`），全部是 0026/0027 引入的新列；现场 DB `alembic_version='0025'` 但代码已经 head=0027
- **现象**：打包版 `init_database()` 跑 `Base.metadata.create_all` —— 但 SQLAlchemy 对已存在表**不会补列**，只补新表；alembic 从未被启动调用过，0026/0027 列从未执行；任何 endpoint 走到这些列 → sqlite3.OperationalError 500
- **根因**：v0.6.x 设计"打包版从不执行迁移"（避免 alembic 解析整棵 importtree 拖慢启动），但代码继续迭代加列 → 部署版本永远落后于 alembic head
- **修复（v0.7.0+1）**：`init_database()` 在 `Base.metadata.create_all` 之后插入 `alembic.command.upgrade(cfg, "head")` 跑 pending migrations + `alembic.command.stamp(cfg, "head")` 兜底重置 version 行（应对项目历史 0001-0024 用 `Base.metadata.create_all` 不更新 `alembic_version` 的 bug）；失败 → 抛异常 → lifespan 让 uvicorn 退出非零 → launcher 弹"启动失败"
- **防重犯**：
  - 任何 backend PR 加列**必须**配 alembic migration（CI 检查 grep `op.add_column` ↔ `backend/migrations/versions/*.py`）；如 PR 漏 migration，集成测试会失败
  - 打包版启动顺序固定为 `create_all → upgrade head → stamp head → seed_default_admin`，禁止颠倒
  - 启动时 upgrade 抛异常 → fail-fast，绝不吞（吞会让用户拿到一个看上去在跑实际缺列的 .app）
- **关联**：spec `docs/superpowers/specs/2026-08-21-package-startup-auto-migrate-design.md`；测试 `backend/tests/test_database_init.py` 5 个用例

#### 问题 ㉜（v0.7.0+2）：老 Administrators 组权限绑不更新 → 前端 nav 菜单消失

- **触发**：用户 2026-08-22 反馈"系统配置的 llm 还是不展示，旧问题一直没修复"。前一段 v0.6.0 已修复 token permissions 含 11 条新码 + Administrators 绑 10 条码；但**老用户**（v0.5.x 升级）Administrators 组已存在 → `seed_default_iam` 第 92-104 行 `if admins is None` 跳过 → 始终没补 `'*'` → 老 token 不含 `*` 通配 + 不含 `settings:read`/`tasks:read` → 前端 `frontend/src/config/navPermissions.ts` 第 56 行 `topLevelPermission` 过滤掉配置中心 / 仪表盘 / 任务日志 三个顶级菜单
- **现象**：用户登入后看上去"4 个列表都没了"；又报告"系统配置里 LLM 模型选择不展示"——同根因
- **根因**：`seed_default_iam` 是"幂等首次 seed"实现，只在组不存在时建+绑权限；老组永远跳过权限绑
- **修复（v0.7.0+2）**：把"首次创建+绑"分支改为"创建或补全"两阶段：
  - `_ensure_group_has_all_permissions(session, group, *, include_wildcard=True)`：每次启动全 Permission.id 集合 - 已绑 permission_id 集合 = 差集 INSERT；**不删既有绑**（用户手动加的非标准码不会被清）
  - `_ensure_group_has_minimum_permission(session, group, code)`：保证 Viewers 至少绑 `users:read`
  - `seed_default_iam` Administrators + Viewers 都改"创建或补全"
- **防重犯**：
  - 新增/删除 Permission code 时，验收项必含"重启后老组的权限绑自动补齐"
  - 任何 builtin group（`is_builtin=True`）在 `seed_default_iam` 都走"补齐缺失"路径，不再用 `if group is None` 单分支
  - 现有 `.env.example` schema 字段加 SCHEDULE_* 写入文档，避免 doc-drift
- **关联**：spec `docs/superpowers/specs/2026-08-22-permission-rebind-admin-groups-design.md`；测试 `backend/tests/test_seed_default_iam_rebind.py` 6 个用例

#### 问题 ㉝（v0.7.0+2）：系统配置页缺定时任务熔断全局配置

- **触发**：用户 2026-08-22 反馈"连续失败熔断，熔断后重启间隔(分钟)的全局配置要展示在系统配置里"。`Settings.schedule_consecutive_fail_limit`（默认 3）+ `Settings.schedule_retry_interval_minutes`（默认 60）两个全局默认字段在 `backend/app/core/config.py` 第 119-120 行已存在
- **现象**：用户改不了全局默认（只能改 schedule 单条覆盖）；前端 `SettingsView.vue` 系统配置页未渲染这两个 `<ElInputNumber>`；`SystemConfigIn` Pydantic 模型也没声明（被 `422 没有需要更新的字段` 拦截）
- **根因**：`system_config.py::_ENV_KEY_MAP` 第 74 行没映射 SCHEDULE_* → 后端 GET 不下发 → 前端表单 v-model undefined → 不展示
- **修复（v0.7.0+2）**：
  - `_ENV_KEY_MAP` 加 2 行 `"schedule_consecutive_fail_limit": "SCHEDULE_CONSECUTIVE_FAIL_LIMIT"` + `"schedule_retry_interval_minutes": "SCHEDULE_RETRY_INTERVAL_MINUTES"`
  - `SystemConfigIn` 加 2 个 `int | None = Field(default=None, ge=1)` 字段（拒绝 0 / 负数）
  - `frontend/src/views/SettingsView.vue` 新增 "定时任务熔断（全局）" config-group；`SettingsView.spec.ts` 加 1 个用例
- **防重犯**：每当 `Settings` 加新全局默认字段，验收项必含"前端 SettingsView 表单渲染 + 测试用例 + `_ENV_KEY_MAP` 映射"三件套，缺一不可；可用 `grep "v-model=\"systemConfig\." frontend/src/views/SettingsView.vue | wc -l` 自查后端字段数
- **关联**：spec `docs/superpowers/specs/2026-08-22-system-config-expose-circuit-global-design.md`；测试 `backend/tests/test_system_config_exposes_circuit_globals.py` 3 个用例 + `frontend/src/views/SettingsView.spec.ts` 1 个用例

#### 问题 ㉞（v0.7.0+2）：同 schedule 频繁串发 + 熔断重启建新任务不复用

- **触发**：用户 2026-08-22 连发三条反馈（同一截图）：①"每次都只能有一个 running" ②"熔断重启时依然启动原任务而不是新建任务" ③"如果多个定时任务出错，间隔重启时是否能找到对应的是哪个中止的任务"
- **现象**：截图里 22:09 分钟内 #52 (PAUSED) + #53 (RUNNING) 两条宁波活动（同 schedule 同 slot 同分钟）；`retry_failed_schedules` 冷却到期新建 PENDING 而不是 restart 现有 PAUSED
- **根因**：
  - `_BUSY_STATUSES` 是全局集合，与"#1 一 schedule 一活跃"语义不匹配
  - `crawl_tasks` 表**没有** partial unique 约束 `(schedule_id)` WHERE type='scheduled' AND status IN (alive) → 并发同 schedule 双发都能成功入库
  - `retry_failed_schedules` 总是 `db.add(CrawlTask(...))` 新建 PENDING，从不查现有 PAUSED，找不到对应 PAUSED 的语义缺失
- **修复（v0.7.0+2）**：
  - alembic 0028：`CREATE UNIQUE INDEX ux_crawl_tasks_active_per_schedule ON crawl_tasks (json_extract(params,'$.schedule_id')) WHERE type='scheduled' AND status IN ('PENDING','RUNNING','STOP_REQUESTED','PAUSED')`；migration 前清掉冲突旧活跃 task
  - `_has_active_task_for_schedule` / `_find_latest_paused_for_schedule` / `_restart_existing_paused_task` 三个 helper（与 `/tasks/{id}/restart` PAUSED 分支等价）
  - `scheduled_dispatch` / `retry_failed_schedules` 加 schedule 级 busy + IntegrityError 兜底
  - `POST /tasks/{id}/restart` 加 `SAME_SCHEDULE_IN_PROGRESS` 409 校验（先于原有 `TASK_IN_PROGRESS`）
- **防重犯**：
  - 任何创建 `crawl_tasks` type='scheduled' 的代码路径必走 `_has_active_task_for_schedule` 守护 + DB partial unique index 兜底（绝不能用全局 `_BUSY_STATUSES` 漏 schedule 级）
  - `retry_failed_schedules` 默认走"复用 PAUSED"路径，新建只是兜底；任何修改 retry 路径必须保证多 schedule 并发时各自找各自的 PAUSED
  - 用户重启 PAUSED schedule 时不能"顶替"同 schedule 另一个 RUNNING——`POST /tasks/{id}/restart` 顺序：先查 SAME_SCHEDULE 再查全局 TASK_IN_PROGRESS
- **关联**：spec `docs/superpowers/specs/2026-08-22-schedule-unique-active-and-paused-restart-design.md`；测试 `backend/tests/test_schedule_unique_active.py` 9 个用例 + `backend/tests/test_tasks_api_same_schedule_busy.py` 2 个用例 + alembic 0028

### §2.2 启动器配置 / DATA_DIR / 启动 UI 状态同步

#### 问题 ②：DATA_DIR 切换后配置不跟随

- **触发**：用户反馈"切到 `~/.xhs-info-crawl/` 后配置消失"（本次 v0.6.1 反馈）
- **现象**：用户切到自定义 DATA_DIR 后，LLM/OCR/opencli 配置仍写在 `.app/.env`，迁移 DATA_DIR 到新机器时配置"消失"
- **根因**：`ensure_env_file` 永远操作 `.app/.env`（project_root），不论 DATA_DIR 是哪个；`status_server._read_launcher_system_config` 也只读这一份
- **修复**：见 §3.1 配置分层 + §3.5 双写语义
- **防重犯**：见 §3.1 表（用户配置走双写，DATA_DIR 优先读取）

#### 问题 ③：启动器修改后 UI 不同步（OCR_ENABLED 拨动后 .env 不更新）

- **触发**：用户反馈"我手动切换启动 OCR，但 .env 仍是 false"（本次 v0.6.1）
- **现象**：OCR_ENABLED el-switch 拨动只改前端 v-model，没自动 PUT，依赖用户点"保存"按钮——但用户经常只拨开关不保存
- **根因 1**：后端只读 `.app/.env`，DATA_DIR/.env 完全没参与
- **根因 2**：前端缺少 `@change` 实时同步机制
- **修复**：OCR 开关加 `@change` 即 PUT；详见 §3.7
- **防重犯**：任何"用户偏好类"开关（不依赖保存按钮）必须 `@change` 实时同步；保存按钮仅用于表单整体保存

#### 问题 ④：启动器 LLM/OCR 配置在自定义 DATA_DIR 下不展示

- **触发**：本次 v0.6.1（实测 root cause：用户根本没保存过，三个字段本来就空）
- **现象**：用户在 DATA_DIR (`/Users/hanamaki_mac_mini/.xhs-info-crawl`) 替换本地数据后，启动器里 LLM API Key/Base URL/Model 字段全部为空
- **根因**：启动器只读 `.app/.env`，没读 DATA_DIR/.env
- **修复**：见 §3.3 多路径合并读取
- **防重犯**：所有用户配置字段读取走 `_read_launcher_system_config` 的统一合并入口，不直接读单文件

#### 问题 ⑤：OCR 探针不区分 disabled vs not installed

- **触发**：本次 v0.6.1（用户"明明能检测到 paddleocr 已装但测试 OCR 报 ocr_disabled"）
- **现象**：`diagnostics_ocr.py` 把"配置关闭"和"包未装"混为同一种 `ocr_disabled`，UI 无法引导用户操作
- **修复**：见 §3.8 四象限表

### §2.3 venv / 符号链接 / python-build-standalone

#### 问题 ⑥：venv 符号链接导致 zip 丢失可执行文件

- **触发 commit**：`d85eb97 fix(packaging): venv 创建用 --copies,避免符号链接 zip 丢失`
- **现象**：打包后的 zip 解压到另一台机器，`python` / `pip` 是死链接，app 启动报 `No such file or directory`
- **根因**：`python -m venv` 默认创符号链接，zip 压缩后符号链接丢失
- **修复**：`python -m venv venv --copies`

#### 问题 ⑦：mv 后 venv/bin/python 仍是符号链接

- **触发 commit**：`08b359e fix(packaging): mv 后手动把 venv/bin/python 符号链接替换为真实 copy`
- **现象**：`mv venv .app/Contents/Resources/` 之后，符号链接断在 `.app` 内指向外部 storage
- **修复**：mv 后做符号链接 → 实拷贝替换

#### 问题 ⑧：python-build-standalone URL/解压逻辑错误

- **触发 commit**：`cbf6e5e fix(packaging): 修复 python-build-standalone URL 和 Windows 解压逻辑` + `46dbaef` `0df87ea`
- **现象**：下载失败、找不到解压目录、文件名变化致脚本找不到
- **根因**：python-build-standalone 仓库结构调整 + Windows 解压路径假设写死
- **修复**：脚本里用 `find` 动态查找解压后的 python 目录；强制 UTF-8 编码；不升级 pip

### §2.4 macOS / Gatekeeper / AppTranslocation

#### 问题 ⑨：macOS AppTranslocation 丢数据（运行数据放到 .app 外）

- **触发 commit**：`f78cb1b fix(packaging): 把运行数据搬到 .app/Contents/Resources/,解决 AppTranslocation 丢数据`
- **现象**：用户下载并运行 .app 时，macOS 把它移到隔离临时目录（`/var/folders/.../AppTranslocation/...`），写到 cwd 的数据被丢，下次启动找不到
- **根因**：早期脚本把 DB/log 写到 .app 同级目录，被 AppTranslocation 复制
- **修复**：运行数据搬到 `.app/Contents/Resources/xhs-info-crawl/data/`，再启动器允许用户在 UI 重定向 DATA_DIR

#### 问题 ⑩：Gatekeeper 拦截未签名 app 弹窗

- **触发 commit**：`7d6a183 feat(packaging): macOS 打包加 adhoc 签名,避免 Gatekeeper 弹窗`
- **现象**：用户首次运行报"无法打开，因为开发者无法验证"
- **修复**：打包后 `codesign --force --deep --sign - xxx.app`（adhoc 签名）
- **注意**：adhoc 签名**不**等价于 Apple Developer ID；公司分发仍需正式签名

### §2.5 路径定位 / start 脚本

#### 问题 ⑪：start.sh 依赖 cwd，导致双击 .app 找不到脚本

- **触发 commit**：`1b46eb2 fix(packaging): start.sh 用 realpath 找脚本位置,不依赖 cwd`
- **现象**：从 Finder 双击启动 cwd 是 `/`，导致 `cd "$(dirname "$0")"` 失败
- **根因**：`start.sh` 用 `pwd` 或 `dirname $0`（依赖 cwd）找脚本位置
- **修复**：用 `realpath "$0"` 拿绝对路径再 `dirname`

#### 问题 ⑫：包内 index.html 用绝对路径导致 SPA 白屏

- **触发 commit**：`b534e3b fix(packaging): 修复白屏 - 打包时把 index.html 的绝对路径改为相对路径`
- **现象**：vue build 默认 `/assets/...`，但 FastAPI 静态服务 prefix 在子路径，加载 js/css 404 → 白屏
- **根因**：前端 `publicPath` 默认 `"/"` 没设为 `"./"`；同时 FastAPI `app.mount("/assets", ...)` 没配 prefix
- **修复**：打包前 `vue.config.js` `publicPath: "./"` 或构建后 sed 改 `/assets/` → `./assets/`；FastAPI `mount` 用 prefix
- **关联 spec**：`2026-08-16-packaged-frontend-static-serving-design.md` + `2026-08-16-packaged-spa-hash-router-design.md`

### §2.6 Windows 脚本特有

#### 问题 ⑬：PowerShell 变量解析错误 `$RobocopyOutput:`

- **触发 commit**：`ba605f1 fix(packaging): 修复 PowerShell 变量解析错误 $RobocopyOutput:`
- **现象**：脚本里 `"$RobocopyOutput:"` 被 PowerShell 解析成变量 + scope qualifier，运行报语法错
- **根因**：PowerShell 变量命名规则 `$name:scope` 有特殊含义，结尾冒号歧义
- **修复**：换名（`$robocopyOutput` 或用 `${var}` 限定）

#### 问题 ⑭：Windows robocopy 退出码 1 被误判失败

- **触发 commit**：`09faed0 fix(packaging): Windows robocopy 退出码 1 误判失败`
- **现象**：robocopy 拷贝文件**成功**但返回 exit code 1（"复制了文件"在 robocopy 里也算变更），被 `if ($LASTEXITCODE -ne 0)` 误判为失败
- **修复**：只判 exit code >= 8 为真失败（1-7 都是 robocopy 信息位）

#### 问题 ⑮：Windows 脚本中文乱码

- **触发 commit**：`0df87ea fix(packaging): Windows 脚本强制 UTF-8 编码 + 不升级 pip`
- **现象**：PowerShell 默认 GBK 编码，中文注释/字符串乱码
- **修复**：脚本顶部 `chcp 65001 > $null` + `[Console]::OutputEncoding = [Text.UTF8Encoding]::UTF8`

#### 问题 ⑯：start.bat 输出被吞，失败窗口一闪而过

- **触发 commit**：`6546196 fix(packaging): Windows start.bat 输出日志到文件,失败时停留窗口`
- **现象**：批处理 console 窗口关闭，用户看不到报错
- **修复**：双管道 `> app.log 2>&1`；`if errorlevel 1 pause`

### §2.7 shell 兼容 / SIGPIPE

#### 问题 ⑰：find | head 触发 SIGPIPE 致脚本失败

- **触发 commit**：`93adc41 fix(packaging): 用 shell glob 替代 find 管道,避免 SIGPIPE 问题` + `804f759` `b3ccc90`
- **现象**：`find ... | head -1` 中 `head` 提前关闭管道，`find` 收到 SIGPIPE，set -e 模式下脚本退出码 != 0
- **修复**：用 shell glob（`for f in $dir/python*`）替代 `find` 管道；或 `|| true` 容错；或 `set +o pipefail` 局部

### §2.8 启动器子进程 / 端口 / 进程管理

#### 问题 ⑱：API 端口 8000 与本地开发冲突

- **触发 commit**：`64c94d5 fix: API 端口从 8001 开始,避免与本地开发服务冲突`
- **现象**：用户本地 `uvicorn app.main:app --port 8000` 跑开发模式，再启动 .app，两个抢 8000
- **修复**：launcher 从 `API_PORT=8001` 起步，配置 `.env` 暴露

#### 问题 ⑲：端口硬编码 / opencli 检测缺失 / apiPort 未透传

- **触发 commit**：`ce19415` `7a67694` `b8e04a6` `8267a8e`
- **现象**：frontend 拿不到 apiPort；opencli doctor 格式 `[OK] Daemon:` 不被识别
- **根因**：fetcher 硬编码 `http://localhost:8000`；opencli 检测只看 PATH/常见 unix 路径
- **修复**：
  - `.env` 暴露 `API_PORT` 和 `WEB_PORT`
  - `process_manager` 从 .env 读，不再硬编码
  - frontend 通过 `/api/config` 拿当前 apiPort（动态注入）
  - opencli 检测加 GUI 安装路径：`~/Applications/opencli` `/Applications/opencli` `/usr/local/bin/opencli`
  - `opencli doctor` 检测兼容多种 `[OK]` `[INFO]` 标签

#### 问题 ⑳：退出后留子进程孤儿

- **触发 commit**：`3aee1f5 fix(launcher): 退出时彻底清理子进程,不留孤儿`
- **现象**：用户关 launcher 窗口，后端 uvicorn / celery worker / opencli 仍占端口
- **根因**：`atexit`/`SIGTERM` 没向下传播
- **修复**：process_manager 注册 `atexit` + signal handler，递归 kill 子进程组（`os.killpg`）
- **关联 spec**：`2026-08-16-launcher-cleanup-on-exit-design.md`

### §2.9 启动器 UI / 鉴权 / CI

#### 问题 ㉑：默认 admin 密码不可见 / PyWebView 崩溃

- **触发 commit**：`3c6e5d9 fix(launcher): 自动生成的初始密码可见 + PyWebView 崩溃保护`
- **现象**：首次启动随机生成 admin 密码写到日志，但 UI 上不显示，用户进不去
- **修复**：UI 顶部 banner 展示首次密码；PyWebView 主线程异常 try/except 兜底
- **关联 spec**：`2026-08-16-packaged-default-login-and-mainthread-window-design.md` + `2026-08-16-launcher-password-visibility-design.md`

#### 问题 ㉒：前后端端口分离 / 自适应 / 配置互通

- **触发 commit**：`aa75520 fix(launcher): 前后端端口分离 + 端口自适应 + 配置互通`
- **现象**：前端 build 静态文件 hardcode 后端 `localhost:8000`，但 launcher 可能换端口
- **修复**：API 端口 / Web 端口写到 `.env`，前端走 `/api/...` 同源代理（或 vite proxy）
- **关联 spec**：`2026-08-16-packaged-frontend-static-serving-design.md`

#### 问题 ㉓：vue-tsc 类型错误吞掉 CI 通过

- **触发 commit**：`18b2444 fix(launcher-ui): 修复 vue-tsc 报错让 CI 失败` + `fe9e3f4` `f58284a`（revert+retry）
- **现象**：`npm run build` 失败但 CI 显示 success
- **根因**：`vue-tsc --noEmit` exit code 被外层 `|| true` 吞掉
- **修复**：去掉 `|| true`，让类型错误真的 fail

#### 问题 ㉔：暴露 `open_url` / `open_dir` API

- **触发 commit**：`d989b92 feat(launcher): 暴露 open_url/open_dir API,支持打开前端和日志目录`
- **现象**：UI 上"打开日志目录"按钮没实现
- **修复**：status_server 加 `POST /open-url` `POST /open-dir`，跨平台 `open`/`start`/`xdg-open`

### §2.10 其它基础设施

#### 问题 ㉕：Python 启动失败 + launcher 模块路径

- **触发 commit**：`b016a17 fix(packaging): 修复 Python 启动失败 + launcher 模块路径`
- **现象**：venv python 找不到 `launcher` 包；`ModuleNotFoundError`
- **根因**：`PYTHONPATH` 没设 + `launcher/` 没作为 package
- **修复**：start 脚本 `export PYTHONPATH="$RES/.."`，`launcher/` 加 `__init__.py`

#### 问题 ㉖：复制后端源码前先创建 app 目录

- **触发 commit**：`0843d00 fix(packaging): 复制后端源码前先创建 app 目录`
- **现象**：`cp backend/...` 到不存在的目录报 `No such file or directory`
- **修复**：加 `mkdir -p`

### §2.11 Windows venv 路径烧与入口残废

#### 问题 ㉗：Windows 打包 venv pyvenv.cfg 的 home 烧 CI runner 路径,解压到用户机器报 `No Python at '<runner 路径>'`

- **触发**：用户 2026-08-21 反馈："No Python at 'D:\a\xhs-info-crawl\xhs-info-crawl\dist\build\xhs-info-crawl\runtime\python\python.exe'"
- **现象**：用户在 `C:\Users\wpx\Downloads\xhs-info-crawl\` 解压 zip,双击 start.bat,启动失败报错
- **根因**：CPython venv 在创建时把 base python 的**绝对路径**烧进
  `runtime\venv\pyvenv.cfg` 的 `home` 字段。打包脚本运行在
  GitHub Actions runner 上(`workspace = D:\a\xhs-info-crawl\xhs-info-crawl\`),
  pyvenv.cfg 里的 home 是 runner 路径,zip 解压到用户机器后 home 不存在 → CPython 启动 venv python.exe 找不到 base python → 抛 `No Python at '<home 路径>'`
- **修复**:
  - 打包脚本 `scripts/package-windows.ps1` 在 venv 创建步骤后**立刻 patch pyvenv.cfg**
  - 把 home 改成相对路径 `..\python`(`\(相对 venv 自身)`),CPython 启动时按相对找 base python
  - 实测:**只修改 home 字段**就足够,venv 内的 site-packages 不需要重定位
- **关联 spec**:`2026-08-21-windows-packaging-pyvenv-relocatable-design.md`
- **防重犯**:
  - 任何修改 `scripts/package-windows.ps1` venv 步骤的 PR 必须保持"venv 创建 → pyvenv.cfg patch"顺序
  - 测试 `backend/tests/test_packaging_scripts.py::TestPackageWindows::test_script_patches_pyvenv_cfg_home_to_relative` + `test_pyvenv_patch_runs_after_venv_creation` 自动守门
  - 静态检查:`grep -E 'home\s*=\s*.*\\runtime' scripts/package-*.sh scripts/package-*.ps1` 应**无输出**

#### 问题 ㉘：Windows start.bat 双击弹 cmd 黑窗口,终端用户不友好 + 没有 `.exe`/`.vbs` 入口

- **触发**：用户 2026-08-21 反馈:"至少目录是 exe 格式的呀,不然都不知道入口"
- **现象**:解压后用户不知道双击什么;start.bat 双击弹 cmd 黑窗口(像极了"程序崩了")
- **根因**:Windows 没有像 macOS 那样把目录"包装"成 `.app` 的概念。
  - `.exe` 必须用 PyInstaller/cx_Freeze 把 Python 脚本打包成 native exe,体积大、改调试路径麻烦
  - `.bat` 双击弹 cmd 窗口,无法隐藏
  - **正确方案**:`.vbs`(WScript.Shell 启动 + WindowStyle=0 隐藏窗口)
- **修复**:
  - 打包脚本 `scripts/package-windows.ps1` 加 `start.vbs` 生成
  - `start.bat` 保留(给高级用户调试用,失败 pause)
  - `start.vbs` 作为终端用户默认入口;FVM 算法:
    - `WScript.ScriptFullName` 取 vbs 自身路径 → 拼 `start.bat` 绝对路径
    - `WshShell.Run "<bat>", 0, False` 第二个参数 0 = HideWindow,False = 不阻塞
- **关联 spec**:`2026-08-21-windows-packaging-pyvenv-relocatable-design.md § 2.1`
- **防重犯**:
  - 测试 `TestPackageWindows::test_script_creates_silent_vbs_entry` 自动守门 `WScript.Shell` 和 `Run ..., 0,`
  - 注释明确"start.bat 给高级用户,start.vbs 给终端用户",谁改 commit 必读这一节

## 3. 核心架构不变量

### 3.1 配置存储分层（强制）

| 字段类型 | 写到哪里 | 读时优先级 | 例子 |
|---|---|---|---|
| **启动器 bootstrap** | `.app/.env`（project_root） | 唯一 | `API_PORT`, `API_HOST`, `WEB_PORT`, `API_BASE_URL`, `SECRET_KEY` |
| **DATA_DIR 指针** | `.app/.env`（project_root） | 唯一 | `DATA_DIR`, `LOG_DIR` |
| **OCR_ENABLED** | `.app/.env`（project_root） | project_root | 启动器根据安装状态自动同步 |
| **用户配置（双写）** | `.app/.env` **+** `DATA_DIR/.env` | DATA_DIR 优先，project_root 兜底 | `MINIMAX_*`, `OPENCLI_BIN`, `CHROME_BIN`, `OCR_LANGUAGE`, `OCR_MIN_CONFIDENCE`, `OCR_PARALLEL_WORKERS`, `CHROME_USER_DATA_DIR` |

### 3.2 写入语义

| 操作 | 写入位置 | 说明 |
|---|---|---|
| launcher 启动 bootstrap（`ensure_env_file`） | project_root/.env | 仅首次（不存在才创建） |
| launcher PUT `/system-config` 用户配置 | project_root/.env **+** DATA_DIR/.env | 双写 |
| launcher PUT `/system-config` 路径/bootstrap 字段 | project_root/.env only | bootstrap 字段不污染 DATA_DIR |
| 启动器检测到 OCR 已装 → `sync_ocr_enabled_with_installed_state` | project_root/.env only | 启动器单方管理 |

### 3.3 读取语义

`_read_launcher_system_config` 按以下顺序合并：

1. 读 project_root/.env 拿 `DATA_DIR` 指针
2. 读 project_root/.env 全部键
3. 读 DATA_DIR/.env 全部键
4. 合并规则：
   - bootstrap 字段（API_*/WEB_PORT/SECRET_KEY）→ 以 project_root 为准
   - DATA_DIR/log_dir → 以 project_root 为准（启动器需要立刻读）
   - OCR_ENABLED → 以 project_root 为准（启动器 sync 函数管理）
   - 其余用户配置 → **DATA_DIR 优先**，缺失回退 project_root

### 3.4 用户契约

> 配置保存时**同时**写到 `.app/.env` 和 `DATA_DIR/.env`。
>
> **DATA_DIR 是用户配置的权威来源**：备份/迁移时只需拷贝 DATA_DIR 整个目录，配置不会丢。
>
> `.app/.env` 是启动器 bootstrap 字段的权威来源，升级 `.app` 时会被覆盖（这是合理的：API 端口、密钥应该跟环境走）。

### §3.5 DATA_DIR 切换行为（强制）

- 切换 DATA_DIR 时，**不**自动复制旧 DATA_DIR 的 .env 到新 DATA_DIR
- 但要 `mkdir -p` 新 DATA_DIR
- 切换后第一次保存时，新 DATA_DIR/.env 才会被创建

#### 附：开发模式与打包生产模式的数据库文件路径差异

| 模式 | 默认 `DATA_DIR` | SQLite 数据库文件绝对路径示例 | 说明 |
|---|---|---|---|
| 开发模式（dev） | `./data`（相对项目根目录） | `/Users/<user>/Documents/github/project/xhs-info-crawl/data/app.db` | 随仓库目录走，便于本地调试；不应把开发 DB 误当成生产 DB 源 |
| 打包生产模式（.app） | `~/Library/Application Support/com.xhs-info-crawl.local` | `/Users/<user>/Library/Application Support/com.xhs-info-crawl.local/data/app.db` | macOS 标准用户应用数据目录，Time Machine 自动备份、用户隔离 |

**关键约定**：

- 两个模式使用**不同的物理数据库文件**，不要假设 dev DB 与生产 DB 内容相同。
- 当需要从生产环境向 dev 环境恢复参考数据（例如 `cities` 表）时，必须先备份 dev DB，再通过 SQL/脚本显式同步，禁止直接覆盖生产 DB。
- 任何诊断命令写死 `data/app.db` 或 `~/Library/...` 路径前，必须先确认当前 `DATA_DIR` 环境变量；`sqlite3` 不展开 `~`，应使用 `$HOME` 环境变量。

### §3.6 OCR_ENABLED 自动同步（强制）

- 启动器启动时 + 每次 GET `/system-config` 第一次调用时执行
- 检测到 OCR 模型已装（`get_ocr_status(...) == installed`）且 `OCR_ENABLED != true` → 自动写 `OCR_ENABLED=true` 到 project_root/.env
- 检测到 OCR 模型未装 → **不**主动改 `OCR_ENABLED`（保留用户选择）

### 3.7 OCR 开关前端同步（强制）

- OCR 开关必须 `@change` 回调自动 PUT，不依赖用户点"保存"按钮
- 这条是 **P0 强制**：用户多次反馈"拨了开关但没保存"造成 .env 不一致

### 3.8 OCR probe 区分 disabled vs not installed（强制）

| `settings.ocr_enabled` | paddleocr 可导入? | reason |
|---|---|---|
| False | True | `ocr_disabled_in_config` |
| False | False | `ocr_not_installed` |
| True | False | `paddleocr_not_installed` |
| True | True | （正常推理） |

UI 据此给用户明确引导："OCR 已安装，前往系统配置启用" vs "OCR 未安装，请先安装"。

## 4. 打包前 TDD 清单（强制）

> 任何改动 `scripts/package-*.sh` / `scripts/package-*.ps1` / `launcher/env_bootstrap.py` / `launcher/status_server.py` / `launcher/ocr_installer.py` / `launcher/ui/src/components/LLMConfigPanel.vue` 后，**必须**跑完本清单且全绿才能 tag 发版。

### 4.1 打包脚本静态约束

- [ ] `grep -E 'pip install (paddleocr|paddlepaddle)' scripts/package-macos.sh` 应**无输出**
- [ ] `grep -E 'pip install (paddleocr|paddlepaddle)' scripts/package-windows.ps1` 应**无输出**
- [ ] 自动化：`scripts/tests/test_package_macos_ocr_excluded.sh` 全过

### 4.2 启动器配置双写 + 多路径读

- [ ] `launcher/tests/test_status_server_env_merge.py` 全过
  - DATA_DIR/.env 优先于 project_root/.env（用户配置字段）
  - project_root/.env 唯一（bootstrap 字段）
  - OCR_ENABLED 走 project_root 不参与合并
  - PUT 用户配置同时写两处，PUT bootstrap 字段只写 project_root

### 4.3 OCR 启用自动同步

- [ ] `launcher/tests/test_status_server_env_merge.py::test_sync_ocr_enabled_when_installed` 全过
  - OCR 模型已装 + OCR_ENABLED=false → 一次 GET 触发同步
  - OCR 模型未装 + OCR_ENABLED=false → 不动
  - 第二次 GET → 幂等不重复写

### 4.4 OCR 开关前端实时同步

- [ ] `launcher/ui/src/components/LLMConfigPanel.vue` 的 `el-switch` 必须有 `@change` 回调
- [ ] 单元测试或 E2E：拨动开关后立刻 PUT，UI 反馈 ElMessage

### 4.5 OCR probe 区分

- [ ] `backend/tests/test_diagnostics_ocr.py` 全过（覆盖 § 3.8 表格四种场景）

### 4.6 .env 写文件操作审查

- [ ] `backend/tests/test_project_internal_writes.py` 全过（确保不硬编码 /tmp / Path.home() 等项目外路径）
- [ ] 所有生产代码对 `.env` 的读写必须通过：
  - `launcher/env_bootstrap.py::update_env_value`（统一入口）
  - 或 `launcher/status_server.py::_update_env_file`（启动器专用）

### 4.7 已有测试基线

- [ ] `cd backend && pytest -q` 全过
- [ ] `cd frontend && npm run test -- --run` 全过
- [ ] `cd launcher/ui && npm run test -- --run`（若配置）全过
- [ ] `scripts/release-check.sh <version>` 全过

## 5. 打包前必读文档清单

每次打包前必读（顺序阅读）：

1. **本文档**（`docs/packaging-design.md`）
2. `docs/superpowers/specs/2026-08-10-one-click-packaging-design.md`（单次变更设计）
3. `docs/superpowers/specs/2026-08-17-launcher-ocr-direct-design.md`（OCR 按需下载）
4. `docs/superpowers/specs/2026-08-17-launcher-system-config-and-opencli-verify-design.md`（系统配置端点）
5. `docs/superpowers/specs/2026-08-17-launcher-storage-base-dir-design.md`（DATA_DIR 推导）
6. 本次变更对应的 spec（如果有）

## 6. 发版流程（更新）

```
1. 阅读本文档 § 5 清单
2. 跑 § 4 TDD 清单（必须全绿）
3. 跑 scripts/release-check.sh <version>
4. git tag v<version> && git push origin v<version>
5. 验证 GitHub Actions release.yml 产物下载、安装、配置保留
```

## 7. 历史变更

| 版本 | 修复（对应 §2 编号） | spec |
|---|---|---|
| **v0.7.0+2**（本次） | ㉜ 启动时重绑老 Administrators 组 + Viewers 组权限绑 → 老用户 token 含 `*` → 前端 nav 菜单全回 + 系统配置显 Llm；㉝ 系统配置页暴露 `schedule_consecutive_fail_limit` + `schedule_retry_interval_minutes` 全局默认；㉞ 每 schedule 唯一活跃 + 熔断重启用原 PAUSED 任务（partial unique index 0028 + retry 复用 /tasks/{id}/restart PAUSED 路径） | [permission-rebind](file:///Users/hanamaki_mac_mini/Documents/github/project/xhs-info-crawl/docs/superpowers/specs/2026-08-22-permission-rebind-admin-groups-design.md) / [circuit-global](file:///Users/hanamaki_mac_mini/Documents/github/project/xhs-info-crawl/docs/superpowers/specs/2026-08-22-system-config-expose-circuit-global-design.md) / [schedule-unique](file:///Users/hanamaki_mac_mini/Documents/github/project/xhs-info-crawl/docs/superpowers/specs/2026-08-22-schedule-unique-active-and-paused-restart-design.md) |
| v0.7.0+1 | ㉚ 打包版启动自动跑 alembic upgrade head，缺列自动补齐；迁移失败 fail-fast 让 launcher 弹"启动失败" | [2026-08-21-package-startup-auto-migrate-design.md](file:///Users/hanamaki_mac_mini/Documents/github/project/xhs-info-crawl/docs/superpowers/specs/2026-08-21-package-startup-auto-migrate-design.md) |
| **v0.7.0** | ① OCR Python 包必须进 venv（v0.6.1 错误纠正）/ ㉙ 删 ocr-addon release，OCR 模型走主 release 的 build-ocr-models job | `docs/superpowers/specs/2026-08-21-ocr-packaging-v0.7-design.md` |
| **v0.6.1+1**（Windows 修复） | ㉗ Windows venv pyvenv.cfg 烧 CI runner 路径 / ㉘ start.vbs 静默入口 | `docs/superpowers/specs/2026-08-21-windows-packaging-pyvenv-relocatable-design.md` |
| **v0.6.1**（macOS 修复） | ① OCR 选装不再进 venv / ② DATA_DIR 双写 / ③ OCR 开关 `@change` 即同步 / ④ 启动器多路径读 / ⑤ OCR probe 区分 | `docs/superpowers/specs/2026-08-21-packaging-ocr-llm-flow-fix-design.md` |
| **v0.6.0** | ⑥⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱⑲⑳㉑㉒㉓㉔ 打包 + 启动器初版 | `docs/superpowers/specs/2026-08-10-one-click-packaging-design.md` + `2026-08-16-*` + `2026-08-17-*` |

> §2 各问题编号到 v0.6.0 提交均可在历史 commit 中追溯（见 §2 顶部 git log 路径）；
> v0.6.1 编号①②③④⑤ 是 macOS 修复 + DATA_DIR 双写；
> v0.6.1+1 编号㉗㉘ 是 Windows 修复；
> **v0.7.0 编号①（修正版）纠正 v0.6.1 错误减肥，编号㉙ 移除空挂的 ocr-addon release**。