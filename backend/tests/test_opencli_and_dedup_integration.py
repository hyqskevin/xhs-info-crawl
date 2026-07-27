from pathlib import Path
import subprocess
import pytest
from app.core.config import Settings
from app.services.opencli_adapter import OpenCLIAdapter

def test_note_field_value_rows_are_normalized_to_object():
    rows=[{'field':'title','value':'活动标题'},{'field':'content','value':'活动正文'},{'field':'likes','value':12}]
    assert OpenCLIAdapter.normalize_note(rows)=={'title':'活动标题','content':'活动正文','likes':12}

def test_note_rejects_empty_url(tmp_path:Path,monkeypatch):
    from app.services.crawler import OpenCLIError
    adapter=OpenCLIAdapter(Settings(project_root=tmp_path))
    called=False
    def run(args):
        nonlocal called; called=True; return {}
    monkeypatch.setattr(adapter,'run',run)
    for bad in ['', None, '   ']:
        try:
            adapter.note(bad)
        except OpenCLIError as exc:
            assert '笔记 url 为空' in str(exc)
        else:
            raise AssertionError(f'expected OpenCLIError for url={bad!r}')
    assert called is False, 'run() should not be invoked when url is empty'

def test_blogger_notes_rejects_empty_profile_url(tmp_path:Path,monkeypatch):
    """博主 profile_url 为空时 blogger_notes 抛 OpenCLIError，不调子命令。"""
    from app.services.crawler import OpenCLIError
    adapter=OpenCLIAdapter(Settings(project_root=tmp_path))
    called=False
    def run(args):
        nonlocal called; called=True; return []
    monkeypatch.setattr(adapter,'run',run)
    for bad in ['', None, '   ']:
        try:
            adapter.blogger_notes('博主', bad)
        except OpenCLIError as exc:
            assert 'profile_url 为空' in str(exc)
        else:
            raise AssertionError(f'expected OpenCLIError for profile_url={bad!r}')
    assert called is False


def test_blogger_notes_rejects_invalid_profile_url(tmp_path:Path,monkeypatch):
    """博主 profile_url 格式不正确无法提取 user-id 时抛 OpenCLIError。"""
    from app.services.crawler import OpenCLIError
    adapter=OpenCLIAdapter(Settings(project_root=tmp_path))
    called=False
    def run(args):
        nonlocal called; called=True; return []
    monkeypatch.setattr(adapter,'run',run)
    try:
        adapter.blogger_notes('博主', 'https://www.xiaohongshu.com/wrong/path/123')
    except OpenCLIError as exc:
        assert '无法从 profile_url 提取 user-id' in str(exc)
    else:
        raise AssertionError('expected OpenCLIError for invalid profile_url')
    assert called is False


def test_blogger_notes_returns_notes_with_xsec_token(tmp_path:Path,monkeypatch):
    """blogger_notes 返回带 xsec_token 的笔记列表。"""
    adapter=OpenCLIAdapter(Settings(project_root=tmp_path))
    calls=[]
    def run(args):
        calls.append(args)
        if args[:2]==['xiaohongshu','whoami']:
            return {'logged_in':True}
        if args[:2]==['xiaohongshu','user']:
            return [
                {
                    'id': '69142d3e000000000302e5ec',
                    'title': '宁波活动锦集',
                    'url': 'https://www.xiaohongshu.com/user/profile/619ca5dc0000000010007e92/69142d3e000000000302e5ec?xsec_token=ABC&xsec_source=pc_user',
                },
                {
                    'id': '68a7df12000000001d020ee2',
                    'title': '宁波美食推荐',
                    'url': 'https://www.xiaohongshu.com/user/profile/619ca5dc0000000010007e92/68a7df12000000001d020ee2?xsec_token=DEF&xsec_source=pc_user',
                },
            ]
        return {'ok':True}
    monkeypatch.setattr(adapter,'run',run)

    notes = adapter.blogger_notes('从零发现宁波', 'https://www.xiaohongshu.com/user/profile/619ca5dc0000000010007e92')

    assert len(notes) == 2
    assert notes[0]['title'] == '宁波活动锦集'
    assert notes[0]['author'] == '从零发现宁波'
    assert 'xsec_token=ABC' in notes[0]['url']
    assert notes[1]['title'] == '宁波美食推荐'
    assert 'xsec_token=DEF' in notes[1]['url']

    user_calls = [args for args in calls if args[:2]==['xiaohongshu','user']]
    assert len(user_calls) == 1
    assert user_calls[0][2] == '619ca5dc0000000010007e92'

def test_download_rejects_empty_url(tmp_path:Path,monkeypatch):
    from app.services.crawler import OpenCLIError
    adapter=OpenCLIAdapter(Settings(project_root=tmp_path))
    called=False
    def run(args):
        nonlocal called; called=True; return {}
    monkeypatch.setattr(adapter,'run',run)
    try:
        adapter.download('', tmp_path/'out')
    except OpenCLIError as exc:
        assert '笔记 url 为空' in str(exc)
    else:
        raise AssertionError('expected OpenCLIError for empty url')
    assert called is False


def test_run_translates_security_challenge_before_generic_error(tmp_path: Path, monkeypatch):
    from app.services.crawler import VerificationRequired

    adapter = OpenCLIAdapter(Settings(project_root=tmp_path))

    class FakeProc:
        pid = 12346
        returncode = 1

        def communicate(self, timeout=None):
            return "", "检测到 captcha，请完成安全验证"

    monkeypatch.setattr(subprocess, "Popen", lambda *args, **kwargs: FakeProc())

    with pytest.raises(VerificationRequired, match="安全验证"):
        adapter.run(["xiaohongshu", "search", "宁波活动"])

def test_run_translates_missing_url_error(tmp_path: Path, monkeypatch):
    from app.services.crawler import OpenCLIError

    adapter = OpenCLIAdapter(Settings(project_root=tmp_path))
    popen_calls: list[tuple[list[str], dict]] = []

    class FakeProc:
        pid = 12345
        returncode = 1

        def communicate(self, timeout=None):
            return "", "✖  Missing url\n"

        def kill(self):
            return None

    def fake_popen(command, **kwargs):
        popen_calls.append((command, kwargs))
        return FakeProc()

    monkeypatch.setattr(subprocess, "Popen", fake_popen)

    try:
        adapter.run(["browser", adapter.session, "open", "", "--window", "background"])
    except OpenCLIError as exc:
        message = str(exc)
        assert "Missing url" in message or "缺少 url" in message
    else:
        raise AssertionError("expected OpenCLIError for missing url from opencli")

    assert len(popen_calls) == 1
    command, kwargs = popen_calls[0]
    assert command == [
        "opencli",
        "browser",
        adapter.session,
        "open",
        "",
        "--window",
        "background",
    ]
    assert kwargs["text"] is True

def test_download_checks_login_and_returns_new_images(tmp_path:Path,monkeypatch):
    adapter=OpenCLIAdapter(Settings(project_root=tmp_path)); calls=[]
    def run(args):
        calls.append(args)
        if args[:2]==['xiaohongshu','download']:
            (tmp_path/'out'/'a.jpg').write_bytes(b'image')
        return {'ok':True}
    monkeypatch.setattr(adapter,'run',run)
    assert adapter.download('https://example/note',tmp_path/'out')==[tmp_path/'out'/'a.jpg']
    assert calls[0][:2]==['xiaohongshu','whoami']

def test_search_recent_uses_city_recent_filter(tmp_path:Path,monkeypatch):
    adapter=OpenCLIAdapter(Settings(project_root=tmp_path)); calls=[]
    def run(args):
        calls.append(args)
        if args[:2]==['xiaohongshu','whoami']: return {'logged_in':True}
        if args[:3]==['browser',adapter.session,'eval'] and 'optionExists' in args[3]: return True
        if args[:3]==['browser',adapter.session,'eval'] and 'targetText' in args[3]: return True
        if args[:3]==['browser',adapter.session,'eval']: return []
        return {'ok':True}
    monkeypatch.setattr(adapter,'run',run)
    assert adapter.search_recent('宁波 活动','半年内') == []
    assert ['browser',adapter.session,'click','.search-layout__top .filter'] in calls
    option_scripts=[args[3] for args in calls if args[:3]==['browser',adapter.session,'eval'] and 'targetText' in args[3]]
    assert any('最新' in script for script in option_scripts)
    assert any('半年内' in script for script in option_scripts)

def test_search_recent_uses_stable_dom_selectors_for_xhs_filters(tmp_path:Path,monkeypatch):
    adapter=OpenCLIAdapter(Settings(project_root=tmp_path)); calls=[]
    def run(args):
        calls.append(args)
        if args[:2]==['xiaohongshu','whoami']: return {'logged_in':True}
        if args[:3]==['browser',adapter.session,'eval'] and 'optionExists' in args[3]: return True
        if args[:3]==['browser',adapter.session,'eval'] and 'targetText' in args[3]: return True
        if args[:3]==['browser',adapter.session,'eval']: return []
        return {'ok':True}
    monkeypatch.setattr(adapter,'run',run)

    assert adapter.search_recent('宁波 活动','一周内') == []

    assert ['browser',adapter.session,'click','.search-layout__top .filter'] in calls
    option_scripts=[args[3] for args in calls if args[:3]==['browser',adapter.session,'eval'] and 'targetText' in args[3]]
    assert any('最新' in script for script in option_scripts)
    assert any('一周内' in script for script in option_scripts)

def test_search_recent_retries_until_filter_panel_is_really_open(tmp_path:Path,monkeypatch):
    adapter=OpenCLIAdapter(Settings(project_root=tmp_path)); calls=[]; probes=iter([False,True])
    def run(args):
        calls.append(args)
        if args[:2]==['xiaohongshu','whoami']: return {'logged_in':True}
        if args[:3]==['browser',adapter.session,'eval'] and 'optionExists' in args[3]: return next(probes)
        if args[:3]==['browser',adapter.session,'eval'] and 'targetText' in args[3]: return True
        if args[:3]==['browser',adapter.session,'eval']: return []
        return {'ok':True}
    monkeypatch.setattr(adapter,'run',run)

    assert adapter.search_recent('宁波 展览','一周内') == []

    filter_clicks=[args for args in calls if args==['browser',adapter.session,'click','.search-layout__top .filter']]
    assert len(filter_clicks) == 2
