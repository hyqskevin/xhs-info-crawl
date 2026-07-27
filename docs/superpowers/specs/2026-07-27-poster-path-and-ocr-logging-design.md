# poster 路径校验统一 + notes OCR 异常可见性 — 设计 spec

> 对应 `docs/TODO.md` 待办 #8。

## 背景

代码审查发现两个小缺陷（证据：`docs/superpowers/qa/2026-07-25-project-audit.md`）：

1. `poster_tasks.py note_image_by_id`（:126）用 `str(target).startswith(str(base))` 做路径穿越防护。字符串前缀可被同前缀兄弟目录绕过：`base=/x/data` 时 `/x/data-evil/pic.jpg` 也通过校验。项目内 `notes.py get_note_image`（:235）已用正确的 `Path.is_relative_to`，两处口径不一。
2. `notes.py` 笔记列表 OCR 聚合（:158-167）`except Exception: ocr_map = {}` 静默吞掉所有异常，DB 故障时前端看到「无 OCR」假象，排查无日志。

## 设计

### 8.1 路径校验统一为 `Path.is_relative_to`

`note_image_by_id` 改为与 `get_note_image` 相同写法：

```python
if not target.is_relative_to(base) or not target.is_file():
    raise HTTPException(404, "图片文件不存在")
```

`is_relative_to` 按路径段比较，`/x/data-evil` 不是 `/x/data` 的后代，绕过失效。行为对正常存储 key 无变化（404 语义不变）。

### 8.2 OCR 聚合异常记 WARNING

`except Exception` 分支改为 `logger.warning("笔记列表 OCR 聚合失败 note_ids=%s: %s", note_ids, exc)`，返回仍降级为空 OCR map（列表可用性优先，但留下可查日志）。

## 验收

- 定向测试：构造 `storage_key` 指向同前缀兄弟目录的 NoteImage，`note_image_by_id` 返回 404（修复前会 200 泄露文件）；
- 定向测试：OCR 查询抛异常时响应仍 200 且产生 WARNING 日志（caplog 断言）；
- 全量后端测试绿。
