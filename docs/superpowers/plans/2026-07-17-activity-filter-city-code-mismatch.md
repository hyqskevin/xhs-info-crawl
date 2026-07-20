# 活动列表 city_code 一致性实施计划

> 按本计划一步步做即可。

**要做的事：** 数据库里 14 条"上海活动"的 `city_code` 字段存的是中文字面量 `'上海'`，但前端按 `City.code='city-99f1e469'` 筛选，所以筛不到。要做的事：写一个迁移脚本把脏数据改成 code，并加防御以后不再产生脏数据。

---

## 步骤 1：写迁移脚本

新建 `backend/scripts/migrations/fix_activity_city_code.py`，写一个 `run_migration(db)` 函数：

```python
def run_migration(db):
    code_by_name = {c.name: c.code for c in db.query(City).all()}
    codes = set(code_by_name.values())
    fixed = 0
    for a in db.query(Activity).filter(Activity.status.notin_(["DELETED", "MERGED"])).all():
        if a.city_code in codes:
            continue
        if a.city_code in code_by_name:
            a.city_code = code_by_name[a.city_code]
            fixed += 1
    db.commit()
    return fixed
```

**不需要 NA 归档城市**——当前脏数据都能匹配上 `cities.name`。

加 CLI 入口：

```python
if __name__ == "__main__":
    db = SessionLocal()
    fixed = run_migration(db)
    print(f"扫描 {db.query(Activity).count()} / 已修正 {fixed}")
```

---

## 步骤 2：写测试

新建 `backend/tests/test_fix_activity_city_code.py`，3 个测试：

1. 城市表有 `上海/code=city-99f1e469`，活动 `city_code='上海'` → 跑完变成 `'city-99f1e469'`
2. 城市表有 `宁波/code=nb`，活动 `city_code='nb'` → 不动
3. 跑两次幂等（第二次 fixed=0）

跑测试看失败：`cd backend && source .venv/bin/activate && pytest tests/test_fix_activity_city_code.py -q`

---

## 步骤 3：实现 run_migration

按步骤 1 的代码填，跑步骤 2 的测试 → 通过 → 提交：

```bash
git add backend/scripts backend/tests/test_fix_activity_city_code.py
git commit -m "feat(db): 修正 activity.city_code 数据迁移脚本"
```

---

## 步骤 4：入库时加防御

修改 `backend/app/tasks/crawl_task.py`，写一个 `assert_city_code(db, code) -> bool` 函数：检查 code 是否在 `cities` 表里，没有就返回 False。

在写 `Activity` 前调用：

```python
if not assert_city_code(db, extracted_city_code):
    log(db, task.id, "ERROR", f"city_code 不在 cities 表: {extracted_city_code}")
    task.skipped_activities += 1
    continue
```

写测试 `backend/tests/test_crawl_task_city_validation.py`：模拟 adapter 返回一个 `city_code='火星'` 的活动，断言不入库、日志包含 ERROR。

跑测试 → 通过 → 提交：`git commit -m "feat(crawl): 入库前校验 city_code 必须在 cities 表"`

---

## 步骤 5：在真实数据库跑迁移

```bash
cd backend && source .venv/bin/activate && python -m scripts.migrations.fix_activity_city_code
```

预期输出：`扫描 34 / 已修正 14`。

跑完查一下：

```bash
cd backend && source .venv/bin/activate && python -c "
from app.core.database import SessionLocal
from app.models.activity import Activity
from sqlalchemy import func
db = SessionLocal()
print(db.query(Activity.city_code, func.count(Activity.id)).group_by(Activity.city_code).all())
"
```

预期：每个 `city_code` 都是 code 字符串。

---

## 步骤 6：前端验证

启动后端，启动前端，访问 `/activities`，选择"上海"过滤器：

- 期望：列表展示 14 条上海活动
- URL 是 `?city=city-99f1e469`

---

## 步骤 7：更新文档

- `docs/database-design.md`：补一句 `activities.city_code` 必须引用 `cities.code`
- `docs/api-doc.md`：补一句前端按 `City.code` 传参
- `tests/test-database-migration.md`：新增迁移脚本用例

提交：`git commit -m "docs: 同步 city_code 一致性设计"`

---

## 步骤 8：跑全量回归

`cd backend && source .venv/bin/activate && pytest -q` → 全绿

---

## 完成检查

- [ ] pytest 全绿
- [ ] 真实数据库：所有活动 `city_code` 都是 code 字符串（没有中文字面量）
- [ ] 前端选择"上海"返回 14 条活动
- [ ] 防御逻辑：模拟脏数据不会被入库

---

## 不做什么

- 不建 NA 归档城市（当前脏数据都能匹配上）。
- 不用 Alembic（只有一个生产库，直接 Python 脚本改）。
- 不删除历史脏数据，只改 `city_code` 字段。
- 不引入 Redis、MinIO、Docker。
