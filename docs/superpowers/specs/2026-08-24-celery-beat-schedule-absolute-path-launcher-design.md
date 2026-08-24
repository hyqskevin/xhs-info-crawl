# v0.7.0+8: celery beat schedule.db 走 DATA_DIR(launcher)

> 状态: 已写完待实施
> 关联: v0.7.0+7 commit 156cc03(Settings 同时读 cwd + DATA_DIR/.env)、scripts/dev-beat.sh(已用 `--schedule`)

## 背景

v0.7.3 修复后,用户验证 DATA_DIR 路径全部自动跟随,但发现一处遗漏:

```
$ ls -la ~/Downloads/xhs-info-crawl.app/Contents/Resources/xhs-info-crawl/celerybeat-schedule.db
-rw-r--r--  16384 Aug 24 10:52 .../xhs-info-crawl.app/Contents/Resources/xhs-info-crawl/celerybeat-schedule.db
```

celery beat 的 `celerybeat-schedule.db` 写在 .app/Contents/Resources/xhs-info-crawl/ 下,而不是 `~/.xhs-info-crawl/celery/celerybeat-schedule.db`。

## 根因

`launcher/process_manager.py:111` 启动 celery beat 的命令:

```python
"beat": [python, "-m", "celery", "-A", "app.tasks.crawl_task", "beat", "--loglevel=info"],
```

**没传 `--schedule` 参数**。celery beat 默认写到 worker 进程的 cwd(进程管理器 `cwd=str(self.project_root)` 即 `.app/Contents/Resources/xhs-info-crawl/`)。

参考:`scripts/dev-beat.sh` 已经传 `--schedule "$CELERY_FOLDER/celerybeat-schedule"`,所以 dev 模式没问题。launcher 模式漏了。

## 影响

- .app 升级后(用户解压新 zip 覆盖旧的),beat schedule 状态丢失
- celery beat 重启时,PersistentScheduler 看到空 db,**会重新触发所有到期的历史任务**
- 用户感知:"升级 .app 后定时任务突然又跑了一次 / 行为变化"
- 数据库本体(`app.db`)和 celery queue/processed 都在 DATA_DIR,不受影响 —— **只是 beat schedule 这一处遗漏**

## 设计

在 `launcher/process_manager.py::_build_default_commands` 的 `"beat"` 命令里加 `--schedule <绝对路径>`:

```python
# beat 的 schedule.db 必须写到 DATA_DIR 内,不能跟着 .app 升级丢
# 路径解析跟 env_bootstrap.resolve_data_dir 同款逻辑,确保绝对路径
"beat": [python, "-m", "celery", "-A", "app.tasks.crawl_task", "beat",
         "--loglevel=info",
         "--schedule", self._resolve_beat_schedule_path()],
```

新增 `_resolve_beat_schedule_path()` 方法(同 `_resolve_logs_dir` 风格):
1. 读 .env 的 `CELERY_FOLDER`,有就用 `<CELERY_FOLDER>/celerybeat-schedule`(转绝对路径)
2. 没有就 fallback 到 `DATA_DIR/celery/celerybeat-schedule`(转绝对路径)
3. 都缺 → 兜底 `project_root/data/celery/celerybeat-schedule`(原行为,不崩)

**为什么不用 `--schedule` 进程环境变量直接传 cwd 解析**:celery beat 不接受 CELERY_BEAT_SCHEDULE env var(我没找到),只能命令行参数。

**为什么不复用 `_resolve_logs_dir`**:语义不同。logs_dir 用 LOG_DIR,beat 用 CELERY_FOLDER。强行复用会让配置耦合,用户单独改 LOG_DIR 不影响 CELERY_FOLDER。

## TDD

### `launcher/tests/test_process_manager_beat_schedule.py`(新增)

5 个 case:

1. `test_beat_schedule_default_under_data_dir_celery`: .env 无 CELERY_FOLDER → schedule 路径 = DATA_DIR/celery/celerybeat-schedule
2. `test_beat_schedule_uses_celery_folder_from_env`: .env `CELERY_FOLDER=/custom/celery` → schedule = /custom/celery/celerybeat-schedule
3. `test_beat_schedule_relative_celery_folder_resolved`: .env `CELERY_FOLDER=./celery` → schedule 解析成 project_root/celery/celerybeat-schedule
4. `test_beat_schedule_absolute_path_preserved`: .env `CELERY_FOLDER=/abs/path/celery` → schedule = /abs/path/celery/celerybeat-schedule
5. `test_beat_schedule_fallback_when_no_data_dir`: .env 完全缺失 → 兜底 project_root/data/celery/celerybeat-schedule(原行为)

### `launcher/tests/test_process_manager.py` 现有 15 个 case

应保持全部通过(本次只加一个 key,不改既有逻辑)。

## 验收

- [ ] `pytest launcher/tests/test_process_manager_beat_schedule.py` 5/5 全绿
- [ ] `pytest launcher/tests/` 全量通过(原 15 个 process_manager + 5 个新 + 既有 data_dir_resolution / logs_dir)
- [ ] 重打 .app,启动后:
  - 实际 celery beat 进程的命令行包含 `--schedule` 参数
  - `~/.xhs-info-crawl/celery/celerybeat-schedule.db` 存在(不再写到 .app 内)
- [ ] commit + push + tag v0.7.4

## 关联教训

- 任何 celery / subprocess 启动的命令,**显式指定持久化路径**(不能依赖 cwd)
- dev 模式(dev-beat.sh)和 launcher 模式(process_manager.py)的启动参数要保持一致,不能一个传 `--schedule` 一个不传
- "路径跟随 DATA_DIR"原则要贯彻到所有持久化文件,不止数据库
