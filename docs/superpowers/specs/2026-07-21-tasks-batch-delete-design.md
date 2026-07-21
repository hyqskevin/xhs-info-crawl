# 抓取日志页批量删除设计

> 状态：审核中。

## 1. 目标

仪表盘"抓取日志"列表（`DashboardView`）当前每行只有"日志"和"停止"按钮。当数据库中累积几十条历史抓取任务（部分状态为 `STOPPED`、`COMPLETED`），用户需要逐条删除。

为加快清理：
- 给 `ElTable` 加 `<ElTableColumn type="selection">`，允许多选；
- 新增 `POST /api/v1/tasks/batch/delete` 端点，后端批量软删除 `Task` 行；
- 前端 toolbar 加"批量删除"按钮，调用新 API。

## 2. 设计

### 2.1 后端

- 新增 `DELETE /api/v1/tasks/batch` 接 `{ids: number[]}`；
- 校验：
  - `ids` 1 ≤ length ≤ 100；
  - 每个 id 是 int；
- 行为：根据 ids 找 `Task` 行，用 `db.delete()` 物理删除（不软删除，因为任务历史日志已经够用，重复跑任务会再生成）；
- 返回 `{deleted_count, deleted_ids}`。

注：测试时确认 SQLite 没有外键约束清理，如有 `Note.task_id` 引用，应先置 null 或保留外键。

### 2.2 前端

`DashboardView.vue`：

```vue
<ElTable :data="tasks" @selection-change="onSelectionChange">
  <ElTableColumn type="selection" width="48" />
  ...
</ElTable>
<ElButton type="danger" :icon="Delete" :disabled="!selectedTasks.length" :loading="batchDeleting" @click="batchDelete">批量删除</ElButton>
```

`selectedTasks` 数组跟踪当前选中行；`batchDelete` 调 `await api.batchDeleteTasks(selectedTasks.value.map(t => t.id))`，然后 `tasks.value = tasks.value.filter(...)`。

### 2.3 api.client

```ts
batchDeleteTasks: (ids:number[]) => http.delete('/tasks/batch', { data: { ids } }),
```

## 3. 测试

### 3.1 后端

`backend/tests/test_tasks_api.py` 加：

- `test_batch_delete_removes_tasks` —— seed 2 tasks → DELETE 2 → 验证 200 + deleted_count=2；
- `test_batch_delete_with_unknown_id_raises_422` —— 1 task 真实、1 task id 不存在 → 422 with id not found；
- `test_batch_delete_rejects_empty_or_too_many` —— `ids=[]` 422 / `ids=[1..101]` 422。

### 3.2 前端

`frontend/src/views/DashboardView.spec.ts` 加：

- 选择 2 个 task → 点"批量删除" → `api.batchDeleteTasks([id1, id2])` 被调用；tasks 状态过滤掉这 2 行。

## 4. 验收

- [ ] 后端 308+ tests pass；
- [ ] 前端 45+ tests pass；
- [ ] build 通过；
- [ ] 实际操作：仪表盘勾选 2 条 → 批量删除 → DB 中 2 行被删；
- [ ] Q&A 文档 `docs/superpowers/qa/dedup-rules.md` 已写。
