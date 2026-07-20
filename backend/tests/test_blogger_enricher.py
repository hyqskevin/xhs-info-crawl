"""博主自动补全：把只填了 username 的博主通过 search 找回 user_id/profile_url。

这是真实场景的修复：用户经常只知道博主名字，先建了空 profile_url/xhs_id 的博主；
抓取脚本启动时顺便用 search 把这些信息补上。
"""

import pytest
from sqlalchemy.orm import Session

from app.models.config import Blogger


def _make_blogger(db_session: Session, username: str, profile_url: str = "", platform_user_id: str | None = None) -> Blogger:
    b = Blogger(
        username=username,
        profile_url=profile_url,
        platform_user_id=platform_user_id,
        enabled=True,
    )
    db_session.add(b)
    db_session.commit()
    return b


def test_enrich_fills_profile_url_and_user_id_when_missing(monkeypatch, db_session: Session):
    b = _make_blogger(db_session, "从零发现宁波")
    captured: dict = {}

    def fake_search_runner(args: list[str]) -> list[dict]:
        captured["args"] = args
        return [
            {
                "author": "从零发现宁波",
                "author_url": "https://www.xiaohongshu.com/user/profile/619ca5dc0000000010007e92?channel_type=web_search_result_notes",
            },
            {
                "author": "另一个博主",
                "author_url": "https://www.xiaohongshu.com/user/profile/aaaaaaaaaaaaaaaaaaaaaaaa",
            },
        ]

    from app.services.blogger_enricher import enrich_bloggers

    filled = enrich_bloggers(db_session, [b], search_runner=fake_search_runner, limit=5)

    assert filled == [b.id]
    assert "从零发现宁波" in captured["args"]
    db_session.refresh(b)
    assert b.platform_user_id == "619ca5dc0000000010007e92"
    assert b.profile_url == "https://www.xiaohongshu.com/user/profile/619ca5dc0000000010007e92"


def test_enrich_skips_bloggers_that_already_have_profile_url(monkeypatch, db_session: Session):
    b = _make_blogger(db_session, "已配置", profile_url="https://www.xiaohongshu.com/user/profile/existing")
    called = {"count": 0}

    def should_not_run(args):
        called["count"] += 1
        return []

    from app.services.blogger_enricher import enrich_bloggers

    filled = enrich_bloggers(db_session, [b], search_runner=should_not_run, limit=5)
    assert filled == []
    assert called["count"] == 0


def test_enrich_handles_search_no_match(monkeypatch, db_session: Session):
    b = _make_blogger(db_session, "找不到的博主")

    def fake_search_runner(args):
        return [{"author": "别的博主", "author_url": "https://xhs/user/profile/zzz"}]

    from app.services.blogger_enricher import enrich_bloggers

    filled = enrich_bloggers(db_session, [b], search_runner=fake_search_runner, limit=5)
    assert filled == []
    db_session.refresh(b)
    assert b.profile_url == ""
    assert b.platform_user_id is None


def test_enrich_skips_existing_platform_user_id(monkeypatch, db_session: Session):
    b = _make_blogger(
        db_session, "只有名字",
        profile_url="",
        platform_user_id="existing_user_id",
    )

    def fake_search_runner(args):
        return [
            {"author": "只有名字", "author_url": "https://xhs/user/profile/new_id"},
        ]

    from app.services.blogger_enricher import enrich_bloggers

    filled = enrich_bloggers(db_session, [b], search_runner=fake_search_runner, limit=5)
    assert filled == [b.id]
    db_session.refresh(b)
    # platform_user_id 已存在，应保留
    assert b.platform_user_id == "existing_user_id"
    # 但 profile_url 空，应当补
    assert b.profile_url == "https://www.xiaohongshu.com/user/profile/new_id"
