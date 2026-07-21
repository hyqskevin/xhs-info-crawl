# 推文零活动处理与"活动 ≥ 推文发布时间"判定测试案例

关联 spec：`docs/superpowers/specs/2026-07-21-zero-activity-and-window-fix-design.md`

## 后端校验

1. `activity_validator.validate_activities`：
   - `activity.start_time >= note.published_at`：accepted；
   - `activity.start_time < note.published_at`：rejected，理由包含"早于推文发布时间"；
   - `note.published_at IS NULL`：全部接收；
   - `start_time` 无法解析：rejected，记录"无法解析"。
2. `classify_zero_activity` 三态：
   - 全部早于 `published_at`：`all_before_publish`；
   - MiniMax 空 + 正文有活动信号：`minimax_empty_retryable`；
   - MiniMax 空 + 正文无信号：`no_activity_signals`。

## 入库流程

1. `process_note` 在 OCR+提取后调 `activity_validator`：
   - `note.status` 进入 `NO_ACTIVITIES` 或 `EMPTY_RESULT_RETRYABLE`；
   - `skipped_activities` 增加：跳过原因记录到日志（含"活动日期 X 早于推文发布时间 Y"）；
   - 不再使用 `ActivityWindow` 60 天窗口。
2. `process_note` 不再用任务开始时间作 `now`，改为 `Note.published_at`（缺则 `started_at` 兜底）。
3. 解析降级：`7.18`、`7/18`、`7.18 18:30`、`7月18日` 能用 `Note.published_at` 年份正确解析；跨年回退。

## 审核 / 周报

1. `POST /api/v1/notes/{id}/review` 当 `target='APPROVED'`：
   - 若该推文无任何未删除子活动，返回 `422` "推文无有效子活动，请先重新处理"；
   - 若 `target='REJECTED'`，允许 0 子活动（驳回不需要有活动）。
2. 推文 `review_status == APPROVED` 但 0 活动时，不能被当作已"可审核"通过；运营人员必须先 `reprocess`。
3. 周报收录（`select_notes`）：
   - `note.published_at IS NOT NULL`；
   - 本周 `published_at` 区间；
   - `note.review_status = APPROVED`；
   - 隐式至少 1 条 `deleted_at IS NULL` 子活动（review 接口已校验）。

## 重处理

1. `POST /api/v1/notes/{id}/reprocess`：
   - 仅当 `note.status ∈ {NO_ACTIVITIES, EMPTY_RESULT_RETRYABLE}` 返回 `202`；
   - 清除该推文所有 `NoteImage` 与 `Activity`，重置 `status=PENDING`，`published_at=null`；
   - 调用 `tasks/{id}/restart` 触发实际重抓取。
2. 其他状态返回 `409`。
3. 已审核（`APPROVED`/`REJECTED`）推文不允许 reprocess（避免破坏审计）。

## 前端

1. 推文编辑表单：状态为 `NO_ACTIVITIES` 时显示"未识别到活动，请重新处理"。
2. 详情页"重新处理"按钮：
   - 仅当 `note.status in {NO_ACTIVITIES, EMPTY_RESULT_RETRYABLE}` 时可见；
   - 点击后调用 `POST /notes/{id}/reprocess`，成功后显示 Toast 并刷新详情。
3. 已审核通过的推文不能再 reprocess。

## 验收命令

```bash
cd backend && .venv/bin/pytest -q
cd ../frontend && npm run test -- --run
npm run build
npx playwright test
cd .. && git diff --check
```
