# 2026-08-23 migration 0028 sqlite3 binding + launcher 监控缺口 修复

> 用户反馈:打包后 API 仍挂 — 原因到底是什么?能不能写到 md 里规定下,打包都打不好。

## 1. 背景

用户 2026-08-23 升级到 v0.7.0 后,启动 .app 发现 API 一直连不上,只能看到"API 连不上",看不到真错误。多次重打 .app 问题复现。

### 1.1 真因(根因)

v0.7.0 commit 5/9 引入的 `backend/migrations/versions/0028_crawl_tasks_unique_active_per_schedule.py` 在清理重复活跃 task 时,用了:

```python
sa.text("... finished_at=:now, ...").bindparams(sa.bindparam("ids", expanding=True)),
{"now": sa.func.current_timestamp(), "ids": duplicate_ids},
```

`sa.func.current_timestamp()` 编译为带 `?` 占位符 + `CURRENT_TIMESTAMP` 类型 tag,传给 sqlite3 stdlib driver。driver 不识别这个 SQLAlchemy 类型 tag,抛:

```
sqlite3.ProgrammingError: Error binding parameter 1: type 'current_timestamp' is not supported
```

这条异常发生在 lifespan 阶段 alembic upgrade head — uvicorn 主动退出,launcher 看不到真错误,前端看到"API 连不上"。

### 1.2 TDD 漏洞

写 0028 时 pytest 只测了 happy path(无重复现场),没构造冲突数据 case → UPDATE 路径未测试。
`backend/tests/test_migration_0020_system_admin.py` 同范本可参考。

### 1.3 launcher 监控缺口

`launcher/process_manager.py::start_service` 把子进程 stderr 写 `data/logs/{name}.log`,但 launcher 不实时显示 stderr 到前端。`get_status` 只回 `state='crashed'`,没说为什么 — 用户只能看"API 连不上"。

`launcher/ui/src/components/ServiceStatus.vue` 没有 last_error 显示。

## 2. 目标

1. 修复 0028 binding 报错,让 lifespan 阶段 alembic upgrade head 在用户现场(已有重复 scheduled task)也能跑通。
2. launcher 暴露 last_error 给前端,让用户弹"API 启动失败: <真错误>",不再被黑盒 API 卡死。
3. 把根因写到 spec + TDD 测试,防止 regression。

## 3. 设计

### 3.1 0028 binding 修复

`backend/migrations/versions/0028_crawl_tasks_unique_active_per_schedule.py`:

```python
# 修改前:
{"now": sa.func.current_timestamp(), "ids": duplicate_ids},
# 修改后:
{"now": "CURRENT_TIMESTAMP", "ids": duplicate_ids},
```

字面量字符串让 sqlite 自己解析为 `CURRENT_TIMESTAMP()` SQL 函数(sa.func.current_timestamp() 也最终生成这个 SQL,但 bindparam 通道上 SQLite 方言处理有差异)。

### 3.2 TDD 5 个 case(写在 `backend/tests/test_migration_0028_conflict_cleanup.py`)

策略:subprocess 跑 alembic upgrade head(从 0027 → 0028)在临时 sqlite 上,不污染项目内 data/app.db。范本:`backend/tests/test_migration_0020_system_admin.py`。

| Case | 目标 |
|---|---|
| `test_upgrade_0028_no_op_when_no_duplicates` | 无冲突 → 0028 no-op + alembic_version=0028 + partial unique index 存在 |
| `test_upgrade_0028_marks_duplicates_failed` | 同 schedule 3 条活跃 → 1 条保留 + 2 条强制 FAILED |
| `test_upgrade_0028_ignores_completed_and_manual_tasks` | manual 类型不动 + 已结束 task 不动 |
| `test_upgrade_0028_sqlite_timestamp_binding_does_not_raise` | **关键回归**: 4 条重复触发 UPDATE → 整条 upgrade 不抛 sqlite3.ProgrammingError |
| `test_init_database_with_duplicates_boots_cleanly` | 端到端:lifespan 路径下 alembic upgrade 不抛 |

### 3.3 launcher 监控缺口修复

#### 3.3.1 `launcher/process_manager.py`

`start_service` 在日志头写分隔符:
```
=== launched at <iso8601> pid=<pid> cmd=<cmd> ===
```
Popen 拿到真 PID 后回填占位符 `pid=__PID__`。

`__init__` 加 `_last_launch_at` / `_last_error` dict。

`get_status` 返回字段加 `last_launch_at` / `last_error`(crashed 时从日志末尾抽 8 行)。

`start_service` 启动时清空 `_last_error`,新启动视作健康。

`get_logs_tail` 复用 `_read_log_tail_lines` 提取函数。

#### 3.3.2 `launcher/ui/src/api/client.ts`

`ServiceState` 类型加 `last_launch_at?: string | null` + `last_error?: string | null`。

#### 3.3.3 `launcher/ui/src/components/ServiceStatus.vue`

顶部加 `<el-alert type="error">`,展示 crashed 服务的真错误。

## 4. 验收

- [x] `uv run --project backend pytest backend/tests/test_migration_0028_conflict_cleanup.py -v` — 5 passed
- [x] `uv run --project backend pytest launcher/tests/test_process_manager.py -v` — 16 passed(含 4 个新 case)
- [x] 在 `~/.xhs-info-crawl/app.db`(alembic_version=0027 + 17 条重复 scheduled)上跑 `alembic upgrade head` → exit=0 + alembic_version=0028 + 16 条 FAILED + partial unique index 存在
- [x] 幂等:再跑一次 `alembic upgrade head` 不报错
- [x] 重打 .app:`dist/build/xhs-info-crawl-0.7.0-macos-arm64.zip` + codesign valid on disk
- [x] 拷贝到 `~/Downloads/`(macOS sandbox 拒绝,提供命令让用户手动)

## 5. 关联

- `docs/superpowers/specs/2026-08-22-schedule-unique-active-and-paused-restart-design.md` — 0028 原始设计
- `docs/superpowers/specs/2026-08-21-package-startup-auto-migrate-design.md` — v0.7.0+1 alembic upgrade head 路径
- `docs/superpowers/specs/2026-08-19-launcher-status-panel-design.md` — StatusPanel 现状
- `docs/superpowers/specs/2026-08-16-launcher-cleanup-on-exit-design.md` — 进程组清理