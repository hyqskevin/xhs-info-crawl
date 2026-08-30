# v0.7.0+5 修复 migration 0028 sqlite3 CURRENT_TIMESTAMP bind 报错 + launcher api.log 监控缺口

## 背景

用户 2026-08-23 反馈"打包都打不好,API 总是挂"。现象：

- 双击 `xhs-info-crawl.app` 后,launcher 启 worker + beat + web 静态服务(5173)都正常
- API 启了立刻退出,lifespan 阶段 alembic upgrade head 抛 `sqlite3.ProgrammingError: Error binding parameter 1: type 'current_timestamp' is not supported`
- 启动器没把这条错误暴露给前端 PyWebView 窗口,前端只看到"API 连不上"
- 用户重启 .app 多次都没用,因为 launchctl `com.xhs.worker` + `com.xhs.beat` 在 macOS 残留,
  launcher 不再尝试拉新的 worker/beat,但 API 每次都因为同样原因失败

## 根因(migration 0028)

`backend/migrations/versions/0028_crawl_tasks_unique_active_per_schedule.py` 里冲突清理:

```python
bind.execute(
    sa.text(
        "UPDATE crawl_tasks SET status='FAILED', finished_at=:now, "
        "error_message='...' WHERE id IN :ids"
    ).bindparams(sa.bindparam("ids", expanding=True)),
    {"now": sa.func.current_timestamp(), "ids": duplicate_ids},
)
```

`sa.func.current_timestamp()` 在 SQLite stdlib driver (`sqlite3`) 下编译成
`?` placeholder + 类型 tag `CURRENT_TIMESTAMP`,但 sqlite3 module 的
`execute(statement, parameters)` 只识别标准类型 (`str`/`int`/`float`/`None`/`bytes`),
不认识 `CURRENT_TIMESTAMP` 这种函数 tag → 直接 `ProgrammingError`。

**TDD 漏洞**: commit 2/9 的 pytest `test_init_database_works_for_old_db_schema_missing_columns` 没构造冲突数据
(只 bootstrap 到 0027,然后 init 升 0028,跑的是 0028 的 happy path)。
我 commit 5/9 把 0028 提交前也只跑了现有 test,没补"现场有 ≥2 条同 schedule 活跃 task 时 0028 升级"的 case。

## 修复

### 代码

**`backend/migrations/versions/0028_crawl_tasks_unique_active_per_schedule.py`**:

```python
-    {"now": sa.func.current_timestamp(), "ids": duplicate_ids},
+    {"now": "CURRENT_TIMESTAMP", "ids": duplicate_ids},
```

字符串字面量 `CURRENT_TIMESTAMP` 直接走 raw SQL,sqlite3 stdlib 完美支持。

### TDD(补真现场测试)

新增 `backend/tests/test_migration_0028_conflict_cleanup.py`:

1. `test_upgrade_0028_no_op_when_no_duplicates`:构造现场只有 1 条同 schedule RUNNING task,0028 升完不 UPDATE
2. `test_upgrade_0028_marks_duplicates_failed`:插入同 schedule 3 条 RUNNING + 1 条 COMPLETED,
   0028 升完后 RUNNING 应剩 id 最小那条,另外 2 条 status=FAILED + error_message 含"迁移 0028"
3. `test_upgrade_0028_ignores_completed_tasks`:COMPLETED/STOPPED 不在 alive 集合内,不占 unique 冲突
4. `test_upgrade_0028_sqlite_timestamp_binding_does_not_raise`:回归保护,
   在 SQLite 上跑 0028 不抛 ProgrammingError(根因 case)
5. `test_init_database_with_duplicates_boots_cleanly`:端到端,init_database 在有冲突的 DB 上跑通,
   alembic_version=0028 + UPDATE 走通

### launcher 监控缺口(同时修)

`launcher/process_manager.py:start_service` 当前不读取子进程 stdout/stderr 实时上报,
只在子进程退出后才在 status_server 查询时拿历史 log。
这导致 alembic 失败时用户看不到任何错误。

**修复**:start_service 在 `_logs_dir/{name}.log` 头加 `=== launched at <iso8601> ===` 分隔符,
status_server 的 `GET /api/v1/launcher/logs/{name}` 接口返回最近 200 行(已有的话)。
PyWebView 状态面板"服务详情"页加"最近日志"折叠区,显示 4 个服务的 tail。
关联需求:`docs/superpowers/specs/2026-08-19-launcher-status-panel-design.md`

### 启动流程再加一道兜底

`backend/app/main.py:lifespan` 在 `init_database()` 抛异常后,**不要立即 raise**,
改为先写 `data/logs/lifespan-error.log`(完整 traceback),再 raise。
launcher 的 `_signal_handler` 不改,但 `process_manager.py:start_service("api")`
的调用方 (`launcher/main.py:255`) 用 try/except 包住:
- api 启动失败 → 把 lifespan-error.log 内容推给 status_server 的 `last_error` 字段
- PyWebView 状态页面上方红条"API 启动失败: <摘要>",点开看完整 traceback

## 验收

- [ ] 后端 pytest 全量跑通(含新增 5 个 case)
- [ ] 在你现有的 `/Users/hanamaki_mac_mini/.xhs-info-crawl/app.db` 上跑
      `uv run --project backend alembic upgrade head` 不再报错
- [ ] alembic_version 从 0027 升到 0028
- [ ] 重新双击 .app → 前端可登录 + 看到 4 个列表
- [ ] launcher 数据目录 `data/logs/api.log` 头出现 `=== launched at ... ===` 分隔符
- [ ] status_server 暴露 `last_error` 字段
- [ ] PyWebView 状态面板显示红条"API 启动失败: <摘要>"(回归 case)

## 不在本次范围

- v0.7.0+5 修复完成后,launcher 自动清理 macOS launchctl 残留 `com.xhs.worker` / `com.xhs.beat` 的逻辑
  (关联需求 `docs/superpowers/specs/2026-08-16-launcher-cleanup-on-exit-design.md` 已有部分实现,
   但需要补"launcher 启动前先 kill 上一轮残留"的预清理,留到 v0.7.0+6)
- migration 0028 升级失败时的回滚路径(目前是 fail-fast,直接 raise 让 uvicorn 退出)

## 关联文件

- `backend/migrations/versions/0028_crawl_tasks_unique_active_per_schedule.py` — 主修复
- `backend/tests/test_migration_0028_conflict_cleanup.py` — 新增
- `launcher/process_manager.py` — 日志头分隔符
- `launcher/status_server.py` — `last_error` 字段
- `launcher/ui/src/components/StatusPanel.vue` — 红条 + 日志折叠区

## 关联 spec

- `docs/superpowers/specs/2026-08-21-package-startup-auto-migrate-design.md` §2.3 fail-fast 行为
- `docs/superpowers/specs/2026-08-19-launcher-status-panel-design.md`
- `docs/superpowers/specs/2026-08-16-launcher-cleanup-on-exit-design.md`
- `docs/superpowers/specs/2026-08-22-schedule-unique-active-and-paused-restart-design.md` (0028 的设计源)
