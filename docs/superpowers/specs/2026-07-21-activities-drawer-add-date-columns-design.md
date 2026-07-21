# 识别活动表格增加「开始时间」与「结束时间」两列设计

> 状态：待审核。

## 1. 目标

推文详情面板里的"识别活动"表格目前只显示 `名称 / 地点 / 操作`，**用户看不到活动发生时间**，必须点击"编辑"才能看到。增加两列展示 `start_time` 与 `end_time`，缺值显示 "待确认"。

## 2. 已确认的产品规则

1. 表格列顺序：**名称 → 地点 → 开始时间 → 结束时间 → 操作**。
2. `start_time` 缺值显示 `待确认`，`end_time` 缺值显示 `-`（空）。
3. 时间格式与列表"发布时间"列一致：`zh-CN` `Asia/Shanghai`，格式 `YYYY-MM-DD HH:mm:ss`。
4. 行宽自适应，桌面 1300px+ 不出现横向滚动。
5. 移动端 / `< 768px` 折叠为「名称 / 时间 / 操作」三列（地点隐藏）。与列表"详情抽屉"的响应式一致。

## 3. 设计

### 3.1 数据来源

- 后端 `/api/v1/notes/{id}` 已经返回 `activities[].start_time` 与 `activities[].end_time`，不需要改动。
- 与 `formatTime(value)` 工具函数复用：列表已经定义，前端再用一次。

### 3.2 前端实现

`frontend/src/views/ActivitiesView.vue`：

```vue
<ElTable :data="detail.activities || []">
  <ElTableColumn prop="name" label="名称" min-width="160" />
  <ElTableColumn prop="location" label="地点" min-width="140" />
  <ElTableColumn label="开始时间" min-width="160" show-overflow-tooltip>
    <template #default="scope">{{ formatTime(scope.row.start_time) }}</template>
  </ElTableColumn>
  <ElTableColumn label="结束时间" min-width="160" show-overflow-tooltip>
    <template #default="scope">{{ scope.row.end_time ? formatTime(scope.row.end_time) : '-' }}</template>
  </ElTableColumn>
  <ElTableColumn label="操作" width="150">...</ElTableColumn>
</ElTable>
```

`formatTime` 已存在；"待确认"逻辑内置：value 为 null 时返回 "待确认"。end_time 处理为空字符串时也回退到 `-`。

### 3.3 测试

- `frontend/src/views/ActivitiesView.spec.ts`：mock 详情含两条 activities（含 start_time/end_time/缺值），点详情后断言表头包含"开始时间"和"结束时间"、行渲染正确。
- `tests/test-drawer-activities-dates.md`：E2E 文档描述"进入详情抽屉→活动表格有 5 列"。

## 4. 验收

### 后端

- 列表/详情接口不变；后端测试 0 改动。

### 前端

- [ ] 活动表格列从 3 列改 5 列。
- [ ] 开始时间为空显示「待确认」、结束时间为空显示「-」。
- [ ] 全部 vitest + Playwright 全绿。

### E2E

- [ ] `tests/test-drawer-activities-dates.md` 落地。

## 5. 范围之外

- 列宽与滚动布局优化（如有需要后续独立 TODO）。
- 「日期冲突」类视觉提醒。
- 详情页活动表格的服务端排序。
