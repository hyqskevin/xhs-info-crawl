# 海报生成系统端到端测试

> 这份文档是 E2E 测试案例描述，对应手工或者脚本化测试。
> 每个场景含：前置条件、操作步骤、期望结果。可以跑 `tests/scripts/test_poster_generation.sh` 一键回放。
>
> 关联 spec： docs/superpowers/specs/2026-07-21-poster-generation-design.md

## 1. 模板 CRUD

### 场景 1.1 列出默认空列表

- 前置：以 admin 登录。
- 步骤：GET /api/v1/settings/poster-templates。
- 期望：200，data.items 长度 ≥ 0（首次为空）。

### 场景 1.2 手动创建模板

- 前置：以 admin 登录。
- 步骤：POST /api/v1/settings/poster-templates { name, description, html_template, css_text }。
- 期望：200，data 返回新模板；模板 html_template 字段完整保存。

### 场景 1.3 重名拒绝

- 步骤：连续两次 POST 同名模板。
- 期望：第二次返回 422 或 409。

### 场景 1.4 编辑 / 删除模板

- 步骤：PUT /api/v1/settings/poster-templates/{id} 修改 css_text；DELETE 删除。
- 期望：编辑保存；删除后 GET 单条返回 404；列表不再包含。

### 场景 1.5 上传海报走 minimax vision

- 步骤：POST /api/v1/settings/poster-templates/parse-from-image multipart/form-data image=@sample.jpg。
- 期望：200，data.html_template 为含中文 + emoji 的可用 HTML 草稿；data.parsed_meta 含 fonts / colors / emoji / layout_blocks。
- 若 minimax 未配 MINIMAX_API_KEY：返回 503 + 提示"AI 识别不可用，请手动编写 HTML"。

## 2. 海报任务流程

### 场景 2.1 创建 draft 任务（推文粒度）

- 前置：有一现成 template_id 与至少 1 条 note。
- 步骤：POST /api/v1/poster-tasks { template_id, items: [{type:note, id, fields:{time_range, location, fee, content}, image_url}] }。
- 期望：200，status='draft'，items 保存为 JSON。

### 场景 2.2 创建 draft 任务（活动粒度）

- 步骤：POST 同上，但 items 的 type='activity' 且额外含 note_id。
- 期望：200，后端识别 type；保存 note_id 用于取图。

### 场景 2.3 更新任务

- 步骤：PUT /api/v1/poster-tasks/{id} 修改 override_html 或 items。
- 期望：200，详情 GET 后字段一致。

### 场景 2.4 候选对象查询

- 步骤：GET /api/v1/poster-tasks/candidates?city_code=shanghai&q=展览 → 列表项含 note_id/title/image_count。
- 期望：200，items.length ≤ 50；每个 note 项含 image_count > 0 时附 image_urls[]（来自 /data/images/note-{id}）。

### 场景 2.5 推文图片列表

- 步骤：GET /api/v1/posters/note-images/{note_id}。
- 期望：200，image_urls 是按 /data/images/note-{id}/{index}.jpg 的有序 URL 数组。

### 场景 2.6 预览 HTML

- 步骤：GET /api/v1/poster-tasks/{id}/preview。
- 期望：200，data.html 是拼装好每个 item 一行的完整 HTML（viewport 1242x2208）；data.items_count 等于 item 数量。

### 场景 2.7 渲染为 PNG

- 前置：playwright 已 playwright install chromium（或 opencli 兜底）。
- 步骤：POST /api/v1/poster-tasks/{id}/render。
- 期望：200，返回 png path 在 output_path / data.url=/static/posters/{id}.png；status 变为 'rendered'。
- 若渲染失败：status='failed'，data.error 含原因。

### 场景 2.8 下载产物

- 步骤：GET /api/v1/poster-tasks/{id}/download。
- 期望：返回 image/png 二进制；Content-Disposition 含附件文件名。

### 场景 2.9 删除任务

- 步骤：DELETE。
- 期望：200，data.deleted_id；产物 PNG 文件同时被清理。

## 3. 浏览器端流程演练

### 场景 3.1 完整 wizard

1. 配置中心 → 海报模板 → 上传某张海报 → 看到 minimax 解析的 HTML → 命名 → 保存；
2. 海报制作 → 新建 → 选"推文为单位" / "活动为单位"；
3. 选 3 个候选（推文粒度时 3 条推文，活动粒度时 3 个活动）；
4. 选模板；
5. 填字段（每条一行 time_range / location / fee / content）；
6. 选每条 item 一张原推文图（来自 /posters/note-images）；
7. 手动编辑 HTML（override_html）；
8. 预览：iframe 加载 /preview 内容；
9. 点"渲染为 PNG"：后端截图后看到缩略图、下载按钮；
10. 进海报列表：看到刚才的任务，状态为 rendered，可下载。

## 4. 验证脚本（可重放）

`tests/scripts/test_poster_generation.sh` 覆盖场景：
- 1.1 / 1.2 / 1.3 / 1.4 / 2.1 / 2.3 / 2.4 / 2.5 / 2.6

依赖：
- 后端 dev 服务运行（默认 http://127.0.0.1:8000）；
- `ADMIN_TOKEN` 已在 export（脚本会先用 admin 登录取得）；
- `IMAGE_PATH` 若要测 AI：路径指 sample.jpg。

跑法：
```bash
make dev-api &
bash tests/scripts/test_poster_generation.sh
```
