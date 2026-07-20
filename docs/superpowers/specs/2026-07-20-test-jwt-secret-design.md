# 测试环境 JWT 密钥隔离设计

> 状态：已审核并实现。

## 1. 目标

为 pytest 提供独立且不少于 32 字节的 JWT HMAC 密钥，消除 PyJWT 的 `InsecureKeyLengthWarning`，同时保证测试不读取、不输出本地 `.env` 中的真实密钥，也不改变本地和生产环境的配置加载方式。

## 2. 已确认的根因

后端测试通常从 `backend/` 目录运行，而 `Settings` 的 `env_file=".env"` 按当前工作目录解析。测试进程没有读取项目根目录的 `.env`，因此 `Settings.secret_key` 回退到 `backend/app/core/config.py` 中的默认值 `change-me-in-local-env`。

该默认值只有 22 字节。测试调用 `create_access_token()` 时，PyJWT 按 HS256 的安全建议检测到密钥少于 32 字节并稳定产生 `InsecureKeyLengthWarning`。单个登录测试已复现为“1 passed, 1 warning”。

问题发生在测试配置注入时序，不是 JWT 编解码实现错误，也不应通过屏蔽 warning 处理。

## 3. 方案比较与决策

### 3.1 采用：pytest 导入应用前注入测试密钥

在 `backend/tests/conftest.py` 导入 `app.main` 之前，直接设置测试进程的 `SECRET_KEY`。密钥使用明确的测试占位值，长度不少于 32 字节，只存在于 pytest 子进程环境中。

选择该方案的原因：

- 与现有 Celery 测试 broker 的导入前隔离方式一致；
- 不依赖 pytest 的启动目录；
- 不读取开发者的本地 `.env`；
- 不修改应用默认值或运行时配置逻辑；
- 测试结束后不会写回任何配置文件。

### 3.2 不采用：新增测试专用 `.env`

测试专用文件仍涉及相对路径和启动目录，容易再次出现加载不到或误读其他 `.env` 的问题，也增加一份需要维护的配置文件。

### 3.3 不采用：加长应用默认密钥

修改 `Settings.secret_key` 默认值会影响未配置 `.env` 的本地运行行为，扩大本次测试隔离修复的范围，并可能让开发者误以为默认密钥适合真实环境。

### 3.4 不采用：过滤 warning

pytest `filterwarnings` 只能隐藏安全提示，不能消除短密钥这个真实原因，因此不采用。

## 4. 配置和数据流

1. pytest 加载 `backend/tests/conftest.py`；
2. `conftest.py` 设置固定的测试专用 `SECRET_KEY`；
3. 随后导入 `app.main`、`app.core.config` 和 `app.core.security`；
4. `get_settings()` 从测试进程环境读取该密钥；
5. 测试中的 JWT 签发和校验使用同一个测试密钥；
6. 正常启动 API 或 worker 时不会加载测试 `conftest.py`，继续读取各自运行环境的 `.env`。

测试中只允许断言密钥长度、来源隔离和 warning 是否出现，不打印密钥原文。

## 5. TDD 范围

先新增测试并确认在当前代码下失败，再修改测试基础设施：

1. 新增测试，断言 pytest 中加载的 `secret_key` 按 UTF-8 计不少于 32 字节；当前默认值为 22 字节，因此该测试先失败；
2. 新增 JWT 签发回归测试，将 `InsecureKeyLengthWarning` 提升为异常，证明测试签发不再产生该 warning；
3. 在 `conftest.py` 的应用导入之前注入测试专用 `SECRET_KEY`；
4. 运行新增测试确认变绿；
5. 运行后端全量测试，确认没有回归且输出不再包含 `InsecureKeyLengthWarning`。

测试不得读取根目录 `.env`，不得把真实密钥复制到测试代码、日志或文档。

## 6. 预计改动

- 修改 `backend/tests/conftest.py`：在应用导入前注入测试专用 JWT 密钥；
- 新增 `backend/tests/test_test_jwt_secret.py`：覆盖密钥长度和 warning 回归；
- 新增 `tests/test-test-jwt-secret.md`：记录自动化和验收步骤；
- 完成后更新 `docs/TODO.md`，将该事项移入“已完成”。

不修改 `backend/app/core/config.py`、`backend/app/core/security.py`、根目录 `.env` 或 `.env.example`。

## 7. 验收标准

- 新增测试先红后绿，并保留为回归测试；
- 测试环境 JWT 密钥按 UTF-8 计不少于 32 字节；
- `cd backend && pytest -q` 退出码为 0；
- pytest 输出不包含 `InsecureKeyLengthWarning`；
- 本地 API、Celery worker 和生产运行时的密钥读取逻辑无改动；
- Git 变更中不包含本地真实密钥或 `.env`。

## 8. 不在本次范围

- 不轮换开发或生产环境现有 JWT 密钥；
- 不调整 JWT 算法、有效期、载荷或权限逻辑；
- 不增加密钥管理服务；
- 不通过关闭或过滤安全 warning 达成验收。
