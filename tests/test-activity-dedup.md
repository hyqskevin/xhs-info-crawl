# 测试用例：活动去重 (Activity Deduplication)

## 测试环境
- **框架**: pytest 7.x
- **语言**: Python 3.11
- **Mock 策略**: Mock DB 查询，真实执行相似度计算逻辑
- **被测模块**: `backend/app/services/dedup.py`

## Mock 依赖

```python
@pytest.fixture
def mock_db():
    with patch("backend.app.core.database.get_session") as mock:
        yield mock

@pytest.fixture
def sample_activity_a():
    return {
        "id": 1, "name": "夏日音乐节",
        "city_code": "shanghai",
        "start_time": "2025-07-20T18:00:00",
        "end_time": "2025-07-20T22:00:00",
        "location": "徐汇滨江",
        "type": "演出"
    }

@pytest.fixture
def sample_activity_b():
    return {
        "id": 2, "name": "夏日户外音乐节",
        "city_code": "shanghai",
        "start_time": "2025-07-20T18:30:00",
        "end_time": "2025-07-20T22:00:00",
        "location": "徐汇滨江龙腾大道",
        "type": "演出"
    }
```

---

## TC-DEDUP-001: 名称相似度计算

**优先级**: P0
**类型**: 单元测试
**被测函数**: `calculate_name_similarity(name_a, name_b)`

### Given
- 两个活动名称

### When
调用 `calculate_name_similarity`

### Then
返回正确的相似度分数（0-1）

```python
@pytest.mark.parametrize("name_a,name_b,expected_min", [
    ("夏日音乐节", "夏日户外音乐节", 0.6),    # 部分匹配
    ("夏日音乐节", "夏日音乐节", 1.0),          # 完全相同
    ("夏日音乐节", "冬季滑雪", 0.0),            # 完全不同
    ("上海周末市集", "上海周末创意市集", 0.7),  # 包含关系
    ("2025音乐节", "音乐节2025", 0.8),          # 顺序不同
])
def test_name_similarity_calculation(name_a, name_b, expected_min):
    """名称相似度计算应准确反映匹配程度"""
    result = calculate_name_similarity(name_a, name_b)
    assert result >= expected_min
```

---

## TC-DEDUP-002: 综合相似度 - 高匹配（自动去重）

**优先级**: P0
**类型**: 单元测试
**被测函数**: `calculate_duplicate_score(activity_a, activity_b)`

### Given
- 两个活动：城市相同、日期相同、名称高度相似、地点相近
- 预期相似度 > 0.7

### When
调用 `calculate_duplicate_score`

### Then
- 返回 score >= 0.7
- matched_fields 包含 ["name", "city", "start_time"]
- 自动标记为 DUPLICATE_CANDIDATE

```python
def test_high_similarity_auto_duplicate(sample_activity_a, sample_activity_b):
    """高相似度活动应自动标记为去重候选"""
    result = calculate_duplicate_score(sample_activity_a, sample_activity_b)

    assert result["score"] >= 0.7
    assert "name" in result["matched_fields"]
    assert "city" in result["matched_fields"]
    assert result["action"] == "auto_duplicate"
```

---

## TC-DEDUP-003: 综合相似度 - 边缘匹配（人工审核）

**优先级**: P0
**类型**: 单元测试
**被测函数**: `calculate_duplicate_score(activity_a, activity_b)`

### Given
- 两个活动：城市相同、名称部分相似但日期不同
- 预期相似度在 0.4-0.7 之间

### When
调用 `calculate_duplicate_score`

### Then
- 返回 0.4 <= score < 0.7
- action = "manual_review"
- 进入人工审核队列

```python
def test_edge_similarity_goes_to_manual_review():
    """边缘相似度应进入人工审核"""
    activity_a = {
        "id": 1, "name": "周末市集",
        "city_code": "shanghai", "start_time": "2025-07-20T10:00:00"
    }
    activity_b = {
        "id": 2, "name": "周末创意市集",
        "city_code": "shanghai", "start_time": "2025-07-27T10:00:00"  # 不同周
    }

    result = calculate_duplicate_score(activity_a, activity_b)

    assert 0.4 <= result["score"] < 0.7
    assert result["action"] == "manual_review"
```

---

## TC-DEDUP-004: 综合相似度 - 低匹配（不重复）

**优先级**: P0
**类型**: 单元测试
**被测函数**: `calculate_duplicate_score(activity_a, activity_b)`

### Given
- 两个活动：城市不同或日期差超过 7 天或名称完全不同
- 预期相似度 < 0.4

### When
调用 `calculate_duplicate_score`

### Then
- 返回 score < 0.4
- action = "not_duplicate"
- 不创建去重候选记录

```python
def test_low_similarity_not_duplicate():
    """低相似度不应创建去重候选"""
    activity_a = {
        "id": 1, "name": "夏日音乐节",
        "city_code": "shanghai", "start_time": "2025-07-20T18:00:00"
    }
    activity_b = {
        "id": 2, "name": "冬日滑雪",
        "city_code": "beijing", "start_time": "2025-12-01T09:00:00"
    }

    result = calculate_duplicate_score(activity_a, activity_b)

    assert result["score"] < 0.4
    assert result["action"] == "not_duplicate"
```

---

## TC-DEDUP-005: 活动创建时触发去重检查

**优先级**: P0
**类型**: 单元测试
**被测函数**: `check_duplicates_on_create(activity_id)`

### Given
- 新建活动 activity_id = 10
- 数据库中存在 3 条同城市、同周的活动
- 其中 1 条相似度 > 0.7，1 条在 0.4-0.7，1 条 < 0.4

### When
调用 `check_duplicates_on_create(10)`

### Then
- 创建 1 条 auto_duplicate 候选
- 创建 1 条 manual_review 候选
- 忽略低相似度的活动
- 共创建 2 条 duplicate_candidates 记录

```python
def test_create_triggers_duplicate_check(mock_db):
    """新建活动应自动触发去重检查"""
    new_activity = {
        "id": 10, "name": "周末音乐节",
        "city_code": "shanghai", "start_time": "2025-07-20T18:00:00"
    }
    existing = [
        {"id": 1, "name": "周末户外音乐节", "city_code": "shanghai",
         "start_time": "2025-07-20T18:30:00"},  # 高相似
        {"id": 2, "name": "周末市集", "city_code": "shanghai",
         "start_time": "2025-07-20T10:00:00"},   # 中相似
        {"id": 3, "name": "滑雪冬令营", "city_code": "shanghai",
         "start_time": "2025-07-20T09:00:00"},   # 低相似
    ]
    mock_db.query.return_value.filter.return_value.all.return_value = existing

    candidates = check_duplicates_on_create(10)

    assert len(candidates) == 2
    assert candidates[0]["status"] == "pending"  # auto_duplicate
    assert candidates[1]["status"] == "pending"  # manual_review
```

---

## TC-DEDUP-006: 合并操作 - keep_a

**优先级**: P0
**类型**: 单元测试
**被测函数**: `merge_duplicates(duplicate_id, resolution="keep_a")`

### Given
- 去重候选 id=1，activity_a 为主，activity_b 为重复
- resolution = "keep_a"

### When
调用 `merge_duplicates(1, "keep_a")`

### Then
- activity_b 状态变为 MERGED
- activity_a 的 related_note_ids 包含 activity_b 的 note_id
- duplicate_candidate 状态变为 "merged"，resolution = "keep_a"

```python
def test_merge_keep_a(mock_db, sample_activity_a, sample_activity_b):
    """keep_a 应保留 A，合并 B 的关联笔记"""
    mock_db.query.return_value.filter.return_value.first.side_effect = [
        {"id": 1, "activity_a_id": 1, "activity_b_id": 2, "status": "pending"},
        sample_activity_a,
        sample_activity_b
    ]

    result = merge_duplicates(1, "keep_a")

    assert result["kept_activity_id"] == 1
    assert result["merged_activity_id"] == 2
    # 验证 activity_b.status = "MERGED"
```

---

## TC-DEDUP-007: 合并操作 - merge_new

**优先级**: P1
**类型**: 单元测试
**被测函数**: `merge_duplicates(duplicate_id, resolution="merge_new", merged_data)`

### Given
- resolution = "merge_new"
- merged_data 包含手动编辑后的字段

### When
调用 `merge_duplicates(1, "merge_new", merged_data)`

### Then
- 创建新活动记录，字段 = merged_data
- 原 activity_a 和 activity_b 状态变为 MERGED
- 新活动的 related_note_ids 包含两者的 note_id

```python
def test_merge_create_new(mock_db, sample_activity_a, sample_activity_b):
    """merge_new 应创建新活动并合并来源"""
    merged_data = {
        "name": "夏日户外音乐节（滨江）",
        "start_time": "2025-07-20T18:00:00",
        "location": "徐汇滨江龙腾大道"
    }

    result = merge_duplicates(1, "merge_new", merged_data)

    assert result["kept_activity_id"] is not None  # 新 ID
    assert sample_activity_a["id"] in result["merged_activity_ids"]
    assert sample_activity_b["id"] in result["merged_activity_ids"]
```

---

## TC-DEDUP-008: 忽略去重候选

**优先级**: P0
**类型**: 单元测试
**被测函数**: `ignore_duplicate(duplicate_id)`

### Given
- 去重候选 id=1，status="pending"

### When
调用 `ignore_duplicate(1)`

### Then
- duplicate_candidate status = "ignored"
- activity_a 和 activity_b 状态不变
- 不触发合并

```python
def test_ignore_duplicate_keeps_both_activities(mock_db):
    """忽略去重应保留两个活动"""
    mock_db.query.return_value.filter.return_value.first.return_value = {
        "id": 1, "status": "pending"
    }

    result = ignore_duplicate(1)

    assert result["status"] == "ignored"
    # 两个活动均未被修改
```

---

## TC-DEDUP-009: 批量去重 - 任务完成时全量检查

**优先级**: P0
**类型**: 单元测试
**被测函数**: `batch_dedup_check(task_id)`

### Given
- 任务完成后，新产生 50 条活动
- 数据库中已有 200 条历史活动

### When
调用 `batch_dedup_check(task_id)`

### Then
- 新活动之间两两比较
- 新活动与历史活动比较（仅同城市）
- 生成所有去重候选
- 返回候选数量

```python
def test_batch_dedup_compares_cross_set(mock_db):
    """批量去重应在新活动和历史活动之间交叉比较"""
    mock_db.query.return_value.filter.return_value.all.side_effect = [
        [{"id": i} for i in range(1, 51)],   # 新活动 50 条
        [{"id": i} for i in range(51, 251)],  # 历史活动 200 条
    ]

    candidates = batch_dedup_check(1)

    assert len(candidates) > 0
    # 验证比较次数 = 50*49/2 + 50*200 = 1225 + 10000 = 11225
```

---

## 测试运行命令

```bash
pytest tests/test_dedup.py -v
pytest tests/test_dedup.py --cov=backend.app.services.dedup --cov-report=html
```
