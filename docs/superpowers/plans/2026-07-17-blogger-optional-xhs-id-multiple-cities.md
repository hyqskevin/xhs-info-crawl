# 博主白名单放宽与多城市实施计划

> 按本计划一步步做即可。

**要做的事：** 博主表单允许 `platform_user_id` 留空，新增 `blogger_cities` 表让一个博主能绑定多个城市；前端的博主表单同步改（去掉 xhs_id 必填、加城市多选）。

---

## 步骤 1：写一个 Python 脚本改数据库结构 + 搬数据

新建 `backend/scripts/migrations/split_blogger_cities.py`，**一个脚本干两件事**：

1. 创建 `blogger_cities` 表
2. 把当前 `bloggers.city_code` 不为空的数据搬到 `blogger_cities(blogger_id, city_code, enabled=blogger.enabled)`

脚本逻辑：

```python
def run_migration(engine):
    # 1. 建表（如果不存在）
    Base.metadata.create_all(engine, tables=[BloggerCity.__table__])
    # 2. 搬数据
    with Session(engine) as db:
        rows = db.execute(text("SELECT id, city_code, enabled FROM bloggers WHERE city_code IS NOT NULL AND city_code != ''")).all()
        for blogger_id, city_code, enabled in rows:
            exists = db.scalar(select(BloggerCity).where(BloggerCity.blogger_id == blogger_id, BloggerCity.city_code == city_code))
            if exists:
                continue
            db.add(BloggerCity(blogger_id=blogger_id, city_code=city_code, enabled=enabled))
        db.commit()
```

加 CLI 入口：`python -m scripts.migrations.split_blogger_cities`

---

## 步骤 2：写测试

新建 `backend/tests/test_split_blogger_cities.py`，2 个测试：

1. 博主有 `city_code='nb'` → 跑完 `blogger_cities` 有 `(blogger_id, 'nb', enabled)` 一条
2. 跑两次幂等（不重复创建）

跑测试看失败：`cd backend && source .venv/bin/activate && pytest tests/test_split_blogger_cities.py -q`

---

## 步骤 3：实现 run_migration

按步骤 1 的代码填，跑测试 → 通过 → 提交：

```bash
git add backend/scripts backend/app/models/blogger_city.py backend/tests/test_split_blogger_cities.py
git commit -m "feat(db): 拆分 blogger 与 city 到多对多表"
```

---

## 步骤 4：改 Blogger 模型

修改 `backend/app/models/config.py`：

- `Blogger.platform_user_id` 改为可空（`Mapped[str | None]`）
- `Blogger.city_code` 改为可空（兼容旧读路径）

写测试 `backend/tests/test_blogger_model.py`：

1. 不传 `platform_user_id` 创建博主成功
2. 传 `platform_user_id=None` 创建博主成功

跑测试 → 通过 → 提交：`git commit -m "feat(model): Blogger.platform_user_id 允许为空"`

---

## 步骤 5：改 BloggerIn 入参

修改 `backend/app/api/v1/settings.py`：

```python
class BloggerIn(BaseModel):
    platform_user_id: str | None = None
    username: str
    profile_url: str | None = None
    city_codes: list[str] = []
    enabled: bool = True
```

修改 `create_setting` 和 `update_setting`：除了存博主字段，还要写 `BloggerCity(blogger_id, city_code, enabled=True)`。

**关键点**：必须删旧的 `BloggerCity` 记录再插新的，否则更新时残留。

写测试 `backend/tests/test_blogger_api.py`：

1. 不传 `platform_user_id` → POST 200
2. 不传 `username` → POST 422
3. 传 `city_codes=[nb, city-99f1e469]` → `blogger_cities` 有两条记录

跑测试 → 通过 → 提交：`git commit -m "feat(api): BloggerIn 接受 city_codes 与可选 platform_user_id"`

---

## 步骤 6：让抓取任务按 blogger_cities 过滤

修改 `backend/app/services/crawl_scope.py` 的 `resolve_effective_bloggers`：

```python
stmt = (
    select(Blogger)
    .join(BloggerCity, BloggerCity.blogger_id == Blogger.id)
    .where(
        BloggerCity.city_code == city.code,
        BloggerCity.enabled.is_(True),
        Blogger.enabled.is_(True),
    )
)
```

写测试 `backend/tests/test_crawl_scope.py` 补充：

1. 博主绑定到城市 A → 抓 A 城市的任务能命中，抓 B 城市不能
2. 博主同时绑定 A 和 B → 抓 A 和 B 都能命中

跑测试 → 通过 → 提交：`git commit -m "feat(crawl): 抓取博主按 blogger_cities 过滤"`

---

## 步骤 7：前端 SettingsView 表单

修改 `frontend/src/views/SettingsView.vue`：

- `xhs_id` 字段去掉"必填"校验
- 城市字段从单选改成 `ElSelect multiple`，绑定 `v-model="form.city_codes"`

写前端测试 `frontend/src/views/SettingsView.spec.ts`：

1. 留空 `xhs_id` 点保存 → POST 不带 `platform_user_id`，返回 200
2. 选两个城市 → POST body 里 `city_codes=["nb", "city-99f1e469"]`
3. 列表展示博主绑定的城市标签

跑测试 → 通过 → 提交：`git commit -m "feat(ui): 博主表单支持多城市与可选 xhs_id"`

---

## 步骤 8：在真实数据库跑迁移

```bash
cd backend && source .venv/bin/activate && python -m scripts.migrations.split_blogger_cities
```

预期：4 条宁波博主都被搬到 `blogger_cities`，1 条 `city_code=''` 的不搬。

查一下：

```bash
cd backend && source .venv/bin/activate && python -c "
from app.core.database import SessionLocal
from app.models.config import Blogger
from app.models.blogger_city import BloggerCity
db = SessionLocal()
print('bloggers:', db.query(Blogger).count())
print('blogger_cities:', db.query(BloggerCity).all())
"
```

---

## 步骤 9：手动端到端验证

- 启动后端、前端
- 在博主管理新增一个博主：留空 xhs_id，绑定上海+宁波
- 跑上海抓取任务 → 该博主笔记出现
- 跑宁波抓取任务 → 同一博主笔记也出现
- 编辑该博主改成只绑定上海 → 跑宁波抓取不再出现

---

## 步骤 10：更新文档

- `docs/database-design.md`：补 `blogger_cities` 表说明
- `docs/api-doc.md`：更新 `BloggerIn` 字段
- `tests/test-config-center-api.md`：补用例
- `tests/test-crawler-engine.md`：补按 blogger_cities 过滤用例

提交：`git commit -m "docs: 同步博主白名单放宽与多城市设计"`

---

## 步骤 11：跑全量回归

```bash
cd backend && source .venv/bin/activate && pytest -q
cd frontend && npm run test:unit && npm run test:e2e
```

预期：全绿。

---

## 完成检查

- [ ] pytest 全绿
- [ ] 真实数据库：4 条博主搬到 `blogger_cities`
- [ ] 前端能创建多城市博主
- [ ] 同一博主在两个城市的抓取任务中都能命中
- [ ] 留空 `xhs_id` 也能保存

---

## 不做什么

- 不用 Alembic（只有一个生产库，直接 Python 脚本改）。
- 不实现博主批量导入/导出、标签、分类、备注。
- 不引入 Redis、MinIO、Docker。