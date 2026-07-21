# 周报选择器显示 ISO 周与日期范围设计

> 状态：审核中。

## 1. 背景

el-date-picker type="week" 显示"YYYY 第 ww 周"。中文用户经常会"按 el-picker 显示的周次"判断选择，但 ISO 周与 el-picker 内部算法的差异可能让用户选的"第 29 周"实际是自然周的另一周。

更严重：用户在前端看到 picker 标签"第 29 周"，期望生成 W29 周报，但后端实际接收到的 ISO 周可能不同。

## 2. 修复

1. picker format 改为 `YYYY/MM/DD`：picker 里**只显示周一日期**（避免周数歧义）。
2. picker 旁边增加 ISO 提示：`ISO 周：2026-W29 (7/13 ~ 7/19)`。
3. `toIsoWeek` 不变（已通过 spec 验证）。
4. 增加 `weekRangeLabel` 帮助函数：把 ISO 周字符串反查回日期范围。

## 3. 设计

### 3.1 改动

`ReportsView.vue`：

```vue
<ElDatePicker v-model="form.weekDate" type="week" format="YYYY/MM/DD" value-format="x" placeholder="选择周一" />
<span v-if="form.weekDate">ISO 周：{{ toIsoWeek(form.weekDate) }}（{{ weekRangeLabel(toIsoWeek(form.weekDate)) }}）</span>
```

```ts
function weekRangeLabel(week: string): string {
  // 反查 ISO 周对应日期范围
  // 通过该年第一个含周四那周的周一，加上 (week - 1) * 7 天，得到当前 ISO 周的周一；
  // 周日为 +6 天
}
```

## 4. 验收

- [ ] 选中 2026-07-13 显示 "ISO 周：2026-W29 (7/13 ~ 7/19)"；
- [ ] 选中 2026-07-06 显示 "ISO 周：2026-W28 (7/6 ~ 7/12)"；
- [ ] 选中 2026-12-31 显示 "ISO 周：2026-W53 (12/28 ~ 1/3)"；
- [ ] 前端 vitest 新增 3 个测试全绿。
