# 周报列表按 week 排序（不再按 id desc）

> 状态：审核中。

## 1. 目标

当前前端 `ReportsView.vue` 表格 `:data="rows"` 直接用 `rows.value`，按后端返回的顺序（id desc = 生成的顺序）展示。这导致：

- **用户选了 W29 生成后**：列表最顶部看到的是**最新生成**的（按生成时间序），而不是**最新周次**的；
- 用户看到"我明明选 29 周，列表顶部却是 28 周"——以为是 bug。

修复：前端用 `sortedRows` 替代 `rows`，**按 week 字符串 desc**，同一周内按 id desc。这样 W30 > W29 > W28 ... 自上而下。

## 2. 设计

```ts
const sortedRows = computed(() => [...rows.value].sort((a, b) => {
  if (a.week < b.week) return 1
  if (a.week > b.week) return -1
  return (b.id ?? 0) - (a.id ?? 0)
}))
```

模板里 `:data="sortedRows"`。

## 3. 测试

`ReportsView.spec.ts` 添加 `sorts the report list by week descending so the newest week is on top`，mock 返回 rows 有 W28、W29、W30 三条乱序，断言渲染顺序：W30 → W29 → W28。

## 4. 验收

- [ ] 前端 vitest 全绿；
- [ ] Playwright 仪表盘进入"周报"截图，行顺序符合 W30 → W29 → W28。
