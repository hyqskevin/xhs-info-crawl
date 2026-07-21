# 移除推文内子活动审核状态设计

> 状态：待审核。

## 1. 目标

子活动（`Activity`）只是 OCR 从推文图片识别出的活动信息，不应有"待审核/已通过/已驳回"等审核语义。

- 审核完全收敛到推文维度（`Note.review_status`）。
- 子活动只保留"存在 / 被软删除"两态，以及"被编辑"的审计时间。
- 删除 `Activity.status` 数据库列；用 `deleted_at: datetime | None` 表达软删除。
- 周报收录逻辑只过滤推文维度，不再过滤子活动的 status。
- 保留子活动的编辑与删除纠错能力。

## 2. 用户已确认的产品规则

1. 子活动不存在审核概念。
2. 子活动字段全部由 OCR 与人工编辑维护；展示 OCR 文字与日期。
3. 子活动允许编辑（名称、地点、城市、开始/结束时间、简介、来源 URL）和软删除。
4. 子活动详情不再有"状态"列，详情操作只剩"编辑"和"删除"。
5. 推文审核通过后，该推文下所有 `deleted_at IS NULL` 的子活动全部进入周报，不强制要求 `start_time` 在本周内。
6. 周报收录门槛：
   - 推文 `review_status == 'APPROVED'`
   - 推文 `published_at`（缺则 `created_at`）落在本周 `[week_start, week_end)`
   - 推文 `city_code` 命中
7. 历史脏数据迁移为最简单策略：所有现有 `status` 值（含 `RAW/APPROVED/PENDING/REJECTED/NEEDS_REVIEW/PUBLISHED/DELETED/MERGED`）一律视为存在 → `deleted_at = NULL`。
8. 删除的 `POST /api/v1/activities/batch/approve` 接口在迁移期间返回 `410 Gone`，提示前端停止使用；前端不再调用，工具栏不再渲染该按钮。

## 3. 设计

### 3.1 数据模型

#### `Activity`（`backend/app/models/activity.py`）

```python
class Activity(Base):
    __tablename__ = "activities"
    id: Mapped[int] = mapped_column(primary_key=True)
    note_id: Mapped[int | None] = mapped_column(Integer, index=True, nullable=True)
    name: Mapped[str] = mapped_column(String(256))
    city_code: Mapped[str] = mapped_column(String(32), index=True)
    start_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    end_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    location: Mapped[str] = mapped_column(String(256), default="")
    price: Mapped[str] = mapped_column(String(128), default="")
    type: Mapped[str] = mapped_column(String(64), index=True)
    source_url: Mapped[str] = mapped_column(String(512), default="")
    source_image_indexes: Mapped[list[int]] = mapped_column(JSON, default=list)
    summary: Mapped[str] = mapped_column(Text, default="")
    confidence: Mapped[float] = mapped_column(Float, default=1.0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
```

字段变化：

- 删除 `status` 列与索引。
- 新增 `deleted_at: datetime | None`（可空，带索引），用于软删除。
- `updated_at` 加 `onupdate` 自动更新（审计编辑历史）。

#### Alembic 迁移（`backend/migrations/versions/0011_activity_soft_delete.py`）

`upgrade()`：

1. 新增 `deleted_at` 列：可空 datetime(timezone=True)，建索引 `ix_activities_deleted_at`。
2. 将现有所有行的 `deleted_at` 设为 `NULL`（脏数据统一保留）。
3. 删除 `status` 列与其索引（如有：现有索引名 `ix_activities_status`）。

`downgrade()`：

1. 重建 `status` 列，默认 `ACTIVE`。
2. 已软删除的行回填 `status = 'DELETED'`。
3. 删除 `deleted_at` 列。

### 3.2 Schema

#### `backend/app/schemas/activity.py`

```python
class ActivityCreate(BaseModel):
    name: str
    city_code: str
    start_time: datetime | None = None
    end_time: datetime | None = None
    location: str = ""
    price: str = ""
    type: str
    source_url: str = ""
    summary: str = ""
    confidence: float = 1.0


class ActivityUpdate(BaseModel):
    name: str | None = None
    city_code: str | None = None
    start_time: datetime | None = None
    end_time: datetime | None = None
    location: str | None = None
    price: str | None = None
    type: str | None = None
    source_url: str | None = None
    summary: str | None = None


class ActivityRead(ActivityCreate):
    model_config = ConfigDict(from_attributes=True)
    id: int
    note_id: int | None = None
    source_image_indexes: list[int] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None = None
```

- 删除 `ActivityCreate.status` / `ActivityUpdate.status`。
- `ActivityRead` 新增 `deleted_at`。
- 不在响应中暴露字段名为 `status`。

### 3.3 API

#### `backend/app/api/v1/activities.py`

| 路由 | 现状 | 改后 |
|---|---|---|
| `GET /activities` | `WHERE status NOT IN (DELETED, MERGED)` + 接受 `?status=` | `WHERE deleted_at IS NULL`；移除 `?status=` 参数 |
| `GET /activities/{id}` | 默认过滤软删 | `WHERE deleted_at IS NULL` |
| `GET /activities/{id}?include_deleted=true` | 过滤软删 | 保留；不再依赖 status 含义 |
| `POST /activities/batch/approve` | 写 `status='APPROVED'` | 返回 `410 Gone`，`detail="活动审核已迁到推文维度，请使用 /notes/{id}/review"` |
| `DELETE /activities/{id}` | 写 `status='DELETED'` | `SET deleted_at = NOW()` |
| `DELETE /activities/batch` | 写 `status='DELETED'` | `SET deleted_at = NOW()` |
| `PUT /activities/{id}` | 含 status 转换校验、防 PUBLISHED→RAW | 删除状态转换校验；保留 `updated_at` 写入 |
| `POST /activities/{id}/opencli`（若有） | n/a | 不变 |

#### `backend/app/api/v1/reports.py`

`select_notes` 周报收录逻辑保持对子活动不过滤 status：

```python
def select_notes(db, cities, week):
    start, end = week_bounds(week)
    published = func.coalesce(Note.published_at, Note.created_at)
    notes = list(db.scalars(select(Note).where(
        Note.city_code.in_(cities),
        Note.review_status == "APPROVED",
        published >= start,
        published < end,
    ).order_by(published, Note.id)).all())
    entries = []
    for note in notes:
        activities = list(db.scalars(
            select(Activity)
            .where(Activity.note_id == note.id, Activity.deleted_at.is_(None))
            .order_by(Activity.id)
        ).all())
        images = list(db.scalars(select(NoteImage).where(NoteImage.note_id == note.id).order_by(NoteImage.id)).all())
        entries.append((note, activities, images))
    return entries
```

关键点：

- 子活动筛选从 `status NOT IN (DELETED, MERGED)` 改为 `deleted_at IS NULL`。
- 删除 `status == "APPROVED"` 与 `start_time IS NOT NULL` 过滤 —— 子活动全部进入周报。

### 3.4 服务

#### `backend/app/services/extraction.py`

抽取结果构造 `Activity` 时不再写 `status`：

```python
item.pop("status", None)
item["confidence"] = ...
return Activity(**filtered)
```

#### `backend/app/services/dedup.py`

- `merge_activities()` 返回 dict 中删除 `status = "APPROVED"` 赋值。
- `create_duplicate_candidates()` 过滤改为 `Activity.deleted_at.is_(None)`。
- `create_note_duplicate_candidates()` 仍基于 `Note`，不变。

#### `backend/app/services/report.py`

- 删除 `approved()` 函数。
- `generate_markdown` / `generate_xlsx` 不存在活动列表（已废弃的旧 weekly 路径），如保留则不过滤 status。
- `generate_note_markdown` / `generate_note_xlsx` 已由 `reports.select_notes` 过滤，不变。

### 3.5 前端

#### `frontend/src/views/ActivitiesView.vue`

- `filters` 删除 `review_status` 仍保留于 Note 维度；删除活动级 status 筛选（已不存在）。
- 详情活动表格删除"状态"列：
  - `<ElTableColumn label="操作" width="150">` 中"编辑/删除"按钮保留。
  - 删除 `<ElTableColumn label="状态" width="100">`。
- 工具栏删除 `批量通过` 按钮（`batchApprove` 函数 + 状态）。
- 详情头部推送"通过/驳回"属于 Note 层，保留。

#### `frontend/src/api/client.ts`

- 移除 `batchApprove` 调用入口（如存在）。
- 移除 `?status=` 参数（如使用）。

#### `frontend/src/views/ActivitiesView.spec.ts`

- 删除与活动状态相关的断言（`status: 'APPROVED'`、`status: 'RAW'` 等）。
- 断言详情表无"状态"列、无"批量通过"按钮。
- 保留推文级 `review_status` 断言。

#### `frontend/e2e/documented-flows.spec.ts`

- 不再断言活动级 `APPROVED`，代之以"活动列表展示".

### 3.6 测试案例

#### `backend/tests/test_activities_api.py`

新增/调整：

- `test_list_activities_filters_by_deleted_at`
  - 插入 3 条活动，1 条软删；`GET /activities` 返回 2 条。
- `test_update_activity_no_longer_validates_status_transition`
  - `PUT /activities/{id}` 不再因 status 转换返 422。
- `test_batch_approve_returns_410_gone`
  - `POST /activities/batch/approve` 返回 410 与清晰 detail。
- `test_delete_activity_uses_deleted_at`
  - `DELETE /activities/{id}` 后 `deleted_at` 非 NULL，列表查不到。

调整现有：

- `make_activity` 工厂删除 `status` 参数。
- 删除 `test_batch_approve` 旧用例。
- 删除 `test_update_activity_rejects_invalid_status_transition` 旧用例。

#### `backend/tests/test_activity_status_removal.py`（新文件）

- 数据库 schema 已经没有 `Activity.status` 列（model 加载不报错）。
- 历史脏数据迁移后无 5xx。
- 周报收录：1 篇 APPROVED 推文下的所有 `deleted_at IS NULL` 子活动全部出现在 markdown/xlsx 内；删除 1 条子活动后该条不在周报内。

#### `tests/test-activity-soft-delete-and-report-include.md`（E2E 文档）

- 后端运行模型迁移后启动服务。
- 推文审核通过；周报导出 markdown 含 OCR 全部子活动。
- 软删除子活动后周报不再含该条。

### 3.7 文档

- `docs/api-doc.md`：移除 `/activities/batch/approve` 接口；更新字段表。
- `docs/database-design.md`：`Activity` 表删除 status，新增 deleted_at。
- `SPEC.md`：同步更新"活动管理"段。

## 4. 验收

### 数据层

- [ ] `activities.status` 列已删除；`activities.deleted_at` 列存在并可空。
- [ ] 迁移升级/回滚均可执行。
- [ ] 现有数据全部可读，无外键/索引故障。

### 后端 API

- [ ] `GET /activities` 默认不返回软删；`?status=` 参数被忽略或拒绝（返回 422）。
- [ ] `DELETE /activities/{id}` 后 `deleted_at` 非 NULL，列表不再出现。
- [ ] `POST /activities/batch/approve` 返回 `410 Gone`。
- [ ] `PUT /activities/{id}` 不再校验 status 转换。

### 业务逻辑

- [ ] 抽取创建 `Activity` 不写 status。
- [ ] dedup `merge_activities` 返回的 dict 不包含 status。
- [ ] dedup 候选过滤使用 `deleted_at IS NULL`。

### 周报

- [ ] 1 篇 `APPROVED` 推文下全部未删除子活动全部进入 markdown/xlsx。
- [ ] 软删除一条子活动后，该条不出现在周报内。
- [ ] 推文未审核通过或非本周 → 整篇推文不进周报。
- [ ] 子活动无需 `start_time` 在本周内。

### 前端

- [ ] 详情表去掉"状态"列。
- [ ] 工具栏去掉"批量通过"按钮。
- [ ] 编辑活动表单不包含 status。
- [ ] 推文级"通过/驳回"按钮保留。
- [ ] 详情活动行展示 OCR 文字 + 日期（与 TODO 4 协同，但本 TODO 只删除状态相关渲染）。

### 测试

- [ ] 后端全量 `pytest -q` 通过，新增/调整的测试覆盖上述断言。
- [ ] 前端组件测试 `npm run test -- --run` 通过。
- [ ] Playwright E2E 通过。
- [ ] 迁移在干净库与已有库下均成功。

## 5. 风险与回滚

| 风险 | 缓解 |
|---|---|
| 旧 API 调用方仍请求 `?status=` | 后端忽略参数；前端移除调用。`/batch/approve` 返回 410 引导下线。 |
| 历史脏数据被一刀切视为存在 | 已知行为；如需更细粒度回填，提供单独迁移脚本。 |
| 周报选材变广导致 markdown 体量上升 | 由 Note 维度筛选约束范围；后续可按需收紧。 |
| dedup 过滤条件改写引入回归 | 新增单元测试覆盖候选创建过滤；全量测试通过。 |

## 6. 范围之外

- TODO 2（真实发布时间解析）与本 TODO 独立。
- TODO 4（OCR 摘要展示）独立；本 TODO 不动 OCR 文本字段。
- 阶段二（PostgreSQL / Redis / MinIO）独立。
