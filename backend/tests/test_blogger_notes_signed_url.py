"""博主笔记抓取改用 user 命令：从 profile_url 提取 user-id，获取带 xsec_token 的完整 URL。

旧实现（bug）：使用 search 命令，返回空列表。
新实现：使用 user 命令，传入从 profile_url 提取的 user-id，获取带 token 的 URL。
"""

import pytest

from app.services.crawler import OpenCLIError


def _settings():
    from app.core.config import Settings
    return Settings()


def test_blogger_notes_uses_user_command_with_user_id(monkeypatch):
    """blogger_notes 应该通过 user 命令获取带 xsec_token 的 URL。"""
    from app.services.opencli_adapter import OpenCLIAdapter

    called = {"user_calls": []}

    def fake_run(self, args, **kwargs):
        if args[:2] == ["xiaohongshu", "user"]:
            called["user_calls"].append(args)
            return [
                {
                    "title": "宁波活动锦集",
                    "url": "https://www.xiaohongshu.com/user/profile/619ca5dc0000000010007e92/69142d3e000000000302e5ec?xsec_token=ABC&xsec_source=pc_user",
                },
                {
                    "title": "本周末展览",
                    "url": "https://www.xiaohongshu.com/user/profile/619ca5dc0000000010007e92/69142d3e000000000302e5ed?xsec_token=DEF&xsec_source=pc_user",
                },
            ]
        return None

    monkeypatch.setattr("app.services.opencli_adapter.OpenCLIAdapter.run", fake_run)
    monkeypatch.setattr(
        "app.services.opencli_adapter.OpenCLIAdapter.check_login",
        lambda self: None,
    )

    adapter = OpenCLIAdapter(_settings())
    notes = adapter.blogger_notes("从零发现宁波", "https://www.xiaohongshu.com/user/profile/619ca5dc0000000010007e92")

    assert called["user_calls"], "应该调用 user 命令"
    assert called["user_calls"][0][2] == "619ca5dc0000000010007e92", "user-id 提取正确"

    assert len(notes) == 2
    for n in notes:
        assert "xsec_token" in n["url"], f"URL 必须带 xsec_token: {n}"
        assert n["author"] == "从零发现宁波"


def test_blogger_notes_skips_results_without_xsec_token(monkeypatch):
    """user 结果里没 xsec_token 的应该被过滤掉。"""
    from app.services.opencli_adapter import OpenCLIAdapter

    def fake_run(self, args, **kwargs):
        if args[:2] == ["xiaohongshu", "user"]:
            return [
                {"title": "带 token", "url": "https://xhs.com/user/profile/aaa/bbb?xsec_token=XYZ"},
                {"title": "裸 URL", "url": "https://xhs.com/user/profile/aaa/ccc"},
            ]
        return None

    monkeypatch.setattr("app.services.opencli_adapter.OpenCLIAdapter.run", fake_run)
    monkeypatch.setattr(
        "app.services.opencli_adapter.OpenCLIAdapter.check_login",
        lambda self: None,
    )

    adapter = OpenCLIAdapter(_settings())
    notes = adapter.blogger_notes("博主", "https://www.xiaohongshu.com/user/profile/aaa")
    assert len(notes) == 1
    assert "xsec_token=XYZ" in notes[0]["url"]


def test_blogger_notes_raises_when_profile_url_empty():
    """profile_url 为空应该抛 OpenCLIError。"""
    from app.services.opencli_adapter import OpenCLIAdapter
    adapter = OpenCLIAdapter(_settings())
    with pytest.raises(OpenCLIError, match="profile_url"):
        adapter.blogger_notes("博主", "")


def test_blogger_notes_raises_when_user_id_not_found_in_profile_url():
    """profile_url 格式不正确无法提取 user-id 应该抛 OpenCLIError。"""
    from app.services.opencli_adapter import OpenCLIAdapter
    adapter = OpenCLIAdapter(_settings())
    with pytest.raises(OpenCLIError, match="无法从 profile_url 提取 user-id"):
        adapter.blogger_notes("博主", "https://www.xiaohongshu.com/wrong/path/123")


def test_blogger_notes_returns_empty_when_no_results(monkeypatch):
    """user 没结果时返回空 list，不抛错。"""
    from app.services.opencli_adapter import OpenCLIAdapter

    def fake_run(self, args, **kwargs):
        if args[:2] == ["xiaohongshu", "user"]:
            return []
        return None

    monkeypatch.setattr("app.services.opencli_adapter.OpenCLIAdapter.run", fake_run)
    monkeypatch.setattr(
        "app.services.opencli_adapter.OpenCLIAdapter.check_login",
        lambda self: None,
    )

    adapter = OpenCLIAdapter(_settings())
    notes = adapter.blogger_notes("某博主", "https://www.xiaohongshu.com/user/profile/abc")
    assert notes == []


def test_blogger_notes_extracts_user_id_correctly(monkeypatch):
    """从不同格式的 profile_url 中正确提取 user-id。"""
    from app.services.opencli_adapter import OpenCLIAdapter

    user_ids = []

    def fake_run(self, args, **kwargs):
        if args[:2] == ["xiaohongshu", "user"]:
            user_ids.append(args[2])
            return []
        return None

    monkeypatch.setattr("app.services.opencli_adapter.OpenCLIAdapter.run", fake_run)
    monkeypatch.setattr(
        "app.services.opencli_adapter.OpenCLIAdapter.check_login",
        lambda self: None,
    )

    adapter = OpenCLIAdapter(_settings())

    adapter.blogger_notes("博主1", "https://www.xiaohongshu.com/user/profile/619ca5dc0000000010007e92")
    adapter.blogger_notes("博主2", "https://www.xiaohongshu.com/user/profile/658fe303000000002001c74c?source=search")

    assert user_ids == ["619ca5dc0000000010007e92", "658fe303000000002001c74c"]
