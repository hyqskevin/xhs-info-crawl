# 推文列表移除 OCR 摘要列 E2E 文档

关联 spec：`docs/superpowers/specs/2026-07-21-remove-summary-column-from-note-list-design.md`

## 步骤

1. 登录 → 进入「活动管理」。
2. 正常加载推文列表。

## 验收

- [ ] 列表头不包含「摘要」一列。
- [ ] 列表行不出现正文或 OCR 长文。
- [ ] 点击「详情」打开抽屉后，"识别活动"上方仍展示"标题/审核/正文/原文"；"识别活动"表格继续有开始时间/结束时间列。
- [ ] 列表宽度更紧凑，没有摘要列占用 320px min-width。

## 自动化

视觉走查：登录后访问 `/activities`，Playwright 断言 headers 不含「摘要」。
