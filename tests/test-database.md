# 测试用例：数据库（迁移 + 种子 + 一致性）

维度：数据库（后端）。

## 目标

验收 SQLite（阶段一）到 PostgreSQL（阶段二）切换前的 DB 维度契约：

- Alembic 迁移顺序在 `alembic_version` 表中向前不可跳跃，downgrade 必须对称。
- 关键列的 nullable / unique / 外键 / 索引必须按照最新 `models/*.py` 实现。
- `seed_admin` 迁移在首次部署 / DB 重置时种入 admin + Argon2 密码。
- 软删除（`deleted_at`）在 `Activity`、`Note`（可选）等表生效，列表查询过滤。
- 历史 24-hex ObjectID 的发布时间回填脚本幂等。
- 模型 → DB schema 漂移检测：Alembic head 等于 models 期望版本。

## 可执行测试锚点

- DB 初始化：[backend/tests/test_database.py](file:///Users/kevin_w/Documents/github/xhs-info-crawl/backend/tests/test_database.py)
- 脚手架 / 迁移契约：[backend/tests/test_scaffold_contract.py](file:///Users/kevin_w/Documents/github/xhs-info-crawl/backend/tests/test_scaffold_contract.py)
- 模型行为：[backend/tests/test_models_and_maintenance.py](file:///Users/kevin_w/Documents/github/xhs-info-crawl/backend/tests/test_models_and_maintenance.py)
- 关键词组多对多 schema：[backend/tests/test_keyword_group_models.py](file:///Users/kevin_w/Documents/github/xhs-info-crawl/backend/tests/test_keyword_group_models.py)
- 海报模型 schema：[backend/tests/test_poster_models.py](file:///Users/kevin_w/Documents/github/xhs-info-crawl/backend/tests/test_poster_models.py)
- seed_admin 迁移：[backend/tests/test_seed_admin_migration.py](file:///Users/kevin_w/Documents/github/xhs-info-crawl/backend/tests/test_seed_admin_migration.py)
- Activity 软删除：[backend/tests/test_activity_status_removal.py](file:///Users/kevin_w/Documents/github/xhs-info-crawl/backend/tests/test_activity_status_removal.py)
- 城市拆分/修复脚本：[backend/tests/test_fix_activity_city_code.py](file:///Users/kevin_w/Documents/github/xhs-info-crawl/backend/tests/test_fix_activity_city_code.py)、[backend/tests/test_split_blogger_cities.py](file:///Users/kevin_w/Documents/github/xhs-info-crawl/backend/tests/test_split_blogger_cities.py)
- 24-hex ObjectID 解析：[backend/tests/test_note_id_published_at.py](file:///Users/kevin_w/Documents/github/xhs-info-crawl/backend/tests/test_note_id_published_at.py)

## 用例编号

| ID | 场景 | 期望 | 锚点 |
|---|---|---|---|
| TC-DB-001 | 在临时 SQLite 上 `init_database` | 文件生成 + 表齐全 | `test_database.py::test_init_database_creates_sqlite_file` |
| TC-DB-002 | 配置覆盖 DATA_DIR 等 | 路径来自 env | `test_scaffold_contract.py` |
| TC-DB-003 | 全部迁移 upgrade | `alembic_version` 抵达 head | `alembic upgrade head` + `test_seed_admin_migration.py` |
| TC-DB-004 | 任意迁移 downgrade | 表可重建 | `test_seed_admin_migration.py::test_downgrade_removes_admin` |
| TC-DB-005 | users 表首次为空 | seed_admin 注入 admin + 97-byte Argon2 | `test_seed_admin_migration.py::test_seed_admin_inserts_when_users_empty` |
| TC-DB-006 | users 已存在 admin | seed_admin 跳过 | `test_seed_admin_migration.py::test_seed_admin_skips_when_admin_exists` |
| TC-DB-007 | `INITIAL_ADMIN_PASSWORD` 设置 | 覆盖默认值 | `test_seed_admin_migration.py::test_env_password_override` |
| TC-DB-008 | 默认密码 + WARNING 日志 | 含"生产环境必须更改"提示 | `test_seed_admin_migration.py::test_default_password_warning` |
| TC-DB-009 | Activity 软删除列存在 | `deleted_at` 索引建立 | `test_activity_status_removal.py` |
| TC-DB-010 | Activity 列表默认过滤软删 | `deleted_at IS NULL` | `test_activities_api.py` |
| TC-DB-011 | KeywordGroup 多对多关联表存在 | `keyword_group_cities / keywords` 关联表 | `test_keyword_group_models.py` |
| TC-DB-012 | Poster 模板 `parsed_meta` JSON 序列化 | 不丢失 | `test_poster_models.py` |
| TC-DB-013 | `fix_activity_city_code` 一次性脚本 | 跑后 `activity.city_code` 与 city.name 一致 | `test_fix_activity_city_code.py` |
| TC-DB-014 | `split_blogger_cities` | 一博主多城市拆分 | `test_split_blogger_cities.py` |
| TC-DB-015 | `dedupe_cities` 幂等 | 多轮跑结果稳定 | `test_dedupe_cities_script.py::test_dedupe_is_idempotent` |
| TC-DB-016 | `backfill_note_id_published_at` | published_at 计数下降，幂等 | `test_note_id_published_at.py` |
| TC-DB-017 | City.name unique | 重复 name INSERT 失败 | 模型 + `test_dedupe_cities_script.py` |
| TC-DB-018 | 字段提取策略：note.published_at 是 UTC | DB 存储 UTC，UI 显示 +08:00 | `test_published_at_parser.py` |
| TC-DB-019 | Maintenance cron `cleanup_activity_dates` | 清理 60 天外异常窗口 | `test_activity_cleanup.py` |
| TC-DB-020 | 阶段二：`DATABASE_URL=postgresql://...` 启动 | 切换无破坏 | （阶段二后续补） |

## 验收

- `uv run --project backend pytest backend/tests/test_database.py backend/tests/test_scaffold_contract.py backend/tests/test_models_and_maintenance.py backend/tests/test_seed_admin_migration.py backend/tests/test_activity_status_removal.py backend/tests/test_keyword_group_models.py backend/tests/test_poster_models.py backend/tests/test_fix_activity_city_code.py backend/tests/test_split_blogger_cities.py backend/tests/test_dedupe_cities_script.py backend/tests/test_note_id_published_at.py backend/tests/test_activity_cleanup.py -q` 全绿。
- 不与 [tests/test-parse-real-published-at.md](file:///Users/kevin_w/Documents/github/xhs-info-crawl/tests/test-parse-real-published-at.md) 重复（后者是解析器专项）；不与 [tests/test-note-zero-activity-and-window.md](file:///Users/kevin_w/Documents/github/xhs-info-crawl/tests/test-note-zero-activity-and-window.md) 重复（后者是零活动业务）。
