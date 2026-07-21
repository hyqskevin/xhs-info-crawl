"""从小红书 note ID（ObjectID 雪花算法）解析推文发布时间。

小红书 note ID 是 24 hex 的 mongo-like ObjectID：前 8 个 hex 字符是 epoch 秒
（按 UTC+8 计）。转换为带 tzinfo=UTC 的 datetime。"""
import re
from datetime import datetime, timezone


_NOTE_ID_RE = re.compile(r"[0-9a-f]{24}", re.IGNORECASE)


def note_id_published_at(note_id_or_url: str | None) -> datetime | None:
    """从 note ID 或完整 URL 中提取 24 hex；前 8 hex = epoch 秒。

    返回 tzinfo=UTC 的 datetime，精度到秒。
    非法输入（None/空/无 24hex/全 0/超出合理 epoch 范围）返回 None。
    """
    if not note_id_or_url:
        return None
    match = _NOTE_ID_RE.search(note_id_or_url)
    if not match:
        return None
    hex_prefix = match.group(0)[:8]
    try:
        ts = int(hex_prefix, 16)
    except ValueError:
        return None
    if ts < 1_000_000_000 or ts > 4_000_000_000:
        return None
    # 复现 OpenCLI noteIdToDate 算法：加 8 小时对齐 UTC+8 后转 UTC。
    # 0x697f6c74 = 1769958516 → +8h → 1769987316 UTC = 2026-02-01 23:08:36 UTC = "2026-02-01".
    return datetime.fromtimestamp(ts + 8 * 3600, tz=timezone.utc)
