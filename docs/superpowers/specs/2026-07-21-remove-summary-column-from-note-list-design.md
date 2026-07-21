# 移除推文列表 OCR 摘要列设计

> 状态：待审核。

## 1. 目标

推文列表当前有一列"摘要"，内容是把 `Note.content` 与 `images.ocr_text` 拼接（`正文：...` + `[图片 1 OCR] ...`），体量大、与"识别活动"功能重复定位；用户工作流是"看到识别活动数→点详情→看识别活动表格和图片 OCR"——摘要列的存在反而拥挤。

OCR 文字已经在：
1. 详情页"识别活动"表格上方的图片 OCR block；
2. 详情接口的 `images[].ocr_text` 字段；
3. 备注展示在前端"识别活动"表单摘要里（TODO A 加进去的）。

所以列表"摘要"列可以撤掉。

## 2. 已确认的产品规则

1. 列表移除"摘要"列；
2. 后端 `_summary` 字段**保留**：详情页还在用，未来如果需要别的展示方式可以复用；
3. 列表接口仍返回 `summary`（不破坏 schema），只是前端不展示。

## 3. 设计

### 3.1 前端

`frontend/src/views/ActivitiesView.vue`：

- 移除 `<ElTableColumn label="摘要" ...>`；
- 移除 `.row-summary` class 与对应 style。

### 3.2 测试

- `ActivitiesView.spec.ts` 移除"摘要"列相关断言；
- 删除 `summary` 在 mock `note.notes` 接口返回值里的 `summary` 字段可保留也可删，但前端完全不展示；
- E2E：`tests/test-note-list-no-summary.md` 新增。

## 4. 验收

- [ ] 前端 ActivitiesView 列表不再展示"摘要"列；
- [ ] 详情页（接口 `summary` 字段保留）依然能拿到完整内容，供前端需要时使用；
- [ ] 前端 vitest + 全部 e2e 全绿。

## 5. 范围之外

- 列表展示精简（只看城市/发布时间/标题/识别活动数）；
- 跨设备列宽优化。
