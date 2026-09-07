"""统一 JSON 响应：所有 datetime 序列化为带 +08:00 后缀的 ISO8601（北京墙钟口径）。

背景：SQLite 存 naive 北京墙钟，FastAPI 响应出口时 datetime 已被 jsonable_encoder
预编码为字符串（如 '2026-08-16T05:18:59.429459'），没有 tz 后缀，JS 会按本机时区
解析。本模块在 render 出口检测 naive ISO datetime 字符串并追加 '+08:00'，任何机器
时区下都能解析出正确时刻。

前端 formatCnDateTime 对 +08:00 输入直接格式化；历史 Z 后缀输入仍兼容。
"""
from __future__ import annotations

import re
from datetime import datetime
from typing import Any

from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse

from app.core.timeutil import CN_TZ

# 匹配无 tz 后缀的 ISO 8601 datetime 字符串
# 如 '2026-08-16T05:18:59' 或 '2026-08-16T05:18:59.429459'
# 已带 Z/偏移的字符串不匹配，普通文本不匹配
_NAIVE_DT_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?$")


def _normalize_dt_inplace(obj: Any) -> Any:
    """递归把 naive datetime 对象标 tzinfo=CN_TZ，并把 naive ISO 字符串补 +08:00。

    FastAPI 在调用 render() 前已通过 jsonable_encoder 把 datetime 转为字符串，
    因此正常情况下不会走到 datetime 分支；保留该分支作为防御性编程。
    """
    if isinstance(obj, datetime):
        if obj.tzinfo is None:
            obj = obj.replace(tzinfo=CN_TZ)
        return obj
    if isinstance(obj, str) and _NAIVE_DT_RE.match(obj):
        return obj + "+08:00"
    if isinstance(obj, dict):
        for k, v in list(obj.items()):
            obj[k] = _normalize_dt_inplace(v)
        return obj
    if isinstance(obj, list):
        for i, v in enumerate(obj):
            obj[i] = _normalize_dt_inplace(v)
        return obj
    if isinstance(obj, tuple):
        return tuple(_normalize_dt_inplace(v) for v in obj)
    return obj


class CnJsonResponse(JSONResponse):
    """在 render 前把所有 naive datetime 字符串补上 '+08:00' 后缀。

    FastAPI 在调用 render() 之前已通过 jsonable_encoder 把 Python 对象
    序列化为 JSON 类型（datetime → str），因此 _normalize_dt_inplace
    主要处理字符串格式。保留 datetime 分支作为防御性编程。
    """

    def render(self, content: Any) -> bytes:
        if content is None:
            return super().render(content)
        normalized = _normalize_dt_inplace(content)
        encoded = jsonable_encoder(normalized)
        return super().render(encoded)
