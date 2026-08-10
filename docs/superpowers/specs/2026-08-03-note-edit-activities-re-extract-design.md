# 推文编辑页展示活动 + 单条重提取 + 手动补充活动

**日期**: 2026-08-03
**状态**: 已审核

## 背景

当前推文编辑弹窗（`noteEditDialog`）只能编辑标题、正文、城市、发布时间，看不到该推文下已有的子活动。用户需要打开详情抽屉才能看到活动和操作。对于无子活动的推文，唯一的出路是 `reprocess`（清空所有数据回 PENDING 等重抓），不能单条重新提取活动。也无法手动补充活动。

## 目标

1. 推文编辑弹窗内展示已有子活动列表
2. 无活动时提供"重新提取"按钮，对单条推文重新跑 OCR + MiniMax 提取
3. 支持手动新增活动

## 设计

### 后端

#### 1. `POST /api/v1/notes/{note_id}/re-extract`

单条推文重新提取活动。不重抓图片，使用已有 OCR 数据（如无 OCR 则先跑 OCR）。

**流程**：
1. 校验 note 存在且可见
2. 读取已有 `NoteImage` 记录，取 OCR 文本
3. 如无 OCR 文本（OCR 未跑或失败），对已有图片文件重新跑 OCR
4. 拼合 `标题 + 正文 + OCR 文本`
5. 调 MiniMax 提取活动（如无 API key 则降级规则提取）
6. 跑 `activity_validator` 校验
7. 清除旧活动（软删除），写入新活动
8. 更新 `note.status` 为 `PROCESSED`（有活动）或 `NO_ACTIVITIES`/`EMPTY_RESULT_RETRYABLE`（无活动）
9. 返回提取结果（活动列表 + 状态）

**请求**: 无 body
**响应**:
```json
{
  "code": 200,
  "message": "success",
  "data": {
    "status": "PROCESSED",
    "activities": [{...}],
    "extracted_count": 3
  }
}
```

#### 2. `POST /api/v1/notes/{note_id}/activities`

手动为推文新增一条子活动。

**请求**:
```json
{
  "name": "活动名称",
  "location": "地点",
  "start_time": "2026-08-03T10:00:00",
  "end_time": "2026-08-03T18:00:00",
  "type": "市集",
  "summary": "活动简介"
}
```

**响应**: 201，返回新创建的 Activity 对象。

### 前端

**`ActivitiesView.vue` 编辑推文弹窗改造**：

1. 弹窗打开时（`openNoteEdit`）加载完整 note 详情（含 activities）
2. 弹窗内增加"识别活动"区域：
   - 已有活动：表格展示（名称、地点、开始时间、结束时间），每行可编辑/删除
   - 无活动：空态提示 + "重新提取"按钮
   - 底部：`+ 手动添加活动` 按钮
3. "重新提取"按钮：loading 态，调用 `POST /notes/{id}/re-extract`，成功后刷新活动列表
4. "手动添加"按钮：弹出活动表单（名称、地点、开始/结束时间、类型、简介），提交后调用 `POST /notes/{id}/activities`

## 不变的部分

- 详情抽屉（`ElDrawer`）的识别活动区域保持不变
- 活动编辑弹窗（`editDialog`）保持不变
- `reprocess` 端点不变

## 验收

- 编辑推文弹窗展示已有活动列表
- 无活动推文点击"重新提取"后跑 OCR→MiniMax→validator，成功则出现活动
- 手动添加活动表单提交后活动出现在列表
- 后端 `POST /notes/{id}/re-extract` 返回提取结果
- 后端 `POST /notes/{id}/activities` 创建活动成功
- 后端全量测试通过，前端 build 通过