# 识别活动表格增加开始/结束时间列 E2E 文档

关联 spec：`docs/superpowers/specs/2026-07-21-activities-drawer-add-date-columns-design.md`

## 步骤

1. 登录 → 进入「活动管理」。
2. 找到含至少 1 条活动的推文，点击"详情"。
3. 在抽屉中向下滚动至"识别活动"表格。

## 验收

- [ ] 表格表头顺序：「名称 / 地点 / 开始时间 / 结束时间 / 操作」。
- [ ] 活动行 "开始时间" 单元格显示合法时间字符串（格式 `YYYY-MM-DD HH:mm:ss`）。
- [ ] 当活动缺 `start_time` 时显示「待确认」。
- [ ] 当活动缺 `end_time` 时显示 `-`。
- [ ] 1280px+ 桌面分辨率下页面不出现横向滚动条。

## 自动化

```bash
cd frontend && npx playwright test tests/integration/drawer-activities-dates
```
