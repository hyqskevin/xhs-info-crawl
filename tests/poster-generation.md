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

### 场景 3.2 浏览器实际渲染（端到端截图）

> 这一类需要在 **Playwright 浏览器**（headless chromium）跑 `frontend/e2e/poster-flow.spec.ts`：

- 前置：dev 服务（`make dev-api` + `make dev-web`）跑起来，登录态已取得。
- 步骤（脚本：`frontend/e2e/poster-flow.spec.ts`）：
  1. 访问 `/posters/new`；
  2. 选 3 个候选活动 → 选模板 → 填字段 → 上传/选图；
  3. 点"渲染为 PNG"按钮；
  4. 等接口响应；
  5. 截全屏 / 取 `<img class="poster-output">` src 与 HTML viewport；
  6. 断言：PNG 不为空；PNG 宽 ≈ 1242，高 ≈ 2208；HTML 中**包含全部 items 的 title 文本**；**包含至少一个 emoji**。
- 期望：脚本退出码 0，输出 `data/posters/{task_id}.png` 与 chromium 截图对比 baseline。

## 4. 样式接口单元测试

### 场景 4.1 HTML 拼装与 CSS 注入

- 单元：`backend/tests/test_poster_render.py::test_html_assembly_injects_items_and_styles`
- 步骤：构造 `PosterTask(items=[...])` 与 `PosterTemplate(css_text='.x{background:red}')`；
  调 `assemble_html(task, template)`；
- 期望：返回字符串包含 `<style>.x{background:red}</style>`；items 元素按 items.length 渲染，每个 item 含 `time_range / location / fee`。

### 场景 4.2 渲染 PNG 字节

- 单元：`test_render_to_png_returns_png_bytes`
- 步骤：用 pytest 调 `render_poster(task)`（Playwright 已经在 conftest fixture 启动 chromium）；
- 期望：返回字节流首 8 字节 == PNG magic `89 50 4e 47 0d 0a 1a 0a`；
- 期望：尺寸实测 ≈ template viewport。

### 场景 4.3 opencli fallback

- 单元：`test_render_falls_back_to_opencli_when_playwright_unavailable`
- 步骤：monkeypatch `playwright.sync_api.sync_playwright` 抛 ImportError，monkeypatch `render_with_opencli` 返回写文件路径；
- 期望：`render_poster` 仍能写文件并返回 PNG 路径；output_path 落到 data/posters/{id}.png。

### 场景 4.4 文件清理

- 单元：`test_render_dedupes_old_png_for_same_task`
- 步骤：连续两次 render 同一 task；
- 期望：第一次 PNG 删除，第二次 PNG 写入新路径；data/posters 下不会留旧文件。

## 5. 视觉回归（截图对比）

> `frontend/e2e/poster-visual.spec.ts`：

- 步骤：对比今日截海报图与 baseline：`tests/baselines/poster-baseline.png`；
- 通过：图像 diff ≤ 0.5% 像素差，CI 标记绿色；
- 失败：拷贝 diff 截图到 `tests/baselines/_diffs/poster-{ts}.png` 供人审。

## 6. 验证脚本（可重放）

`tests/scripts/test_poster_generation.sh` 覆盖场景：
- 1.1 / 1.2 / 1.3 / 1.4 / 2.1 / 2.3 / 2.4 / 2.5 / 2.6
- 4.1 / 4.2 / 4.3 / 4.4 单元端 pytest 跑。

前端 Playwright 流程：单独跑：
```bash
cd frontend && npm run test:e2e -- poster-flow.spec.ts poster-visual.spec.ts
```

依赖：
- 后端 dev 服务运行（默认 http://127.0.0.1:8000）；
- `MINIMAX_API_KEY` 已 export（若要测 AI）；
- 前端 dev 服务（http://127.0.0.1:5173）；
- 系统已 `playwright install chromium`。

跑法：
```bash
make dev-api &
bash tests/scripts/test_poster_generation.sh
npm run test:e2e -- poster-flow.spec.ts poster-visual.spec.ts
```
