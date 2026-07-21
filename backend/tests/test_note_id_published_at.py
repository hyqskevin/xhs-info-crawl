"""从小红书 note ID（ObjectID 雪花算法）解析推文发布时间。

小红书 note ID 是 24 hex 的 mongo-like ObjectID。前 8 hex 字符是 epoch 秒。
按 UTC+8 + 0h 偏移转 UTC 即得到推文创建瞬间。"""
from datetime import datetime, timezone

from app.services.note_id_published_at import note_id_published_at


def test_extracts_published_at_from_known_url() -> None:
    # 0x697f6c74 = 1769958516 epoch 秒 + 8h 对齐 = 1769987316 UTC = 2026-02-01 23:08:36 UTC
    ts = note_id_published_at("https://www.xiaohongshu.com/search_result/697f6c74000000002103de17?xsec_token=abc")
    assert ts is not None
    expected = datetime.fromtimestamp(1769958516 + 8 * 3600, tz=timezone.utc)
    assert ts == expected
    # UTC+8 视角日期："2026-02-02"（与 UTC 边界 23h08m）
    assert ts.strftime("%Y-%m-%d") in ("2026-02-01", "2026-02-02")


def test_handles_explore_path_variant() -> None:
    ts = note_id_published_at("https://www.xiaohongshu.com/explore/68e90be80000000004022e66")
    assert ts is not None
    # 0x68e90be8 = 1760103400 epoch 秒 + 8h = 1760132200 UTC = 2025-10-10 21:36:40 UTC
    expected = datetime.fromtimestamp(1760103400 + 8 * 3600, tz=timezone.utc)
    assert ts == expected
    # 北京时区视角：2025-10-11，但这里只校验 UTC 字符串
    assert ts.year == 2025
    assert ts.month == 10
    assert ts.day == 10 or ts.day == 11


def test_returns_none_for_short_or_invalid_id() -> None:
    # 6 hex 字符 < 24，不能解析
    assert note_id_published_at("https://www.xiaohongshu.com/search_result/abcdef") is None


def test_returns_none_for_empty_or_url_without_path() -> None:
    assert note_id_published_at(None) is None
    assert note_id_published_at("") is None
    assert note_id_published_at("https://www.xiaohongshu.com/") is None
    # 24 hex 字符但全 0 (epoch 0)
    assert note_id_published_at("https://www.xiaohongshu.com/search_result/000000000000000000000000") is None


def test_extracts_24hex_from_bare_id() -> None:
    """能直接接 24hex 字符串，不需要 URL。"""
    ts = note_id_published_at("697f6c74000000002103de17")
    assert ts is not None
    assert ts.strftime("%Y-%m-%d") == "2026-02-01"
