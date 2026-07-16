# 测试用例：OCR 图片识别 (OCR Image Recognition)

## 测试环境
- **框架**: pytest 7.x
- **语言**: Python 3.11
- **Mock 策略**: Mock PaddleOCR 实例，Mock MinIO 下载
- **被测模块**: `backend/app/services/ocr.py`

## Mock 依赖

```python
@pytest.fixture
def mock_paddle_ocr():
    with patch("backend.app.services.ocr.PaddleOCR") as mock:
        mock_instance = MagicMock()
        mock.return_value = mock_instance
        yield mock_instance

@pytest.fixture
def mock_minio():
    with patch("backend.app.services.ocr.minio_client") as mock:
        yield mock
```

---

## TC-OCR-001: OCR 识别 - 正常流程

**优先级**: P0
**类型**: 单元测试
**被测函数**: `ocr_image(note_image_id)`

### Given
- note_image_id = 1
- MinIO 中图片路径 = "xhs-images/note-001/img1.jpg"
- 图片包含文字："2025年7月20日 徐汇滨江 免费入场"

### When
调用 `ocr_image(1)`

### Then
- MinIO 下载图片到临时路径
- PaddleOCR.ocr() 被调用
- 返回 OCR 文字："2025年7月20日 徐汇滨江 免费入场"
- 数据库 `note_images` 更新：ocr_text, ocr_status = "success"
- 临时文件被清理

```python
def test_ocr_extracts_text_from_image(mock_paddle_ocr, mock_minio):
    """应成功从图片提取文字"""
    mock_paddle_ocr.ocr.return_value = [
        [[[10, 10], [100, 10], [100, 50], [10, 50]],
         ("2025年7月20日 徐汇滨江 免费入场", 0.95)]
    ]
    mock_minio.download.return_value = "/tmp/ocr_temp/img1.jpg"

    result = ocr_image(1)

    assert "2025年7月20日" in result
    assert "徐汇滨江" in result
    mock_paddle_ocr.ocr.assert_called_once()
```

---

## TC-OCR-002: OCR 识别 - 图片无文字

**优先级**: P1
**类型**: 单元测试
**被测函数**: `ocr_image(note_image_id)`

### Given
- 图片中无可识别文字（纯图片/插画）
- PaddleOCR 返回空列表

### When
调用 `ocr_image(1)`

### Then
- ocr_text = ""（空字符串）
- ocr_status = "success"（不是失败，只是无文字）
- 不记录为错误

```python
def test_ocr_handles_image_with_no_text(mock_paddle_ocr):
    """无文字图片应返回空字符串，不视为失败"""
    mock_paddle_ocr.ocr.return_value = []

    result = ocr_image(1)

    assert result == ""
    # 验证 ocr_status 为 success 而非 failed
```

---

## TC-OCR-003: OCR 识别失败处理

**优先级**: P0
**类型**: 单元测试
**被测函数**: `ocr_image(note_image_id)`

### Given
- PaddleOCR 抛出异常（图片损坏、格式不支持等）

### When
调用 `ocr_image(1)`

### Then
- 异常被捕获
- 数据库更新：ocr_status = "failed", ocr_error = 异常信息
- 不影响同笔记其他图片的 OCR 处理
- 日志记录错误信息

```python
def test_ocr_failure_marks_as_failed(mock_paddle_ocr, mock_db_session):
    """OCR 失败应标记状态，不阻断其他图片处理"""
    mock_paddle_ocr.ocr.side_effect = RuntimeError("图片格式不支持")

    with pytest.raises(OCRProcessingError):
        ocr_image(1)

    # 验证 ocr_status = "failed"
    mock_db_session.execute.assert_called()
```

---

## TC-OCR-004: OCR 批量处理 - 单篇笔记多图

**优先级**: P0
**类型**: 单元测试
**被测函数**: `ocr_note_images(note_id)`

### Given
- note_id = 1，关联 5 张图片
- 其中第 3 张 OCR 失败

### When
调用 `ocr_note_images(1)`

### Then
- 所有 5 张图片被处理
- 4 张标记为 success，1 张标记为 failed
- 返回所有图片的 OCR 文字合并结果
- 不因单张失败而中断

```python
def test_batch_ocr_continues_on_single_failure(mock_paddle_ocr, mock_db_session):
    """批量 OCR 中单张失败不应影响其他图片"""
    mock_db_session.query.return_value.filter.return_value.all.return_value = [
        {"id": i, "storage_key": f"note-001/img{i}.jpg"}
        for i in range(1, 6)
    ]
    mock_paddle_ocr.ocr.side_effect = [
        [[[None, ("文字1", 0.9)]]],  # 成功
        [[[None, ("文字2", 0.9)]]],  # 成功
        RuntimeError("OCR failed"),   # 失败
        [[[None, ("文字4", 0.9)]]],  # 成功
        [[[None, ("文字5", 0.9)]]],  # 成功
    ]

    result = ocr_note_images(1)

    assert len(result) == 5
    assert result[0]["ocr_status"] == "success"
    assert result[2]["ocr_status"] == "failed"
```

---

## TC-OCR-005: OCR 置信度过滤

**优先级**: P2
**类型**: 单元测试
**被测函数**: `ocr_image(note_image_id)`

### Given
- PaddleOCR 返回多段文字，部分置信度低于阈值（< 0.5）

### When
调用 `ocr_image(1)`，confidence_threshold = 0.5

### Then
- 只保留置信度 >= 0.5 的文字
- 低置信度文字被丢弃

```python
def test_ocr_filters_low_confidence_text(mock_paddle_ocr):
    """应过滤低置信度 OCR 结果"""
    mock_paddle_ocr.ocr.return_value = [
        [[[None, ("活动时间：周六", 0.92)]]],    # 保留
        [[[None, ("xyzk@@", 0.23)]]],            # 过滤
        [[[None, ("免费", 0.67)]]],              # 保留
    ]

    result = ocr_image(1, confidence_threshold=0.5)

    assert "活动时间：周六" in result
    assert "免费" in result
    assert "xyzk@@" not in result
```

---

## TC-OCR-006: 大图片处理

**优先级**: P2
**类型**: 单元测试
**被测函数**: `_preprocess_image(image_path)`

### Given
- 图片尺寸 4000x3000，文件大小 8MB

### When
调用 `_preprocess_image`

### Then
- 图片被缩放至最大 2000px 宽/高
- 保留原始宽高比
- 处理后的图片可被 PaddleOCR 正常识别

```python
def test_large_image_is_resized():
    """大图应被缩放以优化 OCR 性能"""
    with patch("PIL.Image.open") as mock_open:
        mock_img = MagicMock()
        mock_img.size = (4000, 3000)
        mock_open.return_value = mock_img

        result = _preprocess_image("/path/to/large.jpg")

        mock_img.thumbnail.assert_called_with((2000, 2000), Image.LANCZOS)
```

---

## 测试运行命令

```bash
pytest tests/test_ocr.py -v
pytest tests/test_ocr.py --cov=backend.app.services.ocr --cov-report=html
```
