# 测试用例：认证与用户管理 (Auth & User Management)

## 测试环境
- **框架**: pytest 7.x + httpx (TestClient)
- **语言**: Python 3.11
- **Mock 策略**: Mock DB 用户查询，使用 FastAPI TestClient 测试真实路由
- **被测模块**: `backend/app/api/v1/auth.py`, `backend/app/core/security.py`

## Mock 依赖

```python
from fastapi.testclient import TestClient
from backend.app.main import app

@pytest.fixture
def client():
    return TestClient(app)

@pytest.fixture
def test_user():
    return {
        "username": "admin",
        "password": "Admin@123",
        "role": "admin"
    }

@pytest.fixture
def test_editor():
    return {
        "username": "editor",
        "password": "Editor@123",
        "role": "editor"
    }
```

---

## TC-AUTH-001: 登录 - 正确凭据

**优先级**: P0
**类型**: 集成测试
**被测接口**: `POST /api/v1/auth/login`

### Given
- 用户名 "admin"，密码 "Admin@123"
- 数据库中密码哈希匹配

### When
发送 `POST /api/v1/auth/login`

### Then
- HTTP 200
- 返回 access_token（JWT 格式）
- token_type = "bearer"
- expires_in = 86400

```python
def test_login_with_correct_credentials(client, mock_db, test_user):
    """正确凭据应返回 JWT token"""
    mock_db.query.return_value.filter.return_value.first.return_value = {
        "id": 1, "username": "admin",
        "password_hash": bcrypt.hashpw("Admin@123", bcrypt.gensalt()),
        "role": "admin"
    }

    response = client.post("/api/v1/auth/login", json={
        "username": "admin", "password": "Admin@123"
    })

    assert response.status_code == 200
    data = response.json()
    assert data["code"] == 200
    assert "access_token" in data["data"]
    assert data["data"]["token_type"] == "bearer"
    assert data["data"]["expires_in"] == 86400
```

---

## TC-AUTH-002: 登录 - 错误密码

**优先级**: P0
**类型**: 集成测试
**被测接口**: `POST /api/v1/auth/login`

### Given
- 用户名 "admin"，密码错误 "WrongPass"

### When
发送 `POST /api/v1/auth/login`

### Then
- HTTP 401
- code = 401
- message = "用户名或密码错误"
- 不返回 token

```python
def test_login_with_wrong_password(client, mock_db, test_user):
    """错误密码应返回 401"""
    mock_db.query.return_value.filter.return_value.first.return_value = {
        "id": 1, "username": "admin",
        "password_hash": bcrypt.hashpw("Admin@123", bcrypt.gensalt()),
        "role": "admin"
    }

    response = client.post("/api/v1/auth/login", json={
        "username": "admin", "password": "WrongPass"
    })

    assert response.status_code == 401
    data = response.json()
    assert data["code"] == 401
    assert "access_token" not in data.get("data", {})
```

---

## TC-AUTH-003: 登录 - 不存在的用户

**优先级**: P0
**类型**: 集成测试
**被测接口**: `POST /api/v1/auth/login`

### Given
- 用户名 "nonexistent"，数据库中不存在

### When
发送 `POST /api/v1/auth/login`

### Then
- HTTP 401
- 错误信息不应泄露用户是否存在（统一返回"用户名或密码错误"）

```python
def test_login_nonexistent_user(client, mock_db):
    """不存在的用户返回 401，不泄露用户存在性"""
    mock_db.query.return_value.filter.return_value.first.return_value = None

    response = client.post("/api/v1/auth/login", json={
        "username": "nonexistent", "password": "anything"
    })

    assert response.status_code == 401
    assert "用户名或密码错误" in response.json()["message"]
```

---

## TC-AUTH-004: 访问受保护资源 - 无 Token

**优先级**: P0
**类型**: 集成测试
**被测接口**: `GET /api/v1/activities`

### Given
- 未提供 Authorization header

### When
发送 `GET /api/v1/activities`

### Then
- HTTP 401
- message = "未提供认证凭据"

```python
def test_access_protected_route_without_token(client):
    """无 Token 访问受保护接口应返回 401"""
    response = client.get("/api/v1/activities")

    assert response.status_code == 401
```

---

## TC-AUTH-005: 访问受保护资源 - 无效 Token

**优先级**: P0
**类型**: 集成测试
**被测接口**: `GET /api/v1/activities`

### Given
- Authorization header 包含伪造的 JWT

### When
发送 `GET /api/v1/activities`，附带无效 Token

### Then
- HTTP 401
- message = "认证凭据无效或已过期"

```python
def test_access_with_invalid_token(client):
    """无效 Token 应返回 401"""
    response = client.get("/api/v1/activities", headers={
        "Authorization": "Bearer invalid.token.here"
    })

    assert response.status_code == 401
```

---

## TC-AUTH-006: 访问受保护资源 - 过期 Token

**优先级**: P1
**类型**: 集成测试
**被测接口**: `GET /api/v1/activities`

### Given
- JWT Token 已过期（exp 在过去）

### When
发送请求

### Then
- HTTP 401
- message 提示 Token 已过期

```python
def test_access_with_expired_token(client):
    """过期 Token 应返回 401"""
    expired_token = create_access_token(
        data={"sub": "admin", "role": "admin"},
        expires_delta=timedelta(seconds=-1)  # 已过期
    )

    response = client.get("/api/v1/activities", headers={
        "Authorization": f"Bearer {expired_token}"
    })

    assert response.status_code == 401
```

---

## TC-AUTH-007: 角色权限 - editor 不能访问管理接口

**优先级**: P0
**类型**: 集成测试
**被测接口**: `DELETE /api/v1/settings/cities/1`

### Given
- editor 角色的有效 Token
- 请求删除城市配置

### When
发送 `DELETE /api/v1/settings/cities/1`

### Then
- HTTP 403
- message = "权限不足"

```python
def test_editor_cannot_access_admin_routes(client, test_editor):
    """editor 角色不能访问管理员专属接口"""
    token = create_access_token({"sub": "editor", "role": "editor"})

    response = client.delete("/api/v1/settings/cities/1", headers={
        "Authorization": f"Bearer {token}"
    })

    assert response.status_code == 403
```

---

## TC-AUTH-008: 角色权限 - admin 可以访问所有接口

**优先级**: P0
**类型**: 集成测试
**被测接口**: 所有接口

### Given
- admin 角色的有效 Token

### When
发送各种请求

### Then
- 所有接口返回 200（非 403）

```python
@pytest.mark.parametrize("method,url", [
    ("GET", "/api/v1/dashboard/summary"),
    ("GET", "/api/v1/activities"),
    ("POST", "/api/v1/settings/cities"),
    ("DELETE", "/api/v1/settings/keywords/1"),
    ("GET", "/api/v1/tasks"),
    ("POST", "/api/v1/tasks/crawl"),
])
def test_admin_can_access_all_routes(client, method, url):
    """admin 应能访问所有接口"""
    token = create_access_token({"sub": "admin", "role": "admin"})

    response = client.request(method, url, headers={
        "Authorization": f"Bearer {token}"
    })

    assert response.status_code != 403
```

---

## TC-AUTH-009: 密码强度验证

**优先级**: P1
**类型**: 单元测试
**被测函数**: `validate_password_strength(password)`

### Given
各种强度的密码

### When
调用 `validate_password_strength`

### Then
弱密码被拒绝

```python
@pytest.mark.parametrize("password,is_valid", [
    ("123456", False),           # 太短且纯数字
    ("abcdef", False),           # 纯字母
    ("abc123", False),           # 无大写和特殊字符
    ("Abc123!@", True),          # 符合要求
    ("MyP@ssw0rd2025", True),    # 符合要求
])
def test_password_strength_validation(password, is_valid):
    """应验证密码强度"""
    result = validate_password_strength(password)
    assert result == is_valid
```

---

## TC-AUTH-010: Token 刷新机制（可选）

**优先级**: P2
**类型**: 集成测试
**被测接口**: `POST /api/v1/auth/refresh`

### Given
- 有效的 refresh_token

### When
发送 `POST /api/v1/auth/refresh`

### Then
- 返回新的 access_token
- 旧的 refresh_token 失效

```python
def test_token_refresh(client):
    """应能用 refresh_token 换取新 access_token"""
    # 先登录获取 refresh_token
    # 用 refresh_token 换取新 access_token
    # 验证新 token 可用，旧 refresh_token 已失效
    pass  # 当前版本可能不含 refresh 机制，标记为 P2
```

---

## 测试运行命令

```bash
pytest tests/test_auth.py -v
pytest tests/test_auth.py --cov=backend.app.api.v1.auth --cov=backend.app.core.security --cov-report=html
```
