# 表格操作列不换行实施计划

> 按本计划一步步做即可。

**要做的事：** 列表页操作列的按钮在桌面端不换行；移动端按钮纵向堆叠；按钮太多的页面把次要按钮收到"更多"下拉菜单里。

---

## 步骤 1：写一个全局 CSS

新建 `frontend/src/assets/styles/table-actions.css`：

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

在 `frontend/src/main.ts` 里引入：

```ts
import './assets/styles/table-actions.css'
```

提交：`git commit -m "feat(ui): 新增全局操作列样式"`

---

## 步骤 2：改 4 个简单视图的列宽

改 4 个文件，每个文件只改一处（操作列宽度 + 加 class）：

| 文件 | 旧 | 新 |
|---|---|---|
| `frontend/src/views/ActivitiesView.vue` | `width="220"` | `min-width="280" class-name="action-column"` |
| `frontend/src/views/ReportsView.vue` | `min-width="280"` | `min-width="300" class-name="action-column"` |
| `frontend/src/views/TasksView.vue` | `width="100"` | `min-width="120" class-name="action-column"` |
| `frontend/src/views/SettingsView.vue`（关键词/城市两个操作列） | `width="180"` | `min-width="200" class-name="action-column"` |

写 4 个组件测试，断言每个视图的操作列都有 `action-column` 类。

跑测试 → 通过 → 提交：`git commit -m "feat(ui): 简单视图操作列改为 min-width + action-column"`

---

## 步骤 3：DuplicatesView 加抽屉收纳

修改 `frontend/src/views/DuplicatesView.vue`：

- 前两个按钮（保留 / 合并）直显
- 其余按钮（忽略 / 重新比对 / ...）收到 `ElDropdown` "更多 ▾" 菜单里

```vue
<ElTableColumn label="操作" min-width="320" class-name="action-column">
  <template #default="scope">
    <ElButton text type="primary" @click="keep(scope.row)">保留</ElButton>
    <ElButton text type="success" @click="merge(scope.row)">合并</ElButton>
    <ElDropdown @command="(c) => onMore(scope.row, c)">
      <ElButton text>更多 ▾</ElButton>
      <template #dropdown>
        <ElDropdownMenu>
          <ElDropdownItem command="ignore">忽略</ElDropdownItem>
          <ElDropdownItem command="recheck">重新比对</ElDropdownItem>
        </ElDropdownMenu>
      </template>
    </ElDropdown>
  </template>
</ElTableColumn>
```

写组件测试：点"更多"按钮，下拉菜单展开，断言有"忽略"和"重新比对"两个菜单项。

跑测试 → 通过 → 提交：`git commit -m "feat(ui): DuplicatesView 次要操作收进更多菜单"`

---

## 步骤 4：浏览器 E2E 验证分辨率

在 `frontend/e2e/business.spec.ts` 加 2 个测试：

1. 视口 1280px → 访问 `/activities`，断言 `.action-column .el-button` 的高度 < 50px（单行）
2. 视口 375px → 访问 `/activities`，断言第一个按钮的宽度 > 200px（占满）

跑测试 → 通过 → 提交：`git commit -m "test(ui): 操作列分辨率 E2E"`

---

## 步骤 5：更新文档

- `docs/ui-design.md`：补一句"操作列全局样式 + 抽屉收纳规则"
- `docs/README.md`：补 `table-actions.css` 文件说明
- `tests/test-frontend-ui-e2e.md`：补分辨率用例

提交：`git commit -m "docs: 同步操作列不换行设计"`

---

## 步骤 6：跑全量回归

```bash
cd frontend && npm run test:unit && npm run test:e2e
```

预期：全绿。

---

## 完成检查

- [ ] 桌面 1280px：5 个列表页操作按钮单行无折行
- [ ] 移动 375px：按钮纵向堆叠，可点击
- [ ] DuplicatesView "更多" 下拉菜单正常

---

## 不做什么

- 不改后端 API。
- 不换表格组件（如不换 VxeTable）。
- 不引入国际化文案。
- 不引入 Redis、MinIO、Docker。