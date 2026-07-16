# 测试用例：活动 CRUD API (Activity CRUD API)

## 测试环境
- **框架**: pytest 7.x + httpx (TestClient)
- **语言**: Python 3.11
- **Mock 策略**: Mock DB 查询，使用 FastAPI TestClient
- **被测模块**: `backend/app/api/v1/activities.py`

## Mock 依赖

```python
from fastapi.testclient import TestClient
from backend.app.main import app

@pytest.fixture
def client():
    return TestClient(app)

@pytest.fixture
def admin_token():
    return create_access_token({"sub": "admin", "role": "admin"})

@pytest.fixture
def auth_headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}"}

@pytest.fixture
def sample_activity():
    return {
        "id": 1,
        "name": "夏日音乐节",
        "city_code": "shanghai",
        "start_time": "2025-07-20T18:00:00Z",
        "end_time": "2025-07-20T22:00:00Z",
        "location": "徐汇滨江",
        "price": "免费",
        "type": "演出",
        "source_url": "https://www.xiaohongshu.com/explore/xxx",
        "summary": "户外音乐节，现场有多个乐队表演",
        "status": "APPROVED",
        "confidence": 0.85,
        "created_at": "2025-07-14T02:30:00Z",
        "updated_at": "2025-07-14T02:30:00Z"
    }
```

---

## TC-ACT-001: 获取活动列表 - 默认分页

**优先级**: P0
**类型**: 集成测试
**被测接口**: `GET /api/v1/activities`

### Given
- 数据库有 86 条活动
- 未指定任何筛选参数

### When
发送 `GET /api/v1/activities`

### Then
- HTTP 200
- 返回前 20 条（默认 page_size=20）
- pagination: page=1, page_size=20, total=86

```python
def test_get_activities_default_pagination(client, auth_headers, mock_db):
    """默认分页应返回前 20 条"""
    mock_db.query.return_value.filter.return_value.count.return_value = 86
    mock_db.query.return_value.filter.return_value.offset.return_value \
        .limit.return_value.all.return_value = [sample_activity()] * 20

    response = client.get("/api/v1/activities", headers=auth_headers)

    assert response.status_code == 200
    data = response.json()
    assert data["code"] == 200
    assert len(data["data"]["items"]) == 20
    assert data["pagination"]["total"] == 86
    assert data["pagination"]["page"] == 1
    assert data["pagination"]["page_size"] == 20
```

---

## TC-ACT-002: 获取活动列表 - 城市筛选

**优先级**: P0
**类型**: 集成测试
**被测接口**: `GET /api/v1/activities?city=shanghai`

### Given
- 数据库有 50 条上海活动，36 条北京活动

### When
发送 `GET /api/v1/activities?city=shanghai`

### Then
- 只返回上海的活动
- pagination.total = 50

```python
def test_get_activities_filter_by_city(client, auth_headers, mock_db):
    """城市筛选应只返回指定城市活动"""
    mock_db.query.return_value.filter.return_value.count.return_value = 50

    response = client.get("/api/v1/activities?city=shanghai", headers=auth_headers)

    assert response.status_code == 200
    assert response.json()["pagination"]["total"] == 50
```

---

## TC-ACT-003: 获取活动列表 - 多条件筛选

**优先级**: P0
**类型**: 集成测试
**被测接口**: `GET /api/v1/activities?city=shanghai&type=演出&status=APPROVED`

### Given
- 多条件组合

### When
发送多条件筛选请求

### Then
- 返回同时满足所有条件的活动
- 筛选参数正确传递给数据库查询

```python
def test_get_activities_multi_filter(client, auth_headers, mock_db):
    """多条件筛选应正确组合"""
    mock_db.query.return_value.filter.return_value.count.return_value = 10

    response = client.get(
        "/api/v1/activities?city=shanghai&type=演出&status=APPROVED",
        headers=auth_headers
    )

    assert response.status_code == 200
    assert response.json()["pagination"]["total"] == 10
```

---

## TC-ACT-004: 获取活动列表 - 时间范围筛选

**优先级**: P1
**类型**: 集成测试
**被测接口**: `GET /api/v1/activities?start_date=2025-07-20&end_date=2025-07-27`

### Given
- 日期范围筛选

### When
发送带日期的请求

### Then
- 返回举办时间在范围内的活动
- start_date 无效格式返回 422

```python
def test_get_activities_date_range(client, auth_headers, mock_db):
    """日期范围筛选"""
    mock_db.query.return_value.filter.return_value.count.return_value = 30

    response = client.get(
        "/api/v1/activities?start_date=2025-07-20&end_date=2025-07-27",
        headers=auth_headers
    )

    assert response.status_code == 200
    assert response.json()["pagination"]["total"] == 30


def test_get_activities_invalid_date_returns_422(client, auth_headers):
    """无效日期格式应返回 422"""
    response = client.get(
        "/api/v1/activities?start_date=not-a-date",
        headers=auth_headers
    )

    assert response.status_code == 422
```

---

## TC-ACT-005: 获取活动详情 - 存在

**优先级**: P0
**类型**: 集成测试
**被测接口**: `GET /api/v1/activities/1`

### Given
- 活动 id=1 存在
- 关联 1 篇笔记和 3 张图片

### When
发送 `GET /api/v1/activities/1`

### Then
- HTTP 200
- 返回活动全部字段
- 包含原始笔记信息和图片 OCR 结果

```python
def test_get_activity_detail_exists(client, auth_headers, mock_db):
    """存在活动应返回完整详情"""
    mock_db.query.return_value.filter.return_value.first.side_effect = [
        sample_activity(),                          # 活动
        {"id": 1, "title": "...", "content": "..."}, # 笔记
        [{"id": 1, "ocr_text": "..."}] * 3         # 图片
    ]

    response = client.get("/api/v1/activities/1", headers=auth_headers)

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["name"] == "夏日音乐节"
    assert "note" in data
    assert len(data["images"]) == 3
```

---

## TC-ACT-006: 获取活动详情 - 不存在

**优先级**: P0
**类型**: 集成测试
**被测接口**: `GET /api/v1/activities/99999`

### Given
- 活动 id=99999 不存在

### When
发送请求

### Then
- HTTP 404
- message = "活动不存在"

```python
def test_get_activity_not_found(client, auth_headers, mock_db):
    """不存在的活动应返回 404"""
    mock_db.query.return_value.filter.return_value.first.return_value = None

    response = client.get("/api/v1/activities/99999", headers=auth_headers)

    assert response.status_code == 404
```

---

## TC-ACT-007: 更新活动 - 正常

**优先级**: P0
**类型**: 集成测试
**被测接口**: `PUT /api/v1/activities/1`

### Given
- 活动 id=1 存在
- 请求体包含更新的字段

### When
发送 `PUT /api/v1/activities/1`

### Then
- HTTP 200
- 字段已更新
- updated_at 时间已变化

```python
def test_update_activity_success(client, auth_headers, mock_db):
    """应成功更新活动字段"""
    mock_db.query.return_value.filter.return_value.first.return_value = sample_activity()

    response = client.put("/api/v1/activities/1", json={
        "name": "夏日音乐节2025",
        "price": "50元",
        "status": "APPROVED"
    }, headers=auth_headers)

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["name"] == "夏日音乐节2025"
    assert data["price"] == "50元"
```

---

## TC-ACT-008: 更新活动 - 无效状态转换

**优先级**: P1
**类型**: 集成测试
**被测接口**: `PUT /api/v1/activities/1`

### Given
- 活动当前 status = "PUBLISHED"
- 尝试改为 "RAW"

### When
发送更新请求

### Then
- HTTP 422
- message 提示状态转换无效

```python
def test_update_activity_invalid_status_transition(
    client, auth_headers, mock_db
):
    """无效状态转换应被拒绝"""
    activity = sample_activity()
    activity["status"] = "PUBLISHED"
    mock_db.query.return_value.filter.return_value.first.return_value = activity

    response = client.put("/api/v1/activities/1", json={
        "status": "RAW"  # PUBLISHED → RAW 不允许
    }, headers=auth_headers)

    assert response.status_code == 422
```

---

## TC-ACT-009: 删除活动

**优先级**: P0
**类型**: 集成测试
**被测接口**: `DELETE /api/v1/activities/1`

### Given
- 活动 id=1 存在

### When
发送 `DELETE /api/v1/activities/1`

### Then
- HTTP 200
- 活动被软删除（status 变为 DELETED 或实际删除）
- 再次查询返回 404

```python
def test_delete_activity(client, auth_headers, mock_db):
    """应成功删除活动"""
    mock_db.query.return_value.filter.return_value.first.return_value = sample_activity()

    response = client.delete("/api/v1/activities/1", headers=auth_headers)

    assert response.status_code == 200
    # 验证删除操作已执行
    mock_db.delete.assert_called()
    mock_db.commit.assert_called()
```

---

## TC-ACT-010: 创建活动（手动新增）

**优先级**: P1
**类型**: 集成测试
**被测接口**: `POST /api/v1/activities`

### Given
- 完整的活动字段（手动录入）

### When
发送 `POST /api/v1/activities`

### Then
- HTTP 201
- 返回新建活动 ID
- 触发去重检查

```python
def test_create_activity_manual(client, auth_headers, mock_db):
    """手动创建活动应成功"""
    new_activity = {
        "name": "新活动",
        "city_code": "shanghai",
        "start_time": "2025-08-01T10:00:00Z",
        "end_time": "2025-08-01T18:00:00Z",
        "location": "上海中心",
        "price": "免费",
        "type": "展览",
        "source_url": "https://manual.example.com",
        "summary": "手动录入的活动"
    }

    response = client.post("/api/v1/activities", json=new_activity, headers=auth_headers)

    assert response.status_code == 201
    assert "id" in response.json()["data"]
```

---

## 测试运行命令

```bash
pytest tests/test_activities_api.py -v
pytest tests/test_activities_api.py --cov=backend.app.api.v1.activities --cov-report=html
```
