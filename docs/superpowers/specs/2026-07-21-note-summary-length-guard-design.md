# 推文列表 summary 长度保护设计

> 状态：审核中。

## 1. 目标

`GET /notes` 列表每行返回的 `summary` 字段当前是"`正文：<content>` + 全部 `[图片 N OCR] <text>`"拼接，无上限。极端情况下（长正文 + 100 张图 + OCR 长）单行 summary 可达 MB 级别，前端表格渲染会被卡死、JSON 序列化慢。

## 2. 设计

### 2.1 列表接口 `_summary`

- 在 `_summary(note, count, ocr_texts)` 内做两件事：
  1. **OCR 截断**：`ocr_list` 仅取前 `MAX_OCR_BLOCKS = 5` 块（不破坏用户"看看图片说了啥"的诉求，且 5 块一般够定位）；尾部省略多余图片。
  2. **总长度截断**：把 parts 拼起来后若超过 `MAX_SUMMARY_BYTES = 4096`（UTF-8 字节），从尾部截断到 ≤ 4096，并附 `…`（中文省略）。响应里在每个 item 加 `"summary_truncated": true/false`。
- 详情接口（`_detail_data`）保留全部 OCR 原值（详情用），不截断——这是详情/列表的语义差异。

### 2.2 新增字段

每行 item 增 `summary_truncated: bool`，标识该行 summary 是否被截断。

## 3. 测试

### 3.1 单元 `tests/test_note_summary.py`

5 个 case：

1. `test_summary_includes_content_and_5_ocr_blocks`：seed 1 篇正文 + 8 张图 OCR → summary 含 `[图片 1 OCR]` 至 `[图片 5 OCR]`，不含 `[图片 6 OCR]`；
2. `test_summary_truncated_when_exceeds_4kb`：seed 1 篇正文 + 100 张图 OCR，每张 OCR 文本长 100 字符 → summary 字节数 ≤ 4096（用 `len(summary.encode('utf-8'))` 验证）且 `summary_truncated: true`；
3. `test_summary_under_4kb_not_truncated`：seed 普通 3 张图 → summary_truncated: false；
4. `test_summary_omitted_when_content_empty_and_no_ocr`：content 为空且 ocr_list 为空 → summary 是空字符串，`summary_truncated: false`；
5. `test_list_endpoint_returns_summary_truncated_field`：列表接口响应每行都有 `summary_truncated` 字段。
