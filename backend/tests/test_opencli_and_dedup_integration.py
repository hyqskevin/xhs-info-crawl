from datetime import datetime,timezone
from pathlib import Path
from app.core.config import Settings
from app.models.activity import Activity
from app.models.duplicate import DuplicateCandidate
from app.services.dedup import create_duplicate_candidates
from app.services.opencli_adapter import OpenCLIAdapter

def test_note_field_value_rows_are_normalized_to_object():
    rows=[{'field':'title','value':'活动标题'},{'field':'content','value':'活动正文'},{'field':'likes','value':12}]
    assert OpenCLIAdapter.normalize_note(rows)=={'title':'活动标题','content':'活动正文','likes':12}

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

def test_duplicate_candidates_are_created_once(db_session):
    when=datetime(2026,7,18,10,tzinfo=timezone.utc)
    first=Activity(name='上海夏日音乐节',city_code='shanghai',start_time=when,location='徐汇滨江',price='免费',type='演出',status='RAW')
    second=Activity(name='上海夏日音乐节2026',city_code='shanghai',start_time=when,location='徐汇滨江',price='免费',type='演出',status='RAW')
    db_session.add_all([first,second]);db_session.flush()
    assert len(create_duplicate_candidates(db_session,second))==1
    db_session.flush()
    assert len(create_duplicate_candidates(db_session,second))==0
    assert db_session.query(DuplicateCandidate).count()==1


def test_duplicate_candidates_tolerate_missing_start_times(db_session):
    first = Activity(name='宁波纳得美术馆作品展览', city_code='nb', start_time=None, location='宁波纳得美术馆', price='', type='展览', status='NEEDS_REVIEW')
    second = Activity(name='宁波纳得美术馆作品展览', city_code='nb', start_time=None, location='宁波纳得美术馆', price='', type='展览', status='NEEDS_REVIEW')
    db_session.add_all([first, second])
    db_session.flush()

    candidates = create_duplicate_candidates(db_session, second)

    assert len(candidates) == 1
    assert candidates[0].similarity == 0.75
    assert candidates[0].matched_fields == 'city'
