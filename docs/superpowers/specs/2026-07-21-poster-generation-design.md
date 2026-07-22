# 海报生成（Poster Generation）设计

> 状态：审核中。**v3** 重写：补 `docs/海报制作.md` 全部 6 条 + 用户对话中的 4 条扩展要求。

## 1. 用户原始 6 条 + 我的扩展

1. 配置中心 navbar 增加 2 子 nav：参数配置 / 海报模板；
2. 海报模板支持上传 → **调用 minimax 图片识别/OCR 能力**，识别排版 / 配色 / 字体 / emoji / 背景 / 文字位置 / 图片位置 → 生成 HTML 模板；
3. 模板列表管理：查看 / 编辑 / 删除；
4. 新增 navbar 海报制作：选活动 → 选模板 → 填字段（**支持单推文 / 单活动两种粒度**） → 人工改 → **选原推文图展示（可单选，海报从推文原图来）** → 生成；
5. 海报列表管理；
6. 每次海报生成都作为 **PosterTask** 任务，保存所选活动/单推文 id、模板 id、引用的图片地址。

**扩展要求 4 条（用户对话补充）**：

- 活动列表以**推文**为单位；推文下可挂多个活动；
- 同时支持**单推文填充**（一个推文一行）与**单活动填充**（一个活动一行）两种粒度；
- 展示图必须从**原推文图片**里选（单选）；
- 渲染优先 **Playwright**（chromium headless），不够时 fallback **opencli**（截图能力）。

## 2. 数据模型

### 2.1 `poster_templates`

| 列 | 类型 | 说明 |
|---|---|---|
| id | int PK | |
| name | str(128) unique | 模板名 |
| description | text nullable | |
| html_template | text | HTML+CSS 模板字符串 |
| css_text | text nullable | 配套 CSS（默认合并到 style 标签） |
| thumbnail_path | str nullable | 自动渲染缩略图 |
| parsed_meta | json nullable | LLM 解析结果：fonts / colors / emoji / positions |
| source | str default 'manual' | 'manual' / 'minimax-vision' |
| created_at / updated_at | tz datetime | |

### 2.2 `poster_tasks`

| 列 | 类型 | 说明 |
|---|---|---|
| id | int PK | |
| name | str(128) | 任务名（用户改） |
| status | str(32) default 'draft' | draft / rendered / archived / failed |
| template_id | int FK → poster_templates ON DELETE RESTRICT | |
| items | json | 列表：`[{type:'note'|'activity', id, filled_fields, image_url}, ...]`（多推文/多活动共一数组） |
| override_html | text nullable | 用户人工编辑 HTML |
| output_path | str nullable | 渲染产物路径（PNG） |
| output_format | str default 'png' | png / html（HTML 可让前端用 Playwright 重新截屏） |
| created_at / updated_at | | |

`items` 每条形如：
```json
{ "type": "note", "note_id": 1234, "title": "宁波周末活动",
  "fields": {"time_range": "7.4 16:00-17:00", "location": "宁波万象汇L1", "fee": "免费", "content": "..."},
  "image_url": "/data/images/note-1234/0.jpg" }
```
`{ "type": "activity", "note_id": 1234, "activity_id": 567, ...}`：活动归属推文，但 src image 在 note 上。

### 2.3 `migration 0014_poster_models.py`

- 新建 2 表；
- 不破坏现有数据；
- 不加 FK 到 activities / notes（保持 items 灵活；状态无效时由代码端校验）。

## 3. API 设计

### 3.1 模板（配置中心调用）

| Method | Path | 说明 |
|---|---|---|
| GET | `/api/v1/settings/poster-templates` | 列表 |
| GET | `/api/v1/settings/poster-templates/{id}` | 详情（含 html/css/parsed_meta） |
| POST | `/api/v1/settings/poster-templates` | 手动创建 |
| PUT | `/api/v1/settings/poster-templates/{id}` | 编辑 |
| DELETE | `/api/v1/settings/poster-templates/{id}` | 删除 |
| POST | `/api/v1/settings/poster-templates/parse-from-image` | multipart 上传 → minimax 图片识别/OCR → 返回 HTML 草稿 + parsed_meta |

### 3.2 任务（海报制作顶 nav 调用）

| Method | Path | 说明 |
|---|---|---|
| GET | `/api/v1/poster-tasks` | 列表（含 status） |
| GET | `/api/v1/poster-tasks/{id}` | 详情 |
| POST | `/api/v1/poster-tasks` | 创建（draft，含 items / template_id） |
| PUT | `/api/v1/poster-tasks/{id}` | 更新 items / override_html |
| DELETE | `/api/v1/poster-tasks/{id}` | 删除 |
| POST | `/api/v1/poster-tasks/{id}/render` | 服务端 Playwright headless 渲染 PNG，写 `data/posters/{task_id}.png`，回填 output_path |
| GET | `/api/v1/poster-tasks/{id}/preview` | HTML（不渲染） → 前端 iframe 预览 |
| GET | `/api/v1/poster-tasks/{id}/download` | 下载渲染产物 |

### 3.3 辅助端点（前端流程使用）

| Method | Path | 说明 |
|---|---|---|
| GET | `/api/v1/poster-tasks/candidates` | 入参 `?city_code=&keyword=&q=` → 返回可作为 items 的推文/活动列表，含每个候选 note 的图片 URLs |
| GET | `/api/v1/posters/note-images/{note_id}` | 返回某推文的所有图 URL（单选用：可加 `?index=`） |

## 4. AI 识别海报（minimax vision / OCR）

### 4.1 调用流程

```
POST settings/poster-templates/parse-from-image
  multipart/form-data { image: <file> }
    ↓
读文件 → base64 / data URI
    ↓
调 MiniMaxClient.vision_parse(image_b64, instruction)
  返回 { html_template, css_text, parsed_meta: {fonts, colors, emoji, layout_blocks, positions}, name_suggestion }
    ↓
落地候选供保存
```

`MiniMaxClient` 当前没有 vision 接口；扩展：
```python
def vision_parse(image_b64: str, instruction: str) -> dict:
    payload = {
      "model": self.settings.minimax_vision_model,  # 假定 default "minimax-vision-01"
      "messages": [
        {"role": "system", "name": "poster_parser", "content": instruction},
        {"role": "user", "name": "user", "content": [
            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"}},
        ]},
      ],
      "max_completion_tokens": 4096,
    }
    ...
```

落地 `tools=` 让 LLM 输出结构化 JSON。`parsed_meta` schema：

```json
{
  "fonts": ["PingFang SC", "Noto Sans CJK SC"],
  "colors": {"primary": "#F26B2C", "bg": "#FFFFFF", "text": "#222222"},
  "emoji": ["🕐", "📍", "🎫"],
  "layout_blocks": [
    {"type": "title", "x": 60, "y": 60, "w": 1122, "h": 200},
    {"type": "subtitle_date", "x": 60, "y": 280, "w": 1122, "h": 100},
    {"type": "card_row", "x": 60, "y": 420, "w": 1122, "h": 320, "per_item_gap": 32}
  ]
}
```

如果 vision 不可用：返回 503，前端跳"手动编辑 HTML"页。

## 5. 渲染（Playwright，opencli 兜底）

### 5.1 Playwright 路径（首选）

`backend/app/services/poster_renderer.py`：

- `render_poster(task)` → 调用 `playwright.sync_api.sync_playwright()`；
- 安装：`playwright install chromium`（一次性下载）；
- HTML 拼装：模板 + `items` 填字段（每 item 一行）+ 选择图 base64 内嵌或 file://；
- viewport：默认 1242×2208；
- `page.set_content(html, wait_until="networkidle")`；
- `page.screenshot(path=output, full_page=True)`，output 写到 `data/posters/`;
- 真实图片使用 file URI 让 chromium 加载；或 base64 内嵌。

### 5.2 opencli fallback

若 playwright 在 runtime 不可用（极端），**回退 opencli**：
- 调 `opencli screenshot --html <path> --output <path>` 由外部 opencli 完成；
- 若 opencli 也不可用 → 返回 503 `{"code":503,"message":"renderer unavailable"}`。

### 5.3 dev 脱机

开发/CI 环境无 chromium 时，`render_poster` 返回 None；UI 通过 `preview` 端点（仅返回拼装后的 HTML 字符串）依然能看：

```python
GET /poster-tasks/{id}/preview -> { "code":200, "data":{"html":"<html>...</html>", "items_count":3} }
```

## 6. 前端

### 6.1 nav 调整

- `SettingsView` 增加顶部 tab：**参数配置 / 海报模板**；参数配置内部仍有 cities/bloggers/keyword-groups；
- 新顶 nav **海报制作**：仅 `/posters`、`/posters/new` 两个路由；
  - `/posters` 显示 PosterTask 列表；
  - `/posters/new` 是 wizard 多步表单。

### 6.2 PosterWizard（多步）

```
Step 1: 选择范围（推文 / 活动）
  - radio: 推文为单位 / 活动为单位
  - 搜索 + 多选 / 单选表格（来自 /poster-tasks/candidates）
Step 2: 选模板（单选）
  - 来自 settings/poster-templates 列表
Step 3: 填字段（按所选粒度一行动一行）
  - 推文为单位：每条推文 = 一行字段（time_range / location / fee / content）
  - 活动为单位：每个活动 = 一行
Step 4: 人工编辑 HTML（CodeMirror / ElInput type=textarea，monaco-editor 更好但避免引入）
Step 5: 选原推文展示图
  - 显示该推文所有图 list（来自 /posters/note-images/{note_id}）
  - 单选（每条 item 一张）
Step 6: 预览 + 生成
  - 嵌入 iframe 展示 /preview HTML
  - 点"渲染为 PNG" → 调用 /render → 展示下载链接
```

### 6.3 海报列表（PosterTask 列表）

每行：任务名 / 模板名（join）/ item 数量 / 状态 / 操作（查看 / 下载 / 删除）。
进入查看 = 进 wizard 第六步状态。

## 7. 测试

| 文件 | 案例数 |
|---|---|
| `test_poster_template_api.py` | 5 |
| `test_poster_template_parse.py` | 2（mock LLM vision） |
| `test_poster_task_api.py` | 6 |
| `test_poster_candidates.py` | 2 |
| `test_poster_render.py` | 3 |
| `frontend/PostersListView.spec.ts` | 3 |
| `frontend/PosterWizardView.spec.ts` | 4 |
| `frontend/PosterTemplateSettings.spec.ts` | 3 |

## 8. 验收

- 后端 360+ 测试全过；
- 前端 60+ 测试全过；
- build 通过；
- 实操：
  1. **配置中心 → 海报模板**：手动新建 HTML 模板 + **上传一张海报** → minimax vision 解析 → 编辑 → 保存；
  2. **海报制作 → 新建 → 选 1 条推文（里面 3 个活动）→ 选模板 → 填字段 → 选 1 张推文图 → 预览 HTML → 点"渲染为 PNG"**；
  3. **海报列表**：看产出 → 下载 → 与原图风格相近。

## 9. 风险

| 风险 | 缓解 |
|---|---|
| minimax 不支持 vision / OCR | `parse-from-image` 返回 503，前端跳手动 HTML 编辑 |
| playwright chromium 没装 | runtime 抛异常，自动 fallback opencli；再不行返 503 |
| HTML 模板外链 XSS | 服务端渲染时 weasyprint 内置禁用；Playwright 用 iframe sandbox |
| base64 image 阻塞大内存 | `<4MB` 内嵌；更大的改 URL 引用 `data/images/note-{id}/` |
