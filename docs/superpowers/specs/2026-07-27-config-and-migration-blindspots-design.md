# 配置与迁移盲区 — 设计 spec

> 对应 `docs/TODO.md` 待办 #9。

## 背景（取证结论）

1. **`.env.example`（项目根）缺两个真实生效的配置项**：
   - `INITIAL_ADMIN_PASSWORD`：`migrations/versions/0012_seed_admin.py:35` 播种 admin 时读取，未设置则回退默认密码 `Admin@123` 并 WARNING。示例文件只字未提，新部署者无从知晓；
   - `MINIMAX_VISION_MODEL`：`app/core/config.py:46` 定义（默认 `MiniMax-vision-01`），`app/services/minimax.py:99` 消费，示例文件缺失。
   - 顺带发现：示例文件中 `ADMIN_USERNAME`/`ADMIN_PASSWORD` 两项全仓库无任何代码消费（migration 用户名硬编码 `admin`），属过期条目，一并更正为 `INITIAL_ADMIN_PASSWORD` 说明。
2. **`init_database` 的 models import 不全**：`app/core/database.py:25` 只 import `activity, config, duplicate, note, report, task, user`，缺 `blogger_city, blogger_group, keyword_group, poster, schedule, search_usage`。应用内经 `app.main` 路由链间接 import 全部模型而无症状，但任何「只调 `init_database`」的裸脚本路径会建出缺表的库。
3. **`migrations/env.py` 已完整**（import 全部 13 个 models 模块）——TODO 原文该项已过时，本次仅验证，不改代码。
4. **（测试实证新发现）全新建库迁移链断裂**：`0001_initial.upgrade()` 用 `Base.metadata.create_all` 按**运行时当前模型**建表，而 env.py 已 import 全部模型，所以空库跑到 0001 就已建好今日全 schema；随后 0002 `ADD COLUMN note_id` 撞已存在列直接 `OperationalError`，链式中止。老库不受影响（`alembic_version` 已就位、不重放）。后果：新部署「按 .env.example + `alembic upgrade head`」根本建不出库。

## 设计

1. `.env.example`：
   - 「管理员账号」一节：`ADMIN_USERNAME`/`ADMIN_PASSWORD` 过期条目替换为 `INITIAL_ADMIN_PASSWORD`（说明：首次 `alembic upgrade head` 播种 admin 时读取；缺省回退 `Admin@123` 并记 WARNING；仅首次建库生效）；
   - 「MiniMax」一节补 `MINIMAX_VISION_MODEL=MiniMax-vision-01`。
2. `init_database` 的函数内 import 与 `migrations/env.py` 对齐为全量 13 个模块。
3. **历史迁移全部改为幂等**（0002–0016，除已带守卫的 0010/0012）：每文件内置 `_cols()/_idx()/_tables()` 三个 inspect 小助手（自包含、不引入跨文件依赖），按「列/索引/表不存在才操作」加守卫；0008 的存量 UPDATE 仅当 `activities.status` 列存在时执行（全新库当前模型本无此列）；0013 的数据迁移仅在建表由本次迁移完成时执行；0006 的 `alter_column(nullable=True)` 对已是 nullable 的列属无害重建，保留不 guard。老库升级路径行为不变（守卫条件全为真，操作照常执行）。
4. 验证项（非代码改动）：`alembic upgrade head` 对空库可建全表；`alembic revision --autogenerate` 对现有模型零 diff。
5. **（autogenerate 实证新发现）模型/迁移漂移**：0013 在 `cities.name` 上建了唯一索引 `ix_cities_name_unique`（生产库已存在、重名数为 0），但 `City` 模型从未声明，autogenerate 持续报 drop diff。按迁移本意对齐：模型 `__table_args__` 显式声明 `Index("ix_cities_name_unique", "name", unique=True)`（用 Index 而非列级 `unique=True`，与 DB 中「已命名唯一索引」形态一致，否则 autogenerate 仍想重建约束）。连带影响：`test_dedupe_cities_script.py` 的「重名城市」场景在新 schema 下无法 INSERT——加 autouse fixture 先 `DROP INDEX` 模拟 0013 前旧 schema，脚本作为旧库一次性清理工具保留（退役决策归 TODO#12 文档口径）。

## 验收

- 定向测试：
  - 子进程裸跑 `init_database`（不经过 app.main），建库后包含 `keyword_groups`/`blogger_cities`/`poster_tasks`/`schedules`/`search_usage` 等全部表（修复前红）；
  - `.env.example` 含 `INITIAL_ADMIN_PASSWORD` 与 `MINIMAX_VISION_MODEL`（修复前红）；
  - 子进程 `alembic upgrade head` 空库建全表（回归验证）；
- 手动执行 `alembic revision --autogenerate` 确认零 diff（结果记入 TODO 验收）；
- 全量后端测试绿。
