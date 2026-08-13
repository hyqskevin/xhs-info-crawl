# 活动管理（推文列表）按关键词组/博主组筛选 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 ActivitiesView 推文列表页加"关键词组"和"博主组"两个互斥筛选维度；为支持筛选，推文入库时落库 `matched_keywords / matched_blogger_id / matched_blogger_username / like_count / collect_count / comment_count`；列表展示新增 3 列互动数。

**Architecture:**
- 后端：Note 表新增 6 个 nullable 列；alembic 迁移 0022；`crawl_task.download_and_ocr` 透传 `_matched_*` tag 到 Note；从 `detail` 提取 like/collect/comment；`list_notes` 新增 `keyword_group_ids / blogger_group_ids` query 参数，使用 SQLite JSON1 `json_each` 在 SQL 层过滤；与 `keyword / blogger_id` 互斥 422。
- 前端：ActivitiesView 的"内容"和"博主"两个分组加 RadioButton 切换"自定义 vs 组"；互斥清空对方字段；表格新增 3 列互动数（null → "—"）。
- 进程：uvicorn 自动 reload；celery worker 必须手动重启以加载新 ORM 模型。

**Tech Stack:** FastAPI + SQLAlchemy 2.0 + Alembic + Pydantic v2；Vue 3 + Element Plus + TypeScript + Vitest。

---

## File Structure

### 后端
| 路径 | 操作 | 职责 |
|------|------|------|
| `backend/migrations/versions/0022_note_match_and_engagement.py` | 新建 | Note 加 6 列 nullable |
| `backend/app/models/note.py` | 修改 | 新增 6 字段 |
| `backend/app/schemas/note.py` (如有) / `notes.py` 接口 | 修改 | `_summary` 返回 like/collect/comment；list_notes 接收 keyword_group_ids/blogger_group_ids query |
| `backend/app/tasks/crawl_task.py` | 修改 | 博主搜索 item 加 `_matched_blogger_id/username` tag；`Note(...)` 构造时填 6 字段；从 detail 提 like/collect/comment |
| `backend/app/services/opencli_adapter.py` | 修改 | 如 detail 字段名不直接对应，新增 `_extract_engagement(detail) -> dict` 帮助函数（占位） |
| `backend/tests/test_note_match_fields.py` | 新建 | 9 条后端测试 |

### 前端
| 路径 | 操作 | 职责 |
|------|------|------|
| `frontend/src/views/ActivitiesView.vue` | 修改 | Radio 切换 keyword↔keyword_group、blogger↔blogger_group；筛选 payload 包含新参数；表格加 3 列 |
| `frontend/src/api/client.ts` | 修改 | `notes()` 类型签名补充新参数（无需代码改动，仅注释） |
| `frontend/src/views/ActivitiesView.spec.ts` | 修改 | 5 条新测试 |

### 文档
| 路径 | 操作 | 职责 |
|------|------|------|
| `docs/api-doc.md` | 修改 | `GET /api/v1/notes` 参数与互斥规则 |
| `docs/database-design.md` | 修改 | Note 表新增 6 字段说明 |

---

## Task 1: 数据库迁移 — Note 加 6 列

**Files:**
- Create: `backend/migrations/versions/0022_note_match_and_engagement.py`

- [ ] **Step 1: 新建迁移文件**

在 `backend/migrations/versions/0022_note_match_and_engagement.py` 写入：

```python
"""note: 落库抓取来源（matched_keywords / matched_blogger_*）+ 互动数（like/collect/comment_count）

关联 TODO: 活动管理按关键词组/博主组筛选
关联 spec: docs/superpowers/specs/2026-08-13-activities-filter-by-groups-design.md

- Note 表加 6 个 nullable 列
- 不回填历史数据（迁移前入库的推文这些列为 null，筛选时被自然忽略）
- 迁移后必须重启 celery worker，否则 worker 持旧 ORM 模型访问新列触发 no such column
"""
import sqlalchemy as sa
from alembic import op


revision = "0022_note_match_and_engagement"
down_revision = "0021"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    note_cols = {c["name"] for c in inspector.get_columns("notes")}

    if "matched_keywords" not in note_cols:
        op.add_column("notes", sa.Column("matched_keywords", sa.JSON, nullable=True))
    if "matched_blogger_id" not in note_cols:
        op.add_column("notes", sa.Column("matched_blogger_id", sa.Integer, nullable=True))
    if "matched_blogger_username" not in note_cols:
        op.add_column("notes", sa.Column("matched_blogger_username", sa.String(64), nullable=True))
    if "like_count" not in note_cols:
        op.add_column("notes", sa.Column("like_count", sa.Integer, nullable=True))
    if "collect_count" not in note_cols:
        op.add_column("notes", sa.Column("collect_count", sa.Integer, nullable=True))
    if "comment_count" not in note_cols:
        op.add_column("notes", sa.Column("comment_count", sa.Integer, nullable=True))


def downgrade() -> None:
    op.drop_column("notes", "comment_count")
    op.drop_column("notes", "collect_count")
    op.drop_column("notes", "like_count")
    op.drop_column("notes", "matched_blogger_username")
    op.drop_column("notes", "matched_blogger_id")
    op.drop_column("notes", "matched_keywords")
```

- [ ] **Step 2: 运行迁移**

```bash
cd backend && alembic upgrade head
```

预期：迁移成功，无报错。

- [ ] **Step 3: 校验列已加**

```bash
cd backend && sqlite3 data/app.db "PRAGMA table_info(notes);"
```

预期输出包含 `matched_keywords | matched_blogger_id | matched_blogger_username | like_count | collect_count | comment_count` 6 行。

- [ ] **Step 4: 提交**

```bash
git add -f backend/migrations/versions/0022_note_match_and_engagement.py
git commit -m "migration: note matched_* + engagement columns (0022)"
```

---

## Task 2: Note ORM 模型加字段

**Files:**
- Modify: `backend/app/models/note.py:6-21`

- [ ] **Step 1: 修改 Note 模型**

打开 `backend/app/models/note.py`，把 `Note` 类改成：

```python
class Note(Base):
    __tablename__ = "notes"
    id: Mapped[int] = mapped_column(primary_key=True)
    task_id: Mapped[int] = mapped_column(Integer, index=True)
    platform_note_id: Mapped[str] = mapped_column(String(128), unique=True)
    title: Mapped[str] = mapped_column(String(512))
    content: Mapped[str] = mapped_column(Text, default="")
    source_url: Mapped[str] = mapped_column(String(512))
    city_code: Mapped[str] = mapped_column(String(32), index=True)
    status: Mapped[str] = mapped_column(String(32))
    review_status: Mapped[str] = mapped_column(String(32), default="PENDING", index=True)
    merged_into_note_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    raw_data: Mapped[dict] = mapped_column(JSON, default=dict)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    # 2026-08-13: 推文抓取来源（matched_*） + 互动数（engagement）
    matched_keywords: Mapped[list | None] = mapped_column(JSON, nullable=True)
    matched_blogger_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    matched_blogger_username: Mapped[str | None] = mapped_column(String(64), nullable=True)
    like_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    collect_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    comment_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
```

- [ ] **Step 2: 校验导入无错**

```bash
cd backend && python -c "from app.models.note import Note; print(Note.matched_keywords)"
```

预期：`输出 <JSON> 类型`（不报错）。

- [ ] **Step 3: 提交**

```bash
git add backend/app/models/note.py
git commit -m "model: add matched_* + engagement columns to Note"
```

---

## Task 3: 后端测试 — Note 字段落库

**Files:**
- Create: `backend/tests/test_note_match_fields.py`

- [ ] **Step 1: 写第一个失败测试 — matched_keywords 落库**

新建 `backend/tests/test_note_match_fields.py`：

```python
"""Note 落库抓取来源 + 互动数 + list_notes 按组筛选

关联 TODO: 活动管理按关键词组/博主组筛选
关联 spec: docs/superpowers/specs/2026-08-13-activities-filter-by-groups-design.md
"""
import pytest
from sqlalchemy import select

from app.models.blogger import Blogger
from app.models.blogger_city import BloggerCity
from app.models.blogger_group import BloggerGroup, BloggerGroupMember
from app.models.city import City
from app.models.config import Blogger
from app.models.keyword_group import KeywordGroup, KeywordGroupCity, KeywordGroupWord
from app.models.note import Note


def test_note_matched_keywords_persisted(db_session, sample_city: City):
    """Note 入库时 _matched_keywords 写入 Note.matched_keywords"""
    note = Note(
        task_id=1,
        platform_note_id="xhs-001",
        title="宁波咖啡探店",
        content="...",
        source_url="https://www.xiaohongshu.com/explore/xhs-001",
        city_code=sample_city.code,
        status="DOWNLOADED",
        matched_keywords=["咖啡", "探店"],
    )
    db_session.add(note)
    db_session.commit()
    db_session.expire_all()
    found = db_session.scalar(select(Note).where(Note.platform_note_id == "xhs-001"))
    assert found is not None
    assert found.matched_keywords == ["咖啡", "探店"]


def test_note_matched_blogger_persisted(db_session, sample_city: City):
    """博主搜索结果入库带 matched_blogger_id/username"""
    blogger = Blogger(platform_user_id="bp1", username="本地探店君", profile_url="https://www.xiaohongshu.com/user/profile/bp1")
    db_session.add(blogger)
    db_session.commit()
    db_session.refresh(blogger)

    note = Note(
        task_id=1,
        platform_note_id="xhs-002",
        title="博主笔记",
        content="...",
        source_url="https://www.xiaohongshu.com/explore/xhs-002",
        city_code=sample_city.code,
        status="DOWNLOADED",
        matched_blogger_id=blogger.id,
        matched_blogger_username=blogger.username,
    )
    db_session.add(note)
    db_session.commit()
    db_session.expire_all()
    found = db_session.scalar(select(Note).where(Note.platform_note_id == "xhs-002"))
    assert found is not None
    assert found.matched_blogger_id == blogger.id
    assert found.matched_blogger_username == "本地探店君"


def test_note_engagement_fields_persisted(db_session, sample_city: City):
    """赞藏评 3 个字段可独立写入"""
    note = Note(
        task_id=1,
        platform_note_id="xhs-003",
        title="...",
        content="...",
        source_url="https://www.xiaohongshu.com/explore/xhs-003",
        city_code=sample_city.code,
        status="DOWNLOADED",
        like_count=1200,
        collect_count=345,
        comment_count=67,
    )
    db_session.add(note)
    db_session.commit()
    db_session.expire_all()
    found = db_session.scalar(select(Note).where(Note.platform_note_id == "xhs-003"))
    assert found.like_count == 1200
    assert found.collect_count == 345
    assert found.comment_count == 67
```

- [ ] **Step 2: 跑测试看红**

```bash
cd backend && pytest tests/test_note_match_fields.py -v
```

预期：`test_note_matched_keywords_persisted` 失败（字段不存在），`test_note_matched_blogger_persisted` 失败，`test_note_engagement_fields_persisted` 失败。注：Task 2 已加字段，这里会通过 ORM 写入不报错；**但要**等 Task 2 完成。Task 3 假设 Task 2 已 done。

如 Task 2 已 done，3 个测试均应通过（落库字段已存在）。若失败，检查 ORM 字段名与测试一致。

- [ ] **Step 3: 跑测试看绿**

```bash
cd backend && pytest tests/test_note_match_fields.py::test_note_matched_keywords_persisted -v
```

预期：通过。

- [ ] **Step 4: 提交**

```bash
git add backend/tests/test_note_match_fields.py
git commit -m "test: note matched_* + engagement field persistence"
```

---

## Task 4: list_notes 筛选参数 — keyword_group_ids

**Files:**
- Modify: `backend/app/api/v1/notes.py:125-192`

- [ ] **Step 1: 写失败测试 — keyword_group_ids 命中交集**

在 `backend/tests/test_note_match_fields.py` 末尾追加：

```python
def test_list_notes_keyword_group_filter(db_session, sample_city: City, client):
    """GET /notes?keyword_group_ids=1 命中 matched_keywords 与组词有交集的 note"""
    from app.models.keyword_group import KeywordGroup, KeywordGroupWord, KeywordGroupCity
    from app.main import app
    from fastapi.testclient import TestClient

    kg = KeywordGroup(name="探店", enabled=True)
    db_session.add(kg)
    db_session.commit()
    db_session.refresh(kg)
    db_session.add(KeywordGroupCity(keyword_group_id=kg.id, city_code=sample_city.code, enabled=True))
    db_session.add(KeywordGroupWord(keyword_group_id=kg.id, word="咖啡", enabled=True))
    db_session.add(KeywordGroupWord(keyword_group_id=kg.id, word="探店", enabled=True))
    db_session.commit()

    n_match = Note(task_id=1, platform_note_id="xhs-A", title="tA", content="c",
                   source_url="https://www.xiaohongshu.com/explore/xhs-A",
                   city_code=sample_city.code, status="DOWNLOADED",
                   matched_keywords=["咖啡"])
    n_miss = Note(task_id=1, platform_note_id="xhs-B", title="tB", content="c",
                  source_url="https://www.xiaohongshu.com/explore/xhs-B",
                  city_code=sample_city.code, status="DOWNLOADED",
                  matched_keywords=["展馆"])
    n_none = Note(task_id=1, platform_note_id="xhs-C", title="tC", content="c",
                  source_url="https://www.xiaohongshu.com/explore/xhs-C",
                  city_code=sample_city.code, status="DOWNLOADED")
    db_session.add_all([n_match, n_miss, n_none])
    db_session.commit()

    with TestClient(app) as tc:
        token = _login_admin(tc)
        resp = tc.get(f"/api/v1/notes?keyword_group_ids={kg.id}",
                       headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    body = resp.json()
    note_ids = {item["id"] for item in body["data"]["items"]}
    assert n_match.id in note_ids
    assert n_miss.id not in note_ids
    assert n_none.id not in note_ids


def test_list_notes_keyword_group_filter_multi_or(db_session, sample_city: City):
    """多个 keyword_group_ids 之间 OR 关系"""
    from app.models.keyword_group import KeywordGroup, KeywordGroupWord, KeywordGroupCity
    from app.main import app
    from fastapi.testclient import TestClient

    kg1 = KeywordGroup(name="咖啡", enabled=True)
    kg2 = KeywordGroup(name="展馆", enabled=True)
    db_session.add_all([kg1, kg2])
    db_session.commit()
    for kg in (kg1, kg2):
        db_session.refresh(kg)
        db_session.add(KeywordGroupCity(keyword_group_id=kg.id, city_code=sample_city.code, enabled=True))
    db_session.add(KeywordGroupWord(keyword_group_id=kg1.id, word="咖啡", enabled=True))
    db_session.add(KeywordGroupWord(keyword_group_id=kg2.id, word="展馆", enabled=True))
    db_session.commit()

    n1 = Note(task_id=1, platform_note_id="xhs-M1", title="t", content="c",
              source_url="https://www.xiaohongshu.com/explore/xhs-M1",
              city_code=sample_city.code, status="DOWNLOADED", matched_keywords=["咖啡"])
    n2 = Note(task_id=1, platform_note_id="xhs-M2", title="t", content="c",
              source_url="https://www.xiaohongshu.com/explore/xhs-M2",
              city_code=sample_city.code, status="DOWNLOADED", matched_keywords=["展馆"])
    db_session.add_all([n1, n2])
    db_session.commit()

    with TestClient(app) as tc:
        token = _login_admin(tc)
        resp = tc.get(f"/api/v1/notes?keyword_group_ids={kg1.id}&keyword_group_ids={kg2.id}",
                       headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    note_ids = {item["id"] for item in resp.json()["data"]["items"]}
    assert n1.id in note_ids and n2.id in note_ids


def test_list_notes_keyword_and_group_mutex(db_session, sample_city: City):
    """keyword + keyword_group_ids 同传 422"""
    from app.main import app
    from fastapi.testclient import TestClient
    with TestClient(app) as tc:
        token = _login_admin(tc)
        resp = tc.get("/api/v1/notes?keyword=咖啡&keyword_group_ids=1",
                       headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 422
```

并在文件顶部加辅助：

```python
def _login_admin(tc) -> str:
    """返回 admin JWT；首次自动 seed 默认账号"""
    from app.core.config import get_settings
    from app.core.security import create_access_token
    from app.models.user import User
    from app.core.database import SessionLocal
    s = get_settings()
    db = SessionLocal()
    try:
        u = db.query(User).filter(User.username == s.admin_username).first()
        if u is None:
            u = User(username=s.admin_username, role="admin", enabled=True)
            db.add(u)
            db.commit()
        token = create_access_token({"sub": u.username, "role": "admin"})
        return token
    finally:
        db.close()
```

如项目已有登录方式可用，参考 [auth.py](file:///Users/hanamaki_mac_mini/Documents/github/project/xhs-info-crawl/backend/app/api/v1/auth.py) 用 `tc.post('/api/v1/auth/login', json=...)` 走真实登录。优先用真实登录；若 db 需预置 admin 账号且已有 conftest fixture，则用 fixture。

- [ ] **Step 2: 实现 list_notes 新参数 + JSON1 过滤 + 互斥**

修改 `backend/app/api/v1/notes.py` 的 `list_notes` 函数（line 125-192）：

```python
@router.get("")
def list_notes(
    _: Auth,
    db: DB,
    city: str | None = None,
    review_status: str | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    keyword: str | None = None,
    keyword_group_ids: Annotated[list[int] | None, Query()] = None,
    blogger_id: int | None = None,
    blogger_group_ids: Annotated[list[int] | None, Query()] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
):
    # 互斥校验
    if keyword and keyword_group_ids:
        raise HTTPException(status_code=422, detail="参数冲突：keyword 与 keyword_group_ids 不能同时传")
    if blogger_id is not None and blogger_group_ids:
        raise HTTPException(status_code=422, detail="参数冲突：blogger_id 与 blogger_group_ids 不能同时传")

    filters = [Note.review_status.notin_(["DELETED", "MERGED"])]
    if city:
        filters.append(Note.city_code == city)
    if review_status:
        filters.append(Note.review_status == review_status)
    published = Note.published_at
    if start_date:
        filters.append(Note.published_at >= datetime.combine(start_date, time.min))
    if end_date:
        filters.append(Note.published_at <= datetime.combine(end_date, time.max))

    # 关键词组筛选：取所有选中 enabled 组的 words 并集
    if keyword_group_ids:
        words_stmt = (
            select(KeywordGroupWord.word)
            .join(KeywordGroup, KeywordGroup.id == KeywordGroupWord.keyword_group_id)
            .where(
                KeywordGroup.id.in_(keyword_group_ids),
                KeywordGroup.enabled.is_(True),
                KeywordGroupWord.enabled.is_(True),
            )
            .distinct()
        )
        word_set = [w for w in db.scalars(words_stmt).all() if w]
        if not word_set:
            # 选中组无 enabled words → 无结果
            return {"code": 200, "message": "success", "data": {"items": []}, "pagination": {"page": page, "page_size": page_size, "total": 0}}
        # SQLite JSON1 过滤
        from sqlalchemy import text
        filters.append(
            text("EXISTS (SELECT 1 FROM json_each(notes.matched_keywords) WHERE json_each.value IN :word_set)")
            .bindparams(word_set=tuple(word_set))
        )

    # 博主组筛选：取所有选中 enabled 组的成员 blogger id 并集
    if blogger_group_ids:
        from app.models.blogger_group import BloggerGroupMember
        blogger_ids_stmt = (
            select(BloggerGroupMember.blogger_id)
            .join(BloggerGroup, BloggerGroup.id == BloggerGroupMember.group_id)
            .where(
                BloggerGroup.id.in_(blogger_group_ids),
                BloggerGroup.enabled.is_(True),
            )
            .distinct()
        )
        blogger_id_set = list(db.scalars(blogger_ids_stmt).all())
        if not blogger_id_set:
            return {"code": 200, "message": "success", "data": {"items": []}, "pagination": {"page": page, "page_size": page_size, "total": 0}}
        filters.append(Note.matched_blogger_id.in_(blogger_id_set))

    if keyword:
        stripped = keyword.strip()
        if stripped:
            pattern = f"%{stripped}%"
            filters.append(or_(Note.title.ilike(pattern), Note.content.ilike(pattern)))
    if blogger_id is not None:
        blogger = db.scalar(select(Blogger).where(Blogger.id == blogger_id))
        if blogger is None:
            raise HTTPException(404, "博主不存在")
        if not blogger.profile_url:
            return {"code": 200, "message": "success", "data": {"items": []}, "pagination": {"page": page, "page_size": page_size, "total": 0}}
        filters.append(Note.source_url.like(blogger.profile_url + "%"))

    # ... 后续 total / rows 逻辑保持不变
```

并在文件顶部 import：

```python
from app.models.keyword_group import KeywordGroup, KeywordGroupWord
```

- [ ] **Step 3: 跑新测试**

```bash
cd backend && pytest tests/test_note_match_fields.py -v
```

预期：4 条新测试全绿。

- [ ] **Step 4: 跑全量后端测试**

```bash
cd backend && pytest -q
```

预期：无回归。

- [ ] **Step 5: 提交**

```bash
git add backend/app/api/v1/notes.py backend/tests/test_note_match_fields.py
git commit -m "api: list_notes keyword_group_ids + blogger_group_ids (mutex with keyword/blogger_id)"
```

---

## Task 5: list_notes 详情接口 + 列表 _summary 返回互动数列

**Files:**
- Modify: `backend/app/api/v1/notes.py` — `_summary` 函数

- [ ] **Step 1: 写失败测试 — _summary 含互动数**

在 `backend/tests/test_note_match_fields.py` 追加：

```python
def test_list_notes_engagement_in_summary(db_session, sample_city: City):
    """列表 /notes 返回 like/collect/comment 三列"""
    from app.main import app
    from fastapi.testclient import TestClient

    Note.task_id = 1  # 避免 unbound
    n = Note(
        task_id=1, platform_note_id="xhs-E1", title="t", content="c",
        source_url="https://www.xiaohongshu.com/explore/xhs-E1",
        city_code=sample_city.code, status="DOWNLOADED",
        like_count=100, collect_count=20, comment_count=5,
    )
    db_session.add(n)
    db_session.commit()

    with TestClient(app) as tc:
        token = _login_admin(tc)
        resp = tc.get("/api/v1/notes",
                       headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    items = resp.json()["data"]["items"]
    e1 = next(item for item in items if item["id"] == n.id)
    assert e1["like_count"] == 100
    assert e1["collect_count"] == 20
    assert e1["comment_count"] == 5
```

- [ ] **Step 2: 找到 _summary 并加字段**

在 `backend/app/api/v1/notes.py` 找到 `_summary` 函数（已存在，生成列表行），在返回字典里加 3 个键：

```python
def _summary(note: Note, activity_count: int, ocr_texts: list[str]) -> dict:
    return {
        # ... 现有字段 ...
        "like_count": note.like_count,
        "collect_count": note.collect_count,
        "comment_count": note.comment_count,
    }
```

具体字段顺序按现有 `_summary` 实现风格；至少保证 3 个新键存在。

- [ ] **Step 3: 跑测试**

```bash
cd backend && pytest tests/test_note_match_fields.py::test_list_notes_engagement_in_summary -v
```

预期：通过。

- [ ] **Step 4: 提交**

```bash
git add backend/app/api/v1/notes.py backend/tests/test_note_match_fields.py
git commit -m "api: include like/collect/comment in list_notes summary"
```

---

## Task 6: 抓取阶段 — 透传 _matched_* tag 到 Note

**Files:**
- Modify: `backend/app/tasks/crawl_task.py:420-530`

- [ ] **Step 1: 博主搜索 item 加 tag**

打开 `backend/app/tasks/crawl_task.py`，定位 `for blogger in scope.bloggers` 循环（line 420-448）。修改 `results.extend((city.code, item) for item in items)` 这一行之前，给 item 加 tag：

```python
                for item in items:
                    tagged = dict(item)
                    tagged["_matched_blogger_id"] = blogger.id
                    tagged["_matched_blogger_username"] = blogger.username
                    results.append((city.code, tagged))
```

注意：原代码是 `results.extend((city.code, item) for item in items)` 一次性 extend，需要改成 for 循环 + tag。

- [ ] **Step 2: Note 构造时透传 tag**

定位 `Note(...)` 构造（line 519-529），改为：

```python
    note = Note(
        task_id=task.id,
        platform_note_id=extract_platform_note_id(note_url) or note_url.split("/")[-1].split("?")[0],
        title=item.get("title", ""),
        content=detail.get("content", ""),
        source_url=note_url,
        city_code=city,
        status="DOWNLOADED",
        published_at=published_at,
        raw_data=detail,
        matched_keywords=item.get("_matched_keywords") or [],
        matched_blogger_id=item.get("_matched_blogger_id"),
        matched_blogger_username=item.get("_matched_blogger_username"),
        like_count=_extract_engagement(detail, "like_count"),
        collect_count=_extract_engagement(detail, "collect_count"),
        comment_count=_extract_engagement(detail, "comment_count"),
    )
```

- [ ] **Step 3: 在 crawl_task.py 顶部加 _extract_engagement 帮助函数**

```python
def _extract_engagement(detail: dict, field: str) -> int | None:
    """从 opencli note 详情中提取互动数。

    字段名映射：opencli 实际返回可能是 liked_count / collected_count 等。
    实施时若已确认实际字段名，替换候选列表。
    """
    if not isinstance(detail, dict):
        return None
    candidates = {
        "like_count": ("like_count", "liked_count", "likes"),
        "collect_count": ("collect_count", "collected_count", "collects"),
        "comment_count": ("comment_count", "comments"),
    }.get(field, (field,))
    for key in candidates:
        if key in detail and detail[key] is not None:
            try:
                return int(detail[key])
            except (TypeError, ValueError):
                return None
    return None
```

- [ ] **Step 4: 跑后端测试**

```bash
cd backend && pytest -q
```

预期：无回归。

- [ ] **Step 5: 提交**

```bash
git add backend/app/tasks/crawl_task.py
git commit -m "crawl: persist matched_keywords + matched_blogger + engagement on note insert"
```

---

## Task 7: 前端 API 客户端 — 补 type 注释

**Files:**
- Modify: `frontend/src/api/client.ts:6`

- [ ] **Step 1: 添加 ts 类型注释**

打开 `frontend/src/api/client.ts`，line 6 的 `notes:` 函数注释（仅注释，不改运行时）：

```ts
notes:(params:{city?:string;review_status?:string;start_date?:string;end_date?:string;keyword?:string;keyword_group_ids?:number[];blogger_id?:number;blogger_group_ids?:number[];page?:number;page_size?:number}={})=>http.get('/notes',{params}),
```

- [ ] **Step 2: 类型检查**

```bash
cd frontend && npx vue-tsc --noEmit -p tsconfig.json
```

预期：0 error。

- [ ] **Step 3: 提交**

```bash
git add frontend/src/api/client.ts
git commit -m "client: notes() accepts keyword_group_ids + blogger_group_ids"
```

---

## Task 8: 前端 — ActivitiesView 改造筛选器

**Files:**
- Modify: `frontend/src/views/ActivitiesView.vue`

- [ ] **Step 1: 引入 keyword_groups / blogger_groups 数据**

在 `ActivitiesView.vue` 的 script 顶部加 state 和 load：

```ts
const keywordGroups = ref<any[]>([])
const bloggerGroups = ref<any[]>([])

async function loadGroups() {
  try {
    const [kgResp, bgResp] = await Promise.all([api.keywordGroups(), api.bloggerGroups()])
    keywordGroups.value = (kgResp.data.data?.items || []).filter((g: any) => g.enabled)
    bloggerGroups.value = (bgResp.data.data?.items || []).filter((g: any) => g.enabled)
  } catch { keywordGroups.value = []; bloggerGroups.value = [] }
}
```

并在 `initialize()` 末尾加 `await loadGroups()`。

- [ ] **Step 2: filters 改造 — 新增 2 个 mode + 2 个 ids**

把 `filters` 改为：

```ts
const filters = reactive({
  city: '',
  review_status: '',
  keyword_mode: 'custom' as 'custom' | 'groups',  // 新增
  keyword: '',
  keyword_group_ids: [] as number[],                // 新增
  blogger_mode: 'list' as 'list' | 'groups',       // 新增
  blogger_id: null as number | null,
  blogger_group_ids: [] as number[],               // 新增
  dates: [] as string[],
  page: 1,
  page_size: 20,
})
```

- [ ] **Step 3: queryParams 拼装新参数**

```ts
function queryParams() {
  const params: any = {
    city: filters.city || undefined,
    review_status: filters.review_status || undefined,
    start_date: filters.dates?.[0] || undefined,
    end_date: filters.dates?.[1] || undefined,
    page: filters.page,
    page_size: filters.page_size,
  }
  if (filters.keyword_mode === 'custom') {
    const kw = filters.keyword?.trim()
    if (kw) params.keyword = kw
  } else {
    if (filters.keyword_group_ids.length) {
      params.keyword_group_ids = [...filters.keyword_group_ids]
    }
  }
  if (filters.blogger_mode === 'list') {
    if (filters.blogger_id != null) params.blogger_id = filters.blogger_id
  } else {
    if (filters.blogger_group_ids.length) {
      params.blogger_group_ids = [...filters.blogger_group_ids]
    }
  }
  return params
}
```

- [ ] **Step 4: 切换 mode 时清空对方**

新增 helper：

```ts
function setKeywordMode(mode: 'custom' | 'groups') {
  filters.keyword_mode = mode
  if (mode === 'custom') filters.keyword_group_ids = []
  else filters.keyword = ''
}
function setBloggerMode(mode: 'list' | 'groups') {
  filters.blogger_mode = mode
  if (mode === 'list') filters.blogger_group_ids = []
  else filters.blogger_id = null
}
```

- [ ] **Step 5: resetFilters 清空全部 4 个字段**

```ts
function resetFilters() {
  Object.assign(filters, {
    city: '',
    review_status: '',
    keyword_mode: 'custom',
    keyword: '',
    keyword_group_ids: [],
    blogger_mode: 'list',
    blogger_id: null,
    blogger_group_ids: [],
    dates: [],
    page: 1,
    page_size: 20,
  })
  load()
}
```

- [ ] **Step 6: 模板改造 — 模板筛选区**

把现有"内容"+"博主"两个筛选块改为：

```vue
<ElFormItem label="内容">
  <div class="filter-row">
    <ElRadioGroup :model-value="filters.keyword_mode" @change="(v: any) => setKeywordMode(v)">
      <ElRadioButton value="custom">自定义关键词</ElRadioButton>
      <ElRadioButton value="groups">关键词组</ElRadioButton>
    </ElRadioGroup>
    <ElInput
      v-if="filters.keyword_mode === 'custom'"
      v-model="filters.keyword"
      placeholder="标题或正文关键词"
      clearable
      class="filter-input"
    />
    <ElSelect
      v-else
      v-model="filters.keyword_group_ids"
      multiple collapse-tags collapse-tags-tooltip
      placeholder="选择 1 个或多个关键词组"
      class="filter-input"
    >
      <ElOption v-for="g in keywordGroups" :key="g.id" :label="g.name" :value="g.id" />
    </ElSelect>
  </div>
</ElFormItem>
<ElFormItem label="博主">
  <div class="filter-row">
    <ElRadioGroup :model-value="filters.blogger_mode" @change="(v: any) => setBloggerMode(v)">
      <ElRadioButton value="list">博主列表</ElRadioButton>
      <ElRadioButton value="groups">博主组</ElRadioButton>
    </ElRadioGroup>
    <ElSelect
      v-if="filters.blogger_mode === 'list'"
      v-model="filters.blogger_id"
      placeholder="选择博主"
      clearable
      class="filter-input"
    >
      <ElOption v-for="b in bloggerFilteredByCity" :key="b.id" :label="b.username" :value="b.id" />
    </ElSelect>
    <ElSelect
      v-else
      v-model="filters.blogger_group_ids"
      multiple collapse-tags collapse-tags-tooltip
      placeholder="选择 1 个或多个博主组"
      class="filter-input"
    >
      <ElOption v-for="g in bloggerGroups" :key="g.id" :label="g.name" :value="g.id" />
    </ElSelect>
  </div>
</ElFormItem>
```

并在 `<style>` 末尾加：

```scss
.filter-row { display: flex; gap: 8px; align-items: center; }
.filter-input { width: 280px; }
```

注意：原模板中"博主"列已有自己的 `bloggerFilteredByCity` 计算；保留。

- [ ] **Step 7: 表格新增 3 列**

在 ElTable 中追加（在"城市"列后、"活动数"列前）：

```vue
<ElTableColumn label="点赞" width="90">
  <template #default="scope">{{ scope.row.like_count?.toLocaleString() ?? '—' }}</template>
</ElTableColumn>
<ElTableColumn label="收藏" width="90">
  <template #default="scope">{{ scope.row.collect_count?.toLocaleString() ?? '—' }}</template>
</ElTableColumn>
<ElTableColumn label="评论" width="90">
  <template #default="scope">{{ scope.row.comment_count?.toLocaleString() ?? '—' }}</template>
</ElTableColumn>
```

- [ ] **Step 8: 跑前端测试**

```bash
cd frontend && npm run test -- --run
```

预期：所有原测试通过（如有失败，回归 0 项）。

- [ ] **Step 9: 提交**

```bash
git add frontend/src/views/ActivitiesView.vue
git commit -m "ui: ActivitiesView filter by keyword group / blogger group + engagement columns"
```

---

## Task 9: 前端 — ActivitiesView 新增筛选测试

**Files:**
- Modify: `frontend/src/views/ActivitiesView.spec.ts`

- [ ] **Step 1: 加 5 个新测试**

打开 `frontend/src/views/ActivitiesView.spec.ts`，追加：

```ts
import { describe, expect, it, vi, beforeEach } from 'vitest'
import ActivitiesView from './ActivitiesView.vue'
// ... 已有的 setup ...

describe('ActivitiesView group filters', () => {
  it('switches between custom keyword and keyword group filter', async () => {
    render(ActivitiesView)
    // 默认是 custom
    expect(screen.queryByPlaceholderText('标题或正文关键词')).toBeTruthy()
    expect(screen.queryByText('选择 1 个或多个关键词组')).toBeNull()
    // 切到 groups
    const groupsBtn = screen.getByText('关键词组')
    await fireEvent.click(groupsBtn)
    expect(screen.queryByPlaceholderText('标题或正文关键词')).toBeNull()
    expect(screen.queryByText('选择 1 个或多个关键词组')).toBeTruthy()
  })

  it('switches between blogger list and blogger group filter', async () => {
    render(ActivitiesView)
    const bloggerGroupsBtn = screen.getByText('博主组')
    await fireEvent.click(bloggerGroupsBtn)
    expect(screen.queryByText('选择 1 个或多个博主组')).toBeTruthy()
  })

  it('sends keyword_group_ids when filter mode is groups', async () => {
    const mockGet = vi.spyOn(api, 'notes').mockResolvedValue({ data: { data: { items: [] }, pagination: { total: 0 } } } as any)
    render(ActivitiesView)
    // 切到关键词组 + 选第一个
    const groupsBtn = screen.getByText('关键词组')
    await fireEvent.click(groupsBtn)
    // 模拟选择（直接通过 setter，因为 ElSelect mock 复杂）
    // ... 实际实现时可对 ElSelect 用 stub
    await fireEvent.click(screen.getByText('应用筛选'))
    expect(mockGet).toHaveBeenCalled()
    const callArgs = mockGet.mock.calls[0][0]
    expect('keyword_group_ids' in callArgs).toBe(true)
  })

  it('renders like/collect/comment columns with null fallback', async () => {
    vi.mocked(api.notes).mockResolvedValue({
      data: {
        data: {
          items: [{
            id: 1, title: 't', city_code: 'NB', published_at: null, status: 'DOWNLOADED',
            review_status: 'PENDING', activity_count: 0, source_url: 'u', like_count: null, collect_count: 50, comment_count: null,
          }]
        },
        pagination: { total: 1 }
      }
    } as any)
    render(ActivitiesView)
    expect(await screen.findByText('—')).toBeTruthy()
    expect(screen.getByText('50')).toBeTruthy()
  })

  it('resets all four filter fields on reset click', async () => {
    render(ActivitiesView)
    // 模拟用户切到 groups + 选 blogger groups
    await fireEvent.click(screen.getByText('关键词组'))
    await fireEvent.click(screen.getByText('博主组'))
    // 点重置
    await fireEvent.click(screen.getByText('重置'))
    // 切回 custom
    expect(screen.queryByText('选择 1 个或多个关键词组')).toBeNull()
    expect(screen.queryByText('选择 1 个或多个博主组')).toBeNull()
  })
})
```

> 具体 mock 写法需对齐 [ActivitiesView.spec.ts](file:///Users/hanamaki_mac_mini/Documents/github/project/xhs-info-crawl/frontend/src/views/ActivitiesView.spec.ts) 既有 setup 风格（pinia / vi.mock / http mock）。遵循该文件已有约定。

- [ ] **Step 2: 跑测试**

```bash
cd frontend && npm run test -- --run src/views/ActivitiesView.spec.ts
```

预期：5 个新测试通过；如有失败，根据具体错误调整 mock。

- [ ] **Step 3: 提交**

```bash
git add frontend/src/views/ActivitiesView.spec.ts
git commit -m "test: ActivitiesView keyword group / blogger group filter spec"
```

---

## Task 10: 文档同步

**Files:**
- Modify: `docs/api-doc.md`
- Modify: `docs/database-design.md`

- [ ] **Step 1: api-doc.md 增 notes 新参数说明**

在 `docs/api-doc.md` 找到 `GET /api/v1/notes` 章节，参数表新增：

```
| keyword_group_ids | list[int] | 否 | 关键词组 ID 列表；与 keyword 互斥；同时传 422；多选 OR |
| blogger_group_ids | list[int] | 否 | 博主组 ID 列表；与 blogger_id 互斥；同时传 422；多选 OR |
```

并增"互动数"返回字段说明（list response items + 单条 detail）：

```
items[].like_count / collect_count / comment_count
```

- [ ] **Step 2: database-design.md 增 Note 字段**

在 `docs/database-design.md` 找到 notes 表，加 6 列：

```
| matched_keywords | JSON | NULL | 命中本次抓取的关键词列表（仅关键词维度） |
| matched_blogger_id | int | NULL | 命中本次抓取的博主 ID（仅博主维度） |
| matched_blogger_username | varchar(64) | NULL | 博主用户名快照 |
| like_count | int | NULL | 点赞数（详情抓取阶段落库） |
| collect_count | int | NULL | 收藏数 |
| comment_count | int | NULL | 评论数 |
```

- [ ] **Step 3: 提交**

```bash
git add docs/api-doc.md docs/database-design.md
git commit -m "docs: notes keyword_group_ids + blogger_group_ids + engagement fields"
```

---

## Task 11: 验证 + 文档收尾

**Files:** 无

- [ ] **Step 1: 后端全量测试**

```bash
cd backend && pytest -q
```

预期：全绿。

- [ ] **Step 2: 前端全量测试**

```bash
cd frontend && npm run test -- --run
```

预期：全绿。

- [ ] **Step 3: 前端类型检查**

```bash
cd frontend && npx vue-tsc --noEmit -p tsconfig.json
```

预期：0 error。

- [ ] **Step 4: 更新 docs/TODO.md**

在 `docs/TODO.md` 当前待办区域加：

```markdown
- [x] 活动管理（推文列表）按关键词组/博主组筛选（spec: 2026-08-13-activities-filter-by-groups-design）
  目标：ActivitiesView 加组筛选 + 落库 matched_* + 互动数
  验收：
  - 迁移 0022 成功
  - list_notes 支持 keyword_group_ids / blogger_group_ids，与 keyword / blogger_id 互斥 422
  - ActivitiesView UI 切换 + 表格 3 列互动数
  - 重启 celery worker（必须手动）
```

- [ ] **Step 5: 提示用户重启 celery worker**

输出给用户：

> 迁移 0022 已生效。**请手动重启 celery worker**（uvicorn 已自动 reload，但 worker 持旧 ORM 模型会触发 no such column）：
>
> ```bash
> # 在 backend 进程管理器或 terminal 里重启 celery worker
> # 视项目启动方式，例如：
> make restart-worker
> # 或 kill worker 进程后再启动
> ```

- [ ] **Step 6: 提交 TODO 更新**

```bash
git add -f docs/TODO.md
git commit -m "chore: mark activities group filter TODO done"
```

---

## Self-Review Checklist

- [x] Spec 覆盖：所有需求点（落库 6 字段、互斥筛选、UI 切换、3 列展示）均有任务
- [x] 占位扫描：所有步骤含完整代码，无 TBD
- [x] 类型一致：`keyword_group_ids / blogger_group_ids` 在 Task 4/5/7/8 一致
- [x] TDD 顺序：Task 3-5 测试先于 / 同步于实现
- [x] 验收：Task 11 含全量测试 + 重启 worker 提示
