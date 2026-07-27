"""从小红书 note ID（ObjectID 雪花算法）解析推文发布时间。

小红书 note ID 是 24 hex 的 mongo-like ObjectID。前 8 hex 字符是 epoch 秒。
按 UTC+8 解读，返回 Asia/Shanghai 时区的北京墙钟 datetime
（口径修订 spec: 2026-07-27-review-consistency-fixes-design.md）。"""
from datetime import datetime

from app.services.note_id_published_at import note_id_published_at
from app.services.published_at import SHANGHAI


def test_extracts_published_at_from_known_url() -> None:
    # 0x697f6c74 = 1769958516 epoch 秒 → 2026-02-01 23:08:36 +08:00（北京墙钟）
    ts = note_id_published_at("https://www.xiaohongshu.com/search_result/697f6c74000000002103de17?xsec_token=abc")
    assert ts is not None
    expected = datetime.fromtimestamp(1769958516, tz=SHANGHAI)
    assert ts == expected
    assert ts.strftime("%Y-%m-%d") == "2026-02-01"


def test_handles_explore_path_variant() -> None:
    ts = note_id_published_at("https://www.xiaohongshu.com/explore/68e90be80000000004022e66")
    assert ts is not None
    # 0x68e90be8 = 1760103400 epoch 秒 → 2025-10-10 21:36:40 +08:00
    expected = datetime.fromtimestamp(1760103400, tz=SHANGHAI)
    assert ts == expected
    assert ts.year == 2025
    assert ts.month == 10
    assert ts.day == 10


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


def test_profile_url_uses_note_id_not_user_id() -> None:
    """博主链接 /user/profile/<用户ID>/<笔记ID> 必须取笔记 ID（最后一个 24hex）。

    生产事故（任务 #19）：取第一个 24hex 解出的是博主注册时间 2021-09-18，
    导致 2026-07 发布的笔记显示为 2026 年以前。
    """
    url = "https://www.xiaohongshu.com/user/profile/6145b3a20000000002025fca/6a5f0b8e000000001c012957?xsec_token=ABmFa_Nq"
    ts = note_id_published_at(url)
    assert ts is not None
    # 笔记 ID 0x6a5f0b8e → 2026-07-21（北京墙钟）；用户 ID 0x6145b3a2 → 2021-09-18（错误答案）
    assert ts == datetime.fromtimestamp(0x6A5F0B8E, tz=SHANGHAI)
    assert ts.year == 2026 and ts.month == 7


def test_24hex_in_query_string_does_not_interfere() -> None:
    """query 中的 24hex（如 xsec_token 偶然全 hex）不能抢在笔记 ID 前面。"""
    url = "https://www.xiaohongshu.com/explore/697f6c74000000002103de17?xsec_token=6a5f0b8e000000001c012957"
    ts = note_id_published_at(url)
    assert ts is not None
    assert ts == datetime.fromtimestamp(0x697F6C74, tz=SHANGHAI)
