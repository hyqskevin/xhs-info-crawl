# 允许无子活动推文审核通过

**日期**: 2026-08-03
**状态**: 已审核

## 背景

当前审核规则：`POST /notes/{id}/review` 与 `POST /notes/batch/approve` 要求推文至少包含 1 条未删除的子活动（`Activity`）才能审核通过为 `APPROVED`。无子活动时单条返回 422，批量跳过并写入 `skipped`。

用户反馈：推文本身就是活动内容。小红书用户发布的推文（标题 + 正文 + 图片）已经包含了活动信息，即使 MiniMax 没有从中提取出结构化子活动，推文本身也应当能审核通过并进入周报。

## 目标

移除审核通过的前置活动数量校验，允许无子活动的推文审核通过。

## 设计

### 后端改动

**`backend/app/api/v1/notes.py`**

1. `review_note`（`POST /{note_id}/review`）：
   - 删除 APPROVED 分支的 `has_activity` 校验（第 199-204 行）
   - 直接设置 `note.review_status = payload.status`

2. `approve_notes`（`POST /batch/approve`）：
   - 删除 `activity_counts` 查询与跳过逻辑（第 260-276 行）
   - 批量直接设为 APPROVED，不再返回 `skipped` 明细
   - 响应结构简化为 `{"approved_ids": [...], "approved_count": N}`

### 不变的部分

- `POST /notes/{id}/reprocess` 保留，用户仍可对 `NO_ACTIVITIES` / `EMPTY_RESULT_RETRYABLE` 推文触发重处理
- 周报 `select_notes` 按 `review_status == "APPROVED"` 过滤，无活动推文进入周报时显示 `识别活动（0）`，不影响报告生成
- 前端 ActivitiesView 无需改动（审核按钮不依赖活动数量）

## 验收

- 单条审核：无子活动推文 `POST /notes/{id}/review {status: "APPROVED"}` 返回 200，`review_status` 变为 APPROVED
- 批量审核：无子活动推文不再被跳过，全部进入 `approved_ids`
- 既有测试：`test_batch_approve_skips_notes_without_activities` 行为改为全部通过不再跳过
- 后端全量测试通过，前端 build 通过