# 抓取范围由配置驱动实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让抓取任务完全跟随配置中心的启用项（关键词 ∪ 博主），任务参数 `keywords` / `blogger_ids` 仅作为"覆盖"使用；二者最终生效都为空时拒绝任务。

**Architecture:** 新增 `app/services/crawl_scope.py` 计算 `effective_keywords` 与 `effective_bloggers`；`crawl_task.py` 与 `tasks.py` 调用它生成最终的抓取范围并写入任务日志。

**Tech Stack:** Python 3.12、FastAPI、SQLAlchemy 2.0、Celery、SQLite、Vue 3、TypeScript、Element Plus、Vitest、Playwright。

## Global Constraints

- 默认行为（任务参数为空）：抓取范围 = 城市内 enabled 的关键词 ∪ 城市内 enabled 的博主。
- 覆盖行为（任务参数非空）：抓取范围 = 任务参数指定的关键词 ∪ 任务参数指定的博主。
- 任务参数 `keywords=[]` / `blogger_ids=[]` 视为显式禁用该项，不回退到默认。
- 入口校验发生在 `POST /api/v1/tasks/crawl`；`POST /tasks/{id}/restart` 不重新校验。
- 阶段一仍保持本地运行，不引入 Redis、MinIO、Docker。
- 不修改 `Blogger.city_code` / `Blogger.platform_user_id` 字段语义（本 spec 仅解决任务范围的驱动逻辑；博主模型变更见配套 spec）。
- 不修改任务类型字段 `type='mixed'` 默认值。

---

### Task 1: 抓取范围计算服务 `crawl_scope`

**Files:**
- Create: `backend/app/services/crawl_scope.py`
- Test: `backend/tests/test_crawl_scope.py`

**Interfaces:**
- Produces: `resolve_effective_keywords(db, city, task_params) -> list[str]`
- Produces: `resolve_effective_bloggers(db, city, task_params) -> list[Blogger]`
- Produces: `resolve_crawl_scope(db, city, task_params) -> CrawlScope`
- `CrawlScope(keywords: list[str], bloggers: list[Blogger])`

**Step 1: 写失败测试覆盖默认/覆盖/禁用三种语义**

```python
def test_resolve_effective_keywords_uses_city_config_when_task_param_missing(db_session, city):
    db_session.add(Keyword(word="A", city_code=city.code, enabled=True))
    db_session.add(Keyword(word="B", city_code=city.code, enabled=True))
    db_session.flush()
    assert resolve_effective_keywords(db_session, city, {}) == ["A", "B"]

def test_resolve_effective_keywords_overrides_city_config_when_task_param_set(db_session, city):
    db_session.add(Keyword(word="A", city_code=city.code, enabled=True))
    db_session.add(Keyword(word="B", city_code=city.code, enabled=True))
    db_session.flush()
    assert resolve_effective_keywords(db_session, city, {"keywords": ["A"]}) == ["A"]

def test_resolve_effective_keywords_returns_empty_when_task_param_disables(db_session, city):
    db_session.add(Keyword(word="A", city_code=city.code, enabled=True))
    db_session.flush()
    assert resolve_effective_keywords(db_session, city, {"keywords": []}) == []
```

- [ ] **Step 1.1: 跑测试确认失败**

Run: `cd backend && source .venv/bin/activate && pytest tests/test_crawl_scope.py -q`

Expected: FAIL，`ModuleNotFoundError: app.services.crawl_scope`。

- [ ] **Step 1.2: 实现 `resolve_effective_keywords`**

```python
def resolve_effective_keywords(db, city, task_params):
    if "keywords" in task_params:
        return list(task_params["keywords"] or [])
    stmt = select(Keyword.word).where(Keyword.city_code == city.code, Keyword.enabled.is_(True)).order_by(Keyword.id)
    return list(db.scalars(stmt).all())
```

- [ ] **Step 1.3: 跑测试确认通过**

Run: `cd backend && source .venv/bin/activate && pytest tests/test_crawl_scope.py::test_resolve_effective_keywords_uses_city_config_when_task_param_missing -q`

Expected: PASS。

**Step 2: 写失败测试覆盖博主默认/覆盖/禁用**

```python
def test_resolve_effective_bloggers_uses_city_config_when_task_param_missing(db_session, city):
    b1 = Blogger(username="b1", profile_url="https://xhs/u/1", city_code=city.code, enabled=True)
    db_session.add(b1); db_session.flush()
    result = resolve_effective_bloggers(db_session, city, {})
    assert [b.username for b in result] == ["b1"]

def test_resolve_effective_bloggers_filters_by_ids_when_overridden(db_session, city):
    b1 = Blogger(username="b1", profile_url="https://xhs/u/1", city_code=city.code, enabled=True)
    b2 = Blogger(username="b2", profile_url="https://xhs/u/2", city_code=city.code, enabled=True)
    db_session.add_all([b1, b2]); db_session.flush()
    result = resolve_effective_bloggers(db_session, city, {"blogger_ids": [b2.id]})
    assert [b.username for b in result] == ["b2"]

def test_resolve_effective_bloggers_returns_empty_when_task_param_disables(db_session, city):
    db_session.add(Blogger(username="b1", profile_url="https://xhs/u/1", city_code=city.code, enabled=True))
    db_session.flush()
    assert resolve_effective_bloggers(db_session, city, {"blogger_ids": []}) == []
```

- [ ] **Step 2.1: 实现 `resolve_effective_bloggers`**

```python
def resolve_effective_bloggers(db, city, task_params):
    if "blogger_ids" in task_params:
        ids = task_params["blogger_ids"] or []
        if not ids:
            return []
        stmt = select(Blogger).where(
            Blogger.id.in_(ids),
            Blogger.city_code == city.code,
            Blogger.enabled.is_(True),
        )
    else:
        stmt = select(Blogger).where(Blogger.city_code == city.code, Blogger.enabled.is_(True))
    return list(db.scalars(stmt.order_by(Blogger.id)).all())
```

- [ ] **Step 2.2: 跑博主相关测试确认通过**

Run: `cd backend && source .venv/bin/activate && pytest tests/test_crawl_scope.py -k blogger -q`

Expected: PASS。

**Step 3: 提交 Task 1**

Run:
```bash
git add backend/app/services/crawl_scope.py backend/tests/test_crawl_scope.py
git commit -m "feat(crawl): add crawl_scope service for effective keywords and bloggers"
```

---

### Task 2: `run_crawl` 使用 `crawl_scope` 计算并记录抓取范围

**Files:**
- Modify: `backend/app/tasks/crawl_task.py`
- Test: `backend/tests/test_crawl_task_scope.py`

**Step 1: 写失败测试覆盖任务日志**

```python
def test_run_crawl_logs_scope_summary(db_session, task_with_city):
    task = task_with_city
    # monkeypatch adapter.search_recent & adapter.blogger_notes to return []
    # assert any("抓取范围生效" in log.message for log in db_session.query(TaskLog).all())
```

- [ ] **Step 1.1: 实现 `run_crawl` 调用 `resolve_crawl_scope` 并写日志**

```python
from app.services.crawl_scope import resolve_crawl_scope

scope = resolve_crawl_scope(db, city, task.params)
log(db, task.id, "INFO", f"抓取范围生效：keywords={len(scope.keywords)} blogger={len(scope.bloggers)} (override={'任务参数' if ('keywords' in task.params or 'blogger_ids' in task.params) else '配置默认'})")
```

- [ ] **Step 1.2: 跑测试确认通过**

Run: `cd backend && source .venv/bin/activate && pytest tests/test_crawl_task_scope.py -q`

Expected: PASS。

**Step 2: 提交 Task 2**

```bash
git add backend/app/tasks/crawl_task.py backend/tests/test_crawl_task_scope.py
git commit -m "feat(crawl): run_crawl logs scope summary using crawl_scope"
```

---

### Task 3: `POST /api/v1/tasks/crawl` 入口校验最终生效范围

**Files:**
- Modify: `backend/app/api/v1/tasks.py`
- Test: `backend/tests/test_tasks_api_scope.py`

**Step 1: 写失败测试覆盖空范围 422**

```python
def test_crawl_rejects_when_effective_scope_empty(client, db_session, city):
    # 城市下无任何 enabled 关键词、无博主
    response = client.post("/api/v1/tasks/crawl", json={"city": city.code})
    assert response.status_code == 422
    assert "请至少启用一个关键词或博主" in response.json()["detail"]
```

- [ ] **Step 1.1: 在 `tasks.py:crawl` 增加 `resolve_crawl_scope` 校验**

```python
from app.services.crawl_scope import resolve_crawl_scope

scope = resolve_crawl_scope(db, city, payload.model_dump())
if not scope.keywords and not scope.bloggers:
    raise HTTPException(422, "请至少启用一个关键词或博主")
```

- [ ] **Step 1.2: 跑测试确认通过**

Run: `cd backend && source .venv/bin/activate && pytest tests/test_tasks_api_scope.py -q`

Expected: PASS。

**Step 2: 提交 Task 3**

```bash
git add backend/app/api/v1/tasks.py backend/tests/test_tasks_api_scope.py
git commit -m "feat(api): reject empty effective crawl scope at /tasks/crawl"
```

---

### Task 4: 文档同步

**Files:**
- Modify: `docs/business-flow.md`
- Modify: `docs/crawler-design.md`
- Modify: `docs/api-doc.md`
- Modify: `docs/ui-design.md`
- Modify: `tests/test-crawler-engine.md`
- Modify: `tests/test-task-scheduling.md`

- [ ] **Step 1: 在 `business-flow.md` 增加"抓取范围计算"节点**
- [ ] **Step 2: 在 `crawler-design.md` 补充 effective 计算逻辑**
- [ ] **Step 3: 在 `api-doc.md` 补充 `CrawlIn` 空数组语义说明**
- [ ] **Step 4: 在 `ui-design.md` 仪表盘禁用态或 Toast 提示**
- [ ] **Step 5: 在 `test-crawler-engine.md` 覆盖 effective 计算与日志断言**
- [ ] **Step 6: 在 `test-task-scheduling.md` 覆盖入口校验**
- [ ] **Step 7: 提交**

```bash
git add docs/ tests/
git commit -m "docs: sync crawl-scope-config-driven spec"
```

---

## 复盘节点

- 全局：`cd backend && source .venv/bin/activate && pytest -q`（预期全部 PASS，新增 + 回归）。
- 前端：`cd frontend && npm run test:unit && npm run test:e2e`（预期全部 PASS）。
- 提交约定：每个 Task 一个提交，message 前缀 `feat(crawl):` / `feat(api):` / `docs:`。

## 非目标

- 不修改博主模型字段语义；详见 spec 3。
- 不修改 `City.code` 生成规则。
- 不引入第二阶段基础设施。
