# 推文摘要列展示 OCR 文字与日期设计

> 状态：待审核。

## 1. 目标

活动管理列表新增"摘要"列，把推文原始文字和图片 OCR 识别出的文字**完整拼接**展示，可识别的日期带上日期。

- 列表一行展示：推文正文 + 图片 OCR 文字片段（按图片顺序）。
- 解析到的日期（如 `2025-07-20`、`7月20日`）以文本形式保留。
- 不再让用户进入详情才能看到 OCR 文字。

## 2. 已确认的产品规则

1. 列表"摘要"列的输出形如：
   ```
   标题：XXX
   正文：<Note.content>
   [图片 1 OCR] 2025-07-20 18:00  徐汇滨江 本周六市集
   [图片 2 OCR] 8月1日 展览信息 ...
   ```
2. 字段缺失部分跳过，不写占位符。
3. 摘要过长时使用 `show-overflow-tooltip` 鼠标悬浮看完整内容。
4. 后端聚合逻辑只发生在 `GET /api/v1/notes`，不新增独立接口。

## 3. 设计

### 3.1 后端聚合

`backend/app/api/v1/notes.py::_summary` 改为接收 `ocr_texts: list[str]`：

```python
def _summary(note: Note, activity_count: int, ocr_texts: list[str]) -> dict:
    parts = [f"正文：{note.content}"] if note.content else []
    for index, text in enumerate(ocr_texts, 1):
        if text:
            parts.append(f"[图片 {index} OCR] {text}")
    return {
        "id": note.id,
        "title": note.title,
        "city_code": note.city_code,
        "published_at": note.published_at,
        "created_at": note.created_at,
        "processing_status": note.status,
        "review_status": note.review_status,
        "activity_count": activity_count,
        "source_url": note.source_url,
        "summary": "\n".join(parts),
    }
```

列表查询时一次性 LEFT JOIN `note_images`，取 `ocr_text`，按 `Note.id` 分组拼装。

### 3.2 不发新接口

继续使用 `GET /api/v1/notes`，响应 `data.items[].summary`。

### 3.3 前端

`frontend/src/views/ActivitiesView.vue`：

- 列表 `<ElTableColumn prop="summary" label="摘要" min-width="320" show-overflow-tooltip />`。
- 当 `summary` 为空或仅含"正文"且 content 也为空时，展示"—"。
- 详情页"识别活动"上方新增"OCR 摘要"块，复用详情接口已有的 `images[].ocr_text`。

## 4. 验收

### 后端

- [ ] `GET /api/v1/notes` 每行都返回 `summary` 字段，含正文与 OCR 拼接。
- [ ] OCR 文字为空时不写入。
- [ ] N 条推文：聚合 N 条 NoteImage 行的 `ocr_text`，按图片 `id` 排序。

### 前端

- [ ] 活动管理列表新增"摘要"列。
- [ ] 摘要过长时悬浮 Tooltip 显示完整内容。
- [ ] 详情页"OCR 摘要"展示同样信息。

## 5. 范围之外

- 后端 OCR 文本不在 response 中改变（仍保留 `images[].ocr_text`）。
