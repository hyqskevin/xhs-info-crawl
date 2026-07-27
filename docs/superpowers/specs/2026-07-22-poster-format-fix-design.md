# 海报格式修复（外框 + 右侧图片）

> 状态：已审核。修复用户反馈的两个问题：最外面框架缺失、右侧图片缺失。

## 1. 问题描述

用户反馈渲染后的海报与实际设计不符：
1. **最外面框架没有了** — 海报缺少外层橙色边框（外框）
2. **右边图片也没有** — 活动行右侧没有展示图片

## 2. 根因分析

### 2.1 外框缺失

原 `base_css` 中 `.poster` 容器直接铺满 body，无外边距和边框：
```css
body{background:#fff;}
.poster{width:1242px;height:2208px;padding:80px 60px;}
```

### 2.2 右侧图片缺失

原 `_render_item_html` 将图片放在正文区域（`row-body` td）内部，作为内容段落的内联元素，而非独立的右侧列：
```html
<td class="row-body">
  <p>🕐 ...</p>
  <p>📍 ...</p>
  <p>🎫 ...</p>
  <img src="..." />  <!-- 内联在正文中，非右侧 -->
</td>
```

造成两个问题：
- 图片不在右侧，视觉上不突出
- 当 `image_url` 为空字符串时，图片完全不渲染（`if image_url` 条件跳过）

## 3. 修复方案

### 3.1 外框：双层容器结构

```html
<body style="background:#F26B2C">              <!-- 橙色背景 = 外框色 -->
  <div class="poster-outer" style="padding:20px;background:#F26B2C">  <!-- 20px 外框 -->
    <div class="poster" style="background:#fff;border-radius:8px">    <!-- 内白卡片 -->
      <!-- 内容 -->
    </div>
  </div>
</body>
```

- body 背景色 = 外框色 `#F26B2C`
- `.poster-outer` 提供 20px padding（形成橙色边框视觉效果）
- `.poster` 内白卡片 1202×2168（含 80px padding 后可用区域 1082×2008）

### 3.2 右侧图片：三列 table 布局

```html
<table class="row-card-table">
  <tr>
    <td class="row-banner" width="360">标题</td>       <!-- 左：橙底白字 -->
    <td class="row-body">时间/地点/费用/内容</td>        <!-- 中：正文 -->
    <td class="row-image-cell" width="280">            <!-- 右：图片（仅 image_url 非空时） -->
      <img src="..." style="width:256px;height:256px;object-fit:cover"/>
    </td>
  </tr>
</table>
```

- 第三列仅当 `image_url` 非空时渲染
- 图片 256×256，object-fit:cover，圆角 8px

### 3.3 图片 URL 解析（渲染时）

新增 `resolve_item_image_urls()` 函数，将 API 路径（如 `/api/v1/posters/note-image-by-id/123`）解析为本地 `file://` 路径：

```python
def resolve_item_image_urls(items, db, data_dir) -> list[dict]:
    # 正则匹配 /api/v1/posters/note-image-by-id/{id}
    # 查 NoteImage 表获取 storage_key
    # 拼接为 file://{data_dir}/{storage_key}
```

在 render endpoint 中主线解析（避免跨线程传 DB session），然后传入 `render_poster_preview_html(items_override=...)`。

### 3.4 重构：提取 `_render_html_to_png`

将 `render_task_to_png` 中的渲染逻辑抽出为独立函数 `_render_html_to_png(html, output_path)`，方便 render endpoint 直接调用（已解析图片 URL 后）。

## 4. 影响范围

| 文件 | 改动 |
|---|---|
| `backend/app/services/poster_renderer.py` | 重构 `_render_item_html`、`base_css`、HTML 结构；新增 `resolve_item_image_urls`、`_render_html_to_png`；`render_poster_preview_html` 加 `items_override` 参数 |
| `backend/app/api/v1/poster_tasks.py` | render endpoint 主线解析图片 URL；import 更新 |

## 5. 验收

- [x] 后端 419 测试全过
- [x] 前端 57 测试全过
- [x] `_render_item_html` 有图片时渲染三列，无图片时两列
- [x] 生成 HTML 包含 `.poster-outer` 外框容器
- [x] `resolve_item_image_urls` 正确解析 API 路径为 `file://` 路径
- [x] `items_override` 参数可覆盖默认 items
- [ ] 真渲染端到端验证（需 opencli + 图片数据）