# 测试用例：认证 API（`/api/v1/auth`）

维度：接口 + 鉴权（后端）。

## 目标

账号登录、Token 颁发、过期、Token 注入的关键契约：

- `POST /api/v1/auth/login` —— `username + password` 颁发 access_token
- `POST /api/v1/auth/logout` —— 客户端丢弃 token（服务端无状态）
- 任何业务路由必须要求 Bearer Token，否则 401
- Token 过期 / 篡改 → 401 + 客户端跳转 `/login`
- 测试环境独立 JWT 密钥：≥32 字节，禁止使用本地 .env 真实密钥

## 可执行测试锚点

- 主流程：[backend/tests/test_auth_api.py](file:///Users/kevin_w/Documents/github/xhs-info-crawl/backend/tests/test_auth_api.py)
- 测试环境密钥：[backend/tests/test_test_jwt_secret.py](file:///Users/kevin_w/Documents/github/xhs-info-crawl/backend/tests/test_test_jwt_secret.py)
- 前端 LoginView：[frontend/src/views/LoginView.spec.ts](file:///Users/kevin_w/Documents/github/xhs-info-crawl/frontend/src/views/LoginView.spec.ts)
- 路由守卫 + HTTP 鉴权头：[frontend/src/router/index.spec.ts](file:///Users/kevin_w/Documents/github/xhs-info-crawl/frontend/src/router/index.spec.ts)、[frontend/src/api/http.spec.ts](file:///Users/kevin_w/Documents/github/xhs-info-crawl/frontend/src/api/http.spec.ts)
- 端到端：Playwright `frontend/e2e/documented-flows.spec.ts` TC-UI-007

## 用例编号

| ID | 场景 | 期望 | 锚点 |
|---|---|---|---|
| TC-AUTH-001 | 正确账密 | 200 + access_token + expires_in | `test_auth_api.py::test_login_success` |
| TC-AUTH-002 | 错误密码 | 401 + 不颁发 | `test_auth_api.py::test_login_wrong_password` |
| TC-AUTH-003 | 用户名不存在 | 401 | `test_login_unknown_user` |
| TC-AUTH-004 | 空字段 | 422 | `test_login_validation` |
| TC-AUTH-005 | 请求带 Bearer | 200 | 各业务 case 已隐含 |
| TC-AUTH-006 | 缺失 Bearer | 401 | 各业务 case 已隐含 |
| TC-AUTH-007 | Bearer 篡改 | 401 | `test_auth_api.py::test_tampered_token_rejected` |
| TC-AUTH-008 | Bearer 过期（手动构造） | 401 | `test_expired_token_rejected` |
| TC-AUTH-009 | admin 调管理 API | 200 | `test_admin_can_call_admin_endpoint` |
| TC-AUTH-010 | editor 调管理 API（仅 admin） | 403 | `test_role_enforced` |
| TC-AUTH-011 | 测试环境 JWT_SECRET ≥ 32 字节 | 通过 | `test_test_jwt_secret.py::test_pytest_uses_jwt_secret_of_at_least_32_bytes` |
| TC-AUTH-012 | 创建 access_token 无 `InsecureKeyLengthWarning` | 警告被过滤 | `test_access_token_creation_has_no_short_key_warning` |
| TC-AUTH-013 | 前端路由未登录守卫 | 跳 `/login` | `router/index.spec.ts::redirects unauthenticated` |
| TC-AUTH-014 | 前端 HTTP 客户端注入 Authorization | 头存在 | `api/http.spec.ts::adds Authorization header` |
| TC-AUTH-015 | 前端登录后保存 token 并跳 `/dashboard` | 通过 | `LoginView.spec.ts::submits credentials and routes` |

## 验收

- `uv run --project backend pytest backend/tests/test_auth_api.py backend/tests/test_test_jwt_secret.py -q` 全绿。
- 前端 `npm --prefix frontend run test -- --run` 全绿。
- 不与 [tests/test-auth.md](file:///Users/kevin_w/Documents/github/xhs-info-crawl/tests/test-auth.md)、[tests/test-test-jwt-secret.md](file:///Users/kevin_w/Documents/github/xhs-info-crawl/tests/test-test-jwt-secret.md) 重复（前者是模块验收，后者是测试环境密钥专项）。
