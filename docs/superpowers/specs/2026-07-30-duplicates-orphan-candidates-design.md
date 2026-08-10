# 去重候选悬空对与仪表盘/列表不一致修复

## 背景

仪表盘 `pending_duplicates` 与去重审核页面列表不一致：仪表盘按 `NoteDuplicateCandidate.status='pending'` 直接 COUNT（包括指向已 DELETED/MERGED 推文的悬空候选），而 `DuplicatesView.vue` 用 `Promise.all([api.note(a), api.note(b)])` 拉详情时单条 404 会让整批 reject，最终表格空。

例如当前库中候选 1（note_a_id=186 已 MERGED/DELETED）就是悬空 pending，导致：

- 仪表盘显示 4 条待审核
- 去重审核页列表为空

## 目标

1. 后端 `/api/v1/duplicates` 默认过滤：仅返回两侧 Note 都可见（`review_status NOT IN ('DELETED', 'MERGED')`）的 pending 候选。
2. 提供一次性脚本 `backend/scripts/prune_orphan_duplicates.py`，把指向已不可见 note 的 pending 候选标为 `superseded`，并补 `resolved_at`。脚本幂等。
3. 前端 `DuplicatesView.vue`：把每对详情改成 `Promise.allSettled`，单侧 404 不影响其它候选展示。
4. 测试用例文档 `tests/test-duplicates-api.md` 增补：悬空对过滤、悬空对 prune 幂等、DuplicatesView.spec.ts 加全部降级断言。

## 设计

### 后端

`/api/v1/duplicates`：

```python
stmt = select(NoteDuplicateCandidate).where(NoteDuplicateCandidate.status == 'pending')
stmt = stmt.join(Note, Note.id == NoteDuplicateCandidate.note_a_id).where(
    Note.review_status.notin_(['DELETED', 'MERGED'])
).join(aliased_Note_b, ...).where(b.review_status.notin_(['DELETED', 'MERGED']))
```

通过 join 双向过滤，pending 计数同步收敛。

合并端点 `/duplicates/{id}/merge` 保持现有行为不变；ignore 同样。

### 一次性脚本

```python
def prune_orphan_duplicates(db: Session) -> dict[str, int]:
    """把 note_a_id 或 note_b_id 不可见的 pending 候选标为 superseded。"""
```

调用方：

- 命令行：`python -m backend.scripts.prune_orphan_duplicates`
- 测试：`backend/tests/test_prune_orphan_duplicates.py`

### 前端

`DuplicatesView.vue` 第 9-13 行：

```ts
const items = (await api.duplicates()).data.data.items
rows.value = (
  await Promise.all(
    items.map(async (row: any) => {
      const [left, right] = await Promise.allSettled([
        api.note(row.note_a_id),
        api.note(row.note_b_id),
      ])
      if (left.status === 'rejected' || right.status === 'rejected') {
        return null
      }
      return {
        ...row,
        note_a: (left as any).value.data.data,
        note_b: (right as any).value.data.data,
      }
    }),
  )
).filter((row): row is object => row !== null)
```

## 验收

- 后端 `uv run --project backend pytest backend/tests/test_duplicates_orphan.py backend/tests/test_prune_orphan_duplicates.py -q` 全绿。
- 现有 `test_note_dedup_merge_cleanup.py`、`test_duplicates_api.py` 不退化。
- 前端 `npm --prefix frontend run test -- --run` 全绿，`DuplicatesView.spec.ts` 加 "skips orphan pairs without dropping the rest" 通过。
- `curl /api/v1/duplicates` 默认返回不再含候选 1。
- `python -m backend.scripts.prune_orphan_duplicates` 跑一次后，仪表盘 `pending_duplicates` 等于实际可点击列表条数。
- 已完成 TODO 项记入 [docs/TODO.md](file:///Users/kevin_w/Documents/github/xhs-info-crawl/docs/TODO.md)。