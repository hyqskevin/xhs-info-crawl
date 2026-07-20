# 测试环境 JWT 密钥隔离测试案例

## 目标

确认 pytest 使用独立的强度合格 JWT 密钥，不读取本地真实密钥，且不再产生 PyJWT 短密钥安全警告。

## 自动化案例

1. 运行 `cd backend && .venv/bin/pytest -q tests/test_test_jwt_secret.py`。
2. 预期 2 个测试通过。
3. 预期测试环境密钥按 UTF-8 计不少于 32 字节。
4. 预期 JWT 签发过程不产生 `InsecureKeyLengthWarning`。

## 全量回归

1. 运行 `cd backend && .venv/bin/pytest -q`。
2. 预期全部测试通过，输出不包含 `InsecureKeyLengthWarning`。
3. 检查 Git 变更，预期 `.env` 未被修改或纳入版本控制。
