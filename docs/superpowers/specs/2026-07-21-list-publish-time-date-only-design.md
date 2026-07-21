# 推文列表"发布时间"列只显示日期设计

> 状态：审核中。

## 1. 目标

当前推文列表"发布时间"列显示完整 ISO timestamp `2026/07/24 16:00:00`。按用户反馈**只显示日期 `2026-07-24`**，不含时分秒。

## 2. 规则

- 后端 `Note.published_at` 字段保持 DateTime 类型（精度到秒），不动 schema；
- **前端列表**: 新增 `formatDate()` 函数，`YYYY-MM-DD` 切前 10 个字符；
- 列表"发布时间"列改用 `formatDate`；
- 详情页"识别活动"表格的"开始时间/结束时间"列仍使用 `formatTime`（带时分秒，活动需要更精细）。

## 3. 设计

### 3.1 前端

`frontend/src/views/ActivitiesView.vue`：

```ts
function formatTime(value) { return value ? new Date(value).toLocaleString('zh-CN', { hour12: false }) : '待确认' }
function formatDate(value) { return value ? new Date(value).toISOString().slice(0, 10) : '待确认' }
```

`<ElTableColumn label="发布时间" ...>` 内用 `formatDate`。

### 3.2 测试

`ActivitiesView.spec.ts` 加 `shows the note publish time as YYYY-MM-DD only (no hours/minutes)`。

## 4. 验收

- [ ] 前端 16 个 vitest 全绿；
- [ ] Playwright 不变（推文列表"发布时间"列长宽可能略变）；
- [ ] 后端无变化，pytest 全绿。
