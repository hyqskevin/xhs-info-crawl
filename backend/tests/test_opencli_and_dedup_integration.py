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

def test_duplicate_candidates_are_created_once(db_session):
    when=datetime(2026,7,18,10,tzinfo=timezone.utc)
    first=Activity(name='上海夏日音乐节',city_code='shanghai',start_time=when,location='徐汇滨江',price='免费',type='演出',status='RAW')
    second=Activity(name='上海夏日音乐节2026',city_code='shanghai',start_time=when,location='徐汇滨江',price='免费',type='演出',status='RAW')
    db_session.add_all([first,second]);db_session.flush()
    assert len(create_duplicate_candidates(db_session,second))==1
    db_session.flush()
    assert len(create_duplicate_candidates(db_session,second))==0
    assert db_session.query(DuplicateCandidate).count()==1
