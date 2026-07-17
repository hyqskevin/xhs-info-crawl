from types import SimpleNamespace

from app.services.browser_launcher import open_xhs_login


def test_macos_launcher_opens_configured_url_in_chrome_without_shell() -> None:
    calls = []
    settings = SimpleNamespace(
        xhs_login_url="https://www.xiaohongshu.com/explore",
        xhs_login_browser="Google Chrome",
    )

    url = open_xhs_login(
        settings,
        platform_name="darwin",
        run=lambda args, **kwargs: calls.append((args, kwargs)),
    )

    assert url == settings.xhs_login_url
    assert calls == [
        (["open", "-a", "Google Chrome", "https://www.xiaohongshu.com/explore"], {"check": True})
    ]
