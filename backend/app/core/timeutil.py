"""全工程统一时区工具：存储与业务口径 = 北京墙钟 naive（Asia/Shanghai）。

关联 spec: docs/superpowers/specs/2026-09-07-unify-beijing-timezone-design.md
- now_cn(): 生产代码所有"当前时间"的唯一入口（models default / api / services / tasks）
- to_cn_naive(): aware → 北京墙钟 naive；naive 视为已是北京墙钟（单口径约定）

协议内部时间（JWT exp、文件 mtime cutoff）不使用本模块，保持 aware UTC。
"""
from datetime import datetime
from zoneinfo import ZoneInfo

CN_TZ = ZoneInfo("Asia/Shanghai")


def now_cn() -> datetime:
    return datetime.now(CN_TZ).replace(tzinfo=None)


def to_cn_naive(value: datetime) -> datetime:
    return value.astimezone(CN_TZ).replace(tzinfo=None) if value.tzinfo else value
