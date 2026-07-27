# 测试用例：海报 API（`/api/v1/posters`）

维度：接口（后端）。

## 目标

海报模板 CRUD + 图生图解析接口，作用是从已抓取素材生成活动宣传海报：

- `GET /api/v1/posters/templates` —— 模板列表
- `POST /api/v1/posters/templates` —— 新建
- `PATCH /api/v1/posters/templates/{id}` —— 编辑（保留 `parsed_meta`）
- `DELETE /api/v1/posters/templates/{id}` —— 删除
- `POST /api/v1/posters/parse-from-image` —— 上传图片用视觉模型解析（MiniMax-M3 视觉）→ 返回字段后填入模板

## 可执行测试锚点

- API：[backend/tests/test_poster_template_api.py](file:///Users/kevin_w/Documents/github/xhs-info-crawl/backend/tests/test_poster_template_api.py)
- 模型：[backend/tests/test_poster_models.py](file:///Users/kevin_w/Documents/github/xhs-info-crawl/backend/tests/test_poster_models.py)
- 海报生成验收：[tests/poster-generation.md](file:///Users/kevin_w/Documents/github/xhs-info-crawl/tests/poster-generation.md) + [scripts/test_poster_generation.sh](file:///Users/kevin_w/Documents/github/xhs-info-crawl/tests/scripts/test_poster_generation.sh)

## 用例编号

| ID | 场景 | 期望 | 锚点 |
|---|---|---|---|
| TC-POSTER-001 | 未登录 | 401 | `test_auth_api.py` |
| TC-POSTER-002 | 列表为空 | `items=[]` | `test_poster_template_api.py::test_list_poster_templates_empty` |
| TC-POSTER-003 | 新建模板合法 | 201 + 返回 id | `test_create_poster_template` |
| TC-POSTER-004 | 新建重复 name | 409 | `test_create_poster_template_duplicate_name_409` |
| TC-POSTER-005 | 编辑保留 `parsed_meta` | 字段不被清空 | `test_update_poster_template_keeps_parsed_meta` |
| TC-POSTER-006 | 删除模板 | 204 + 列表移除 | `test_delete_poster_template` |
| TC-POSTER-007 | 删除被引用 | 409 | model 层 `task_items` relationship + API 检查 |
| TC-POSTER-008 | parse-from-image 未设 MINIMAX_API_KEY | 503 | `test_parse_from_image_without_api_key_returns_503` |
| TC-POSTER-009 | parse-from-image 注入 mock 视觉模型 | 200 + 返回结构化字段 | `test_parse_from_image_with_mocked_vision` |
| TC-POSTER-010 | parse-from-image 文件过大 | 422 | `test_parse_from_image_too_large_rejected` |
| TC-POSTER-011 | parse-from-image 非图像 MIME | 422 | `test_parse_from_image_non_image_content_type_rejected` |
| TC-POSTER-012 | 模板 `parsed_meta` 接受 dict | 序列化成功 | `test_poster_models.py::test_template_parsed_meta_accepts_dict` |
| TC-POSTER-013 | 海报生成脚本 | 验收 [scripts/test_poster_generation.sh](file:///Users/kevin_w/Documents/github/xhs-info-crawl/tests/scripts/test_poster_generation.sh) 可执行 | [tests/poster-generation.md](file:///Users/kevin_w/Documents/github/xhs-info-crawl/tests/poster-generation.md) |

## 验收

- `uv run --project backend pytest backend/tests/test_poster_template_api.py backend/tests/test_poster_models.py -q` 全绿。
- 不与 [tests/poster-generation.md](file:///Users/kevin_w/Documents/github/xhs-info-crawl/tests/poster-generation.md) 重复（后者是端到端生成验收）。
