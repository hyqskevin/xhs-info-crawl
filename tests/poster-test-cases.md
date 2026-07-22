# 海报生成测试案例（Case-By-Case）

> 每个 case 是**自包含的最小独立测试场景**，可以单独重放、debug、skip。
> 关联: docs/superpowers/specs/2026-07-21-poster-generation-design.md
> 后端: backend/tests/test_poster_*.py；E2E: tests/scripts/test_poster_generation.sh。

---

# §0 总览

| case 编号 | 类别 | 前置 | 落地 |
|---|---|---|---|
| TC-PT-001~005 | 模型 | db_session | test_poster_models.py |
| TC-PTT-001~009 | 模板 CRUD/AI | client | test_poster_template_api.py |
| TC-PTK-001~007 | 任务流程 | client | test_poster_task_api.py |
| TC-PSH-001~011 | API E2E (bash) | dev_api | test_poster_generation.sh |

**总计**：32 case。

---

# §1 模型层（PT = PosterTemplate / PK = PosterTask）

## TC-PT-001 模板 name UNIQUE 约束

- 目的：PosterTemplate.name DB 层 UNIQUE 防止重名。
- 前置：db_session。
- 步骤：
  1. insert PosterTemplate name='橙橙周末合集'；
  2. 再 insert 同名 → 期望抛 IntegrityError，事务回滚。
- 期望：第二次 commit 失败；DB 中只有 1 条 '橙橙周末合集'。
- 落地：`tests/test_poster_models.py::test_template_unique_name`

## TC-PT-002 模板 parsed_meta 接受 dict

- 目的：parsed_meta 字段允许任意 JSON dict，含 fonts/colors/emoji。
- 前置：db_session。
- 步骤：
  1. 创建模板，parsed_meta={'fonts':['PingFang'],'colors':{'primary':'#F26B2C'},'emoji':['🕐']};
  2. commit + refresh；
  3. assert t.parsed_meta == 入参。
- 期望：dict 完整保留（无 ORM 变更）。
- 落地：`tests/test_poster_models.py::test_template_parsed_meta_accepts_dict`

## TC-PT-003 任务 status 默认 draft

- 目的：新 PosterTask 默认 status='draft', output_format='png'。
- 前置：db_session + 1 个 PosterTemplate。
- 步骤：建任务不传 status / output_format。
- 期望：t.status == 'draft'，t.output_format == 'png'。
- 落地：`tests/test_poster_models.py::test_task_status_default_draft`

## TC-PT-004 任务 items 是 JSON 列表

- 目的：items 是 list[dict]，含 type='note' / 'activity'。
- 前置：db_session + 1 模板。
- 步骤：
  ```python
  items = [
      {"type":"note", "id":1, "title":"示例推文", "fields":{...}, "image_url":"..."},
      {"type":"activity", "id":5, "note_id":1, ...},
  ]
  PosterTask(items=items)
  ```
- 期望：保存后 t.items 长度 2；t.items[1]["note_id"] == 1。
- 落地：`tests/test_poster_models.py::test_task_items_json_list`

## TC-PT-005 模板被引用时删除 RESTRICT

- 目的：FK ON DELETE RESTRICT 阻止删除还有任务的模板。
- 前置：db_session + 1 模板 + 1 任务。
- 步骤：db.delete(template) + commit。
- 期望：抛 IntegrityError，事务回滚；template / task 都还在。
- 落地：`tests/test_poster_models.py::test_task_remove_template_restricted`

---

# §2 模板 API（PTT = Poster-Template API）

## TC-PTT-001 列出空模板列表

- 目的：GET 返回 data.items=[]。
- 前置：admin auth；新 DB。
- 步骤：GET /api/v1/settings/poster-templates。
- 期望：HTTP 200；data.items == []。
- 落地：`tests/test_poster_template_api.py::test_list_poster_templates_empty`

## TC-PTT-002 手动创建模板

- 目的：POST 入参 html_template/css_text 被原样保存；source='manual'。
- 前置：admin auth。
- 入参：
  ```json
  { "name":"橙橙周末合集", "description":"橙底白字...",
    "html_template":"<div class='poster'><h1>{{title}}</h1>{{items}}</div>",
    "css_text":".poster{background:#F26B2C;...}" }
  ```
- 期望：HTTP 200；data.source='manual'；data.html_template 以 `<div` 开头。
- 落地：`tests/test_poster_template_api.py::test_create_poster_template`

## TC-PTT-003 重名 POST 拒绝

- 目的：第二次同名 POST 返回 409。
- 前置：已存在 name='DUP'。
- 步骤：再 POST name='DUP'。
- 期望：HTTP 409。
- 落地：`tests/test_poster_template_api.py::test_create_poster_template_duplicate_name_409`

## TC-PTT-004 PUT 不修改 parsed_meta 时保留

- 目的：PUT 入参不含 parsed_meta 时，原值保留。
- 前置：模板 parsed_meta={'fonts':['PingFang']}。
- 步骤：PUT {name, html_template}（无 parsed_meta）。
- 期望：HTTP 200；fetched.parsed_meta == 原 dict。
- 落地：`tests/test_poster_template_api.py::test_update_poster_template_keeps_parsed_meta`

## TC-PTT-005 DELETE 模板返回 404 on GET

- 目的：DELETE 后 GET 单条返 404。
- 步骤：DELETE /settings/poster-templates/{id} → GET /{id}。
- 期望：DELETE 200；GET 404。
- 落地：`tests/test_poster_template_api.py::test_delete_poster_template`

## TC-PTT-006 parse-from-image 无 API key 时 503

- 目的：MINIMAX_API_KEY 空时返 503。
- 前置：admin auth；monkeypatch env 让 minimax_api_key=''。
- 步骤：上传 1 个合法 PNG。
- 期望：HTTP 503 + 提示设置 MINIMAX_API_KEY。
- 落地：`tests/test_poster_template_api.py::test_parse_from_image_without_api_key_returns_503`

## TC-PTT-007 parse-from-image mocked MiniMax 成功

- 目的：mock MiniMaxClient.vision_chat 后 200 + 草稿 HTML/parsed_meta。
- 前置：admin auth；monkeypatch minimax_api_key='fake'；monkeypatch MiniMaxClient.vision_chat 返 fake dict。
- 步骤：上传 sample.png。
- 期望：HTTP 200；data.html_template 以 `<div` 开头；data.parsed_meta.colors.primary=='#F26B2C'；data.name_suggestion=='橙橙风格'。
- 落地：`tests/test_poster_template_api.py::test_parse_from_image_with_mocked_vision`

## TC-PTT-008 parse-from-image 超大文件 413

- 目的：>6 MiB 文件拒绝。
- 步骤：上传 8 MiB。
- 期望：HTTP 413。
- 落地：`tests/test_poster_template_api.py::test_parse_from_image_too_large_rejected`

## TC-PTT-009 parse-from-image 非图片 content-type 415

- 目的：text/plain content-type 拒绝。
- 步骤：上传 a.txt。
- 期望：HTTP 415。
- 落地：`tests/test_poster_template_api.py::test_parse_from_image_non_image_content_type_rejected`

---

# §3 任务 API（PTK = Poster-Task API）

## TC-PTK-001 创建最小任务

- 目的：POST 含模板 ID 时建 draft 任务。
- 前置：admin auth + 1 个 PosterTemplate。
- 步骤：POST { name, template_id, items:[] }。
- 期望：HTTP 200；data.status='draft'；data.output_format='png'。
- 落地：`tests/test_poster_task_api.py::test_create_poster_task_minimal`

## TC-PTK-002 模板不存在时 422

- 目的：template_id=99999（不存在）拒。
- 步骤：POST { name, template_id:99999 }。
- 期望：HTTP 422。
- 落地：`tests/test_poster_task_api.py::test_create_poster_task_invalid_template`

## TC-PTK-003 更新 items JSON

- 目的：PUT items 后持久化。
- 前置：1 模板 + 1 任务（items=[]）。
- 步骤：PUT /poster-tasks/{id} { items:[note, activity] }。
- 期望：HTTP 200；data.items 长度 2；data.items[1]["note_id"]=1。
- 落地：`tests/test_poster_task_api.py::test_update_poster_task_items`

## TC-PTK-004 preview 拼接 HTML 含 emoji 与 items

- 目的：preview 把每条 item 渲染成 row-card。
- 前置：1 模板 html='{{title}} {{items}}' + 任务含 1 条 item。
- 步骤：GET /poster-tasks/{id}/preview。
- 期望：HTTP 200；data.html 含 '🕐' / '卷被子' / '宁波周末活动'。
- 落地：`tests/test_poster_task_api.py::test_preview_renders_items`

## TC-PTK-005 candidates 返回 notes

- 目的：candidates 端点列笔记（从前端 wizard 用）。
- 前置：admin auth；DB 写 3 条 Note（city='nb'）。
- 步骤：GET /poster-tasks/candidates?city_code=nb。
- 期望：HTTP 200；items ≥ 3；每个 item type='note'。
- 落地：`tests/test_poster_task_api.py::test_candidates_returns_notes`

## TC-PTK-006 删除任务

- 目的：DELETE 后 GET 404。
- 步骤：DELETE /poster-tasks/{id} → GET /{id}。
- 期望：DELETE 200；GET 404。
- 落地：`tests/test_poster_task_api.py::test_delete_poster_task`

## TC-PTK-007 render mocked opencli 写 PNG

- 目的：mock _playwright_available=False + mock subprocess.run 假装写 PNG。
- 前置：admin auth + 1 模板 + 1 任务（items 1 条）。
- 步骤：POST /poster-tasks/{id}/render。
- 期望：HTTP 200；data.url 含 /download；GET /download 返 image/png。
- 落地：`tests/test_poster_task_api.py::test_render_with_mocked_opencli`

---

# §4 bash API 回放（PSH = Poster Shell）

## TC-PSH-001 登录拿 token

- 步骤：POST /auth/login {username:admin, password:Admin@123}。
- 期望：data.access_token 非空。
- 落地：`tests/scripts/test_poster_generation.sh §0`

## TC-PSH-002 模板列表初始为空

- 步骤：GET /settings/poster-templates。
- 期望：HTTP 200。
- 落地：`tests/scripts/test_poster_generation.sh §1`

## TC-PSH-003 手动创建模板

- 步骤：POST /settings/poster-templates（name 含时间戳避免重名）。
- 期望：data.id > 0。
- 落地：`tests/scripts/test_poster_generation.sh §1`

## TC-PSH-004 重名 POST 拒绝

- 步骤：连续两次 POST 同 name。
- 期望：第二次 409 或 422。
- 落地：`tests/scripts/test_poster_generation.sh §1`

## TC-PSH-005 PUT 模板

- 步骤：PUT /settings/poster-templates/{id} { css_text: 新值 }。
- 期望：HTTP 200。
- 落地：`tests/scripts/test_poster_generation.sh §1`

## TC-PSH-006 DELETE 模板

- 步骤：DELETE /settings/poster-templates/{id}。
- 期望：HTTP 200。
- 落地：`tests/scripts/test_poster_generation.sh §1`

## TC-PSH-007 candidates 列表（≤50）

- 步骤：GET /poster-tasks/candidates?page_size=5。
- 期望：data.items 长度 0~50。
- 落地：`tests/scripts/test_poster_generation.sh §2`

## TC-PSH-008 创建任务（推文粒度）

- 步骤：POST /poster-tasks（先建临时模板，再带 items）。
- 期望：data.id 非空。
- 落地：`tests/scripts/test_poster_generation.sh §2`

## TC-PSH-009 更新任务 override_html

- 步骤：PUT /poster-tasks/{id} { override_html: 手改 HTML }。
- 期望：HTTP 200。
- 落地：`tests/scripts/test_poster_generation.sh §2`

## TC-PSH-010 preview HTML 含 items

- 步骤：GET /poster-tasks/{id}/preview。
- 期望：data.html 含 item 标题字段。
- 落地：`tests/scripts/test_poster_generation.sh §2`

## TC-PSH-011 推文图片列表端点

- 步骤：GET /posters/note-images/1（即使 note 1 无图，也返 200 + 空数组）。
- 期望：HTTP 200。
- 落地：`tests/scripts/test_poster_generation.sh §2`

---

# §5 测试矩阵

| 类别 | 数量 | 自动跑 (CI) | 手动 (dev) | 是否 mock |
|---|---|---|---|---|
| 模型单元 | 5 | ✅ | — | 真实 DB |
| 模板 API | 9 | ✅ | — | MiniMax mock |
| 任务 API | 7 | ✅ | — | subprocess mock |
| bash E2E | 11 | ✅（需 dev API） | — | 真实 HTTP |
| **真实 render** | 0 | ❌ | ✅（待补）| 真 opencli |
| 前端 View | 0 | — | 待补 | — |
| Playwright | 0 | — | 待补 | — |

---

# §6 case 编号→文件名 速查

| 编号前缀 | 文件 |
|---|---|
| TC-PT | backend/tests/test_poster_models.py |
| TC-PTT | backend/tests/test_poster_template_api.py |
| TC-PTK | backend/tests/test_poster_task_api.py |
| TC-PSH | tests/scripts/test_poster_generation.sh |

---

# §7 spec→case 矩阵

| spec 节 | TC 编号 |
|---|---|
| §2.1 poster_templates | TC-PT-001 / 002 / TC-PTT-001~005 |
| §2.2 poster_tasks | TC-PT-003 / 004 / TC-PTK-001 / 003 |
| §2.3 migration 0014 | TC-PT-005（外键 FK 测试） |
| §3.1 模板 CRUD | TC-PTT-001~005 |
| §3.1 模板 parse-from-image | TC-PTT-006~009 |
| §3.2 任务 CRUD | TC-PTK-001 / 002 / 003 / 006 |
| §3.2 任务 preview | TC-PTK-004 |
| §3.2 任务 render | TC-PTK-007 |
| §3.2 任务 candidates | TC-PTK-005 / TC-PSH-007 |
| §3.3 辅助端点 note-images | TC-PSH-011 |
| §4 AI minimax vision | TC-PTT-006 / 007 |
