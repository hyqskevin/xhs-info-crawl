# 表格操作列不换行设计

## 1. 背景与已确认规则

当前多个列表页的操作列宽度硬编码，按钮在 1280px 及以上分辨率下出现文字/图标换行：

- `ActivitiesView.vue` `width="220"`，3 个按钮"详情 / 编辑审核 / 删除"。
- `ReportsView.vue` `min-width="280"`，3 个按钮"预览 / Markdown / Excel"。
- `DuplicatesView.vue` `width="260"`，多个按钮"保留 / 合并 / 忽略"。
- `SettingsView.vue` `width="180"`，2 个按钮"编辑 / 删除"。
- `TasksView.vue` `width="100"`，1 个按钮"日志"。

按钮默认 `text` 类型，无 `nowrap`，因此在列宽不足时文字会折行。

本次已确认的产品规则：

- 操作列按钮单行展示，不允许折行（桌面端 1280px 及以上）。
- 移动端允许按钮纵向堆叠，每个按钮占满整行宽度；保持可点击区域。
- 不修改后端 API；纯前端样式调整。
- 阶段一仍保持本地运行，不引入 Redis、MinIO 或 Docker。

## 2. 方案选择

采用"列宽自适应 + 按钮 `nowrap` + 抽屉收纳"三层方案：

- 列宽自适应：操作列改用 `min-width`，由 Element Plus 按内容计算建议宽度，并设置 `min-width` 下限保证单行。
- 按钮 `nowrap`：所有操作按钮加 `style="white-space: nowrap"`，禁止按钮内文字换行。
- 抽屉收纳：当按钮数 ≥ 4 时，前两个按钮直显，其余收入"更多"下拉菜单，保持总列宽可控。

不采用"全部固定宽度再加大"的方案，因为不同视图按钮数量不同，固定宽度仍会浪费或不足；也不采用"完全删除文字只保留图标"的方案，会牺牲可访问性。

## 3. 前端设计

### 3.1 通用样式

在 `frontend/src/assets/styles/table-actions.css` 新增：

```css
.action-column {
  white-space: nowrap;
}
.action-column .el-button {
  white-space: nowrap;
  padding-left: 8px;
  padding-right: 8px;
}
@media (max-width: 768px) {
  .action-column .el-button {
    display: block;
    width: 100%;
    margin-left: 0;
    margin-right: 0;
  }
}
```

### 3.2 各视图调整

| 视图 | 当前 | 改为 | 备注 |
|---|---|---|---|
| ActivitiesView.vue | `width="220"` | `min-width="280" class="action-column"` | 3 按钮 |
| ReportsView.vue | `min-width="280"` | `min-width="300" class="action-column"` | 3 按钮 |
| DuplicatesView.vue | `width="260"` | `min-width="320" class="action-column"` + 抽屉收纳 | ≥4 按钮 |
| SettingsView.vue | `width="180"` | `min-width="200" class="action-column"` | 2 按钮 |
| TasksView.vue | `width="100"` | `min-width="120" class="action-column"` | 1 按钮 |

### 3.3 DuplicatesView 抽屉收纳

新增 `ElDropdown` "更多"按钮，包含 ≥3 个次要操作；前两个主要操作（保留 / 合并）保留直显。

## 4. 数据流与错误隔离

- 仅样式变更，不影响业务逻辑。
- 列宽改动不触发接口调用，不影响分页、排序、筛选。
- 抽屉收纳的更多操作触发原有回调，不改变参数。

## 5. 测试设计

### 5.1 前端组件测试

- 各视图操作列在 1280px、1440px、1920px 分辨率下截图无折行。
- 移动端 375px 宽度下按钮纵向堆叠，每行可点击。
- DuplicatesView"更多"下拉菜单展开正常，触发原回调。

### 5.2 浏览器 E2E

- 在 1280px 视口下访问 ActivitiesView，操作列无横向滚动条。
- 在 375px 视口下访问 ActivitiesView，操作按钮纵向排列且可点击。

### 5.3 真实本地验证

- 桌面端访问 ActivitiesView、ReportsView、DuplicatesView、SettingsView、TasksView，操作按钮单行展示。
- 移动端访问同上，操作按钮纵向堆叠。

## 6. 文档同步范围

- `docs/ui-design.md`：表格操作列通用样式与抽屉收纳规则。
- `docs/README.md`：新增 `frontend/src/assets/styles/table-actions.css` 说明。
- `tests/test-frontend-ui-e2e.md`：覆盖分辨率用例。

## 7. 非目标

- 不修改后端 API。
- 不重写列表组件（如换成 VxeTable）。
- 不引入国际化文案（按钮文字保持中文）。
- 不引入第二阶段的 Redis、MinIO、Docker。