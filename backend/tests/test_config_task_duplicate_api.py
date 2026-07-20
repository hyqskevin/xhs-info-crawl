from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.security import create_access_token
from app.models.activity import Activity
from app.models.duplicate import NoteDuplicateCandidate
from app.models.note import Note
from app.models.task import CrawlTask, TaskLog
from app.services.crawler import AuthenticationRequired


@pytest.fixture
def headers():
    return {"Authorization": f"Bearer {create_access_token({'sub': 'admin', 'role': 'admin'})}"}


def test_city_keyword_blogger_crud(client: TestClient, headers):
    city = client.post('/api/v1/settings/cities', json={
        'name': '上海',
        'keywords': ['周末活动', '亲子活动'],
        'recent_filter': '一周内',
    }, headers=headers)
    assert city.status_code == 201
    created = city.json()['data']
    assert created['code'].startswith('city-')
    assert created['keywords'] == ['周末活动', '亲子活动']
    assert created['recent_filter'] == '一周内'

    updated = client.put(f"/api/v1/settings/cities/{created['id']}", json={
        'name': '上海市',
        'keywords': ['展览'],
        'recent_filter': '一天内',
        'enabled': False,
    }, headers=headers)
    assert updated.status_code == 200
    assert updated.json()['data']['code'] == created['code']
    assert updated.json()['data']['keywords'] == ['展览']
    assert updated.json()['data']['recent_filter'] == '一天内'

    listed = client.get('/api/v1/settings/cities', headers=headers).json()['data'][0]
    assert listed['name'] == '上海市'
    assert listed['keywords'] == ['展览']
    assert client.post('/api/v1/settings/bloggers', json={'platform_user_id': 'u1', 'username': '博主', 'profile_url': 'https://example.com/u1', 'city_codes': [created['code']]}, headers=headers).status_code == 201
    assert client.delete(f"/api/v1/settings/cities/{city.json()['data']['id']}", headers=headers).status_code == 200


def test_city_rejects_unsupported_recent_filter(client: TestClient, headers):
    response = client.post('/api/v1/settings/cities', json={
        'name': '宁波',
        'keywords': ['周末活动'],
        'recent_filter': '三天内',
    }, headers=headers)
    assert response.status_code == 422


def test_tasks_list_logs_and_reject_concurrent_trigger(client: TestClient, db_session: Session, headers):
    running = CrawlTask(type='keyword', status='RUNNING', params={})
    db_session.add(running); db_session.flush(); db_session.add(TaskLog(task_id=running.id, level='INFO', message='running')); db_session.commit()
    assert client.get('/api/v1/tasks', headers=headers).json()['pagination']['total'] == 1
    assert client.get(f'/api/v1/tasks/{running.id}/logs', headers=headers).json()['data'][0]['message'] == 'running'


def test_dashboard_task_uses_configured_city_keywords_time_and_bloggers(client: TestClient, db_session: Session, headers, monkeypatch):
    city = client.post('/api/v1/settings/cities', json={'name': '上海', 'keywords': ['活动', '展览'], 'recent_filter': '一周内'}, headers=headers).json()['data']
    blogger = client.post('/api/v1/settings/bloggers', json={'platform_user_id': 'u1', 'username': '博主', 'profile_url': 'https://example.com/u1', 'city_codes': [city['code']]}, headers=headers).json()['data']
    monkeypatch.setattr('app.tasks.crawl_task.run_crawl.delay', lambda *_: None)
    invalid = client.post('/api/v1/tasks/crawl', json={'type': 'mixed', 'city': city['code'], 'keywords': ['不存在'], 'recent_filter': '一天内', 'blogger_ids': []}, headers=headers)
    assert invalid.status_code == 422
    response = client.post('/api/v1/tasks/crawl', json={'type': 'mixed', 'city': city['code'], 'keywords': ['活动'], 'recent_filter': '一天内', 'blogger_ids': [blogger['id']]}, headers=headers)
    assert response.status_code == 202
    assert response.json()['data']['params'] == {'type': 'mixed', 'city': city['code'], 'keywords': ['活动'], 'recent_filter': '一天内', 'blogger_ids': [blogger['id']]}


def test_failed_task_restarts_with_same_id_and_preserves_completed_progress(client: TestClient, db_session: Session, headers, monkeypatch):
    city = client.post('/api/v1/settings/cities', json={'name': '宁波', 'keywords': ['活动'], 'recent_filter': '一周内'}, headers=headers).json()['data']
    task = CrawlTask(type='mixed', status='FAILED', params={'type': 'mixed', 'city': city['code'], 'keywords': ['活动'], 'recent_filter': '一周内', 'blogger_ids': []}, total_notes=113, downloaded_notes=5, ocr_notes=5, extracted_notes=5, success_notes=5, failed_notes=1, error_message='bad date')
    db_session.add(task); db_session.commit(); queued=[]
    monkeypatch.setattr('app.tasks.crawl_task.run_crawl.delay', lambda task_id, run_token: queued.append((task_id, run_token)))

    response = client.post(f'/api/v1/tasks/{task.id}/restart', headers=headers)

    assert response.status_code == 202
    assert response.json()['data']['id'] == task.id
    db_session.refresh(task)
    assert task.status == 'PENDING'
    assert task.success_notes == 5
    assert task.failed_notes == 0
    assert task.error_message is None
    assert queued == [(task.id, task.run_token)]


def test_task_stop_transitions_are_safe_and_idempotent(client: TestClient, db_session: Session, headers):
    pending = CrawlTask(type='mixed', status='PENDING', params={})
    running = CrawlTask(type='mixed', status='RUNNING', params={})
    completed = CrawlTask(type='mixed', status='COMPLETED', params={})
    failed = CrawlTask(type='mixed', status='FAILED', params={})
    db_session.add_all([pending, running, completed, failed]); db_session.commit()

    pending_response = client.post(f'/api/v1/tasks/{pending.id}/stop', headers=headers)
    running_response = client.post(f'/api/v1/tasks/{running.id}/stop', headers=headers)
    repeated_response = client.post(f'/api/v1/tasks/{running.id}/stop', headers=headers)
    completed_response = client.post(f'/api/v1/tasks/{completed.id}/stop', headers=headers)
    failed_response = client.post(f'/api/v1/tasks/{failed.id}/stop', headers=headers)
    # STOPPED 状态再次 stop 应幂等返回 202
    stopped_id = pending.id
    stopped_response = client.post(f'/api/v1/tasks/{stopped_id}/stop', headers=headers)

    assert pending_response.status_code == 202
    assert pending_response.json()['data']['status'] == 'STOPPED'
    assert running_response.status_code == 202
    assert running_response.json()['data']['status'] == 'STOP_REQUESTED'
    assert repeated_response.status_code == 202
    assert repeated_response.json()['data']['status'] == 'STOP_REQUESTED'
    assert completed_response.status_code == 202
    assert completed_response.json()['data']['status'] == 'COMPLETED'
    assert failed_response.status_code == 202
    assert failed_response.json()['data']['status'] == 'STOP_REQUESTED'
    assert stopped_response.status_code == 202
    assert client.post('/api/v1/tasks/99999/stop', headers=headers).status_code == 404


def test_stopped_task_can_restart_with_same_id(client: TestClient, db_session: Session, headers, monkeypatch):
    city = client.post('/api/v1/settings/cities', json={'name': '宁波', 'keywords': ['活动'], 'recent_filter': '一周内'}, headers=headers).json()['data']
    task = CrawlTask(type='mixed', status='STOPPED', params={'type': 'mixed', 'city': city['code'], 'keywords': ['活动'], 'recent_filter': '一周内', 'blogger_ids': []}, total_notes=10, extracted_notes=3, success_notes=3)
    db_session.add(task); db_session.commit(); queued = []
    monkeypatch.setattr('app.tasks.crawl_task.run_crawl.delay', lambda task_id, run_token: queued.append((task_id, run_token)))

    response = client.post(f'/api/v1/tasks/{task.id}/restart', headers=headers)

    assert response.status_code == 202
    assert response.json()['data']['id'] == task.id
    assert response.json()['data']['status'] == 'PENDING'
    assert queued == [(task.id, task.run_token)]


def test_paused_task_stays_paused_when_login_check_fails(client: TestClient, db_session: Session, headers, monkeypatch):
    city = client.post('/api/v1/settings/cities', json={'name': '宁波', 'keywords': ['活动'], 'recent_filter': '一周内'}, headers=headers).json()['data']
    task = CrawlTask(type='mixed', status='PAUSED', params={'type': 'mixed', 'city': city['code'], 'keywords': ['活动'], 'recent_filter': '一周内', 'blogger_ids': []}, total_notes=100, downloaded_notes=19, ocr_notes=19, extracted_notes=19, success_notes=19, error_message='请登录')
    db_session.add(task); db_session.commit()

    def require_login(_self):
        raise AuthenticationRequired('请登录')

    monkeypatch.setattr('app.api.v1.tasks.OpenCLIAdapter.check_login', require_login)

    response = client.post(f'/api/v1/tasks/{task.id}/restart', headers=headers)

    assert response.status_code == 409
    assert response.json()['message'] == 'AUTH_REQUIRED'
    db_session.refresh(task)
    assert task.status == 'PAUSED'
    assert task.downloaded_notes == 19


def test_paused_task_reuses_id_started_at_and_progress_after_login(client: TestClient, db_session: Session, headers, monkeypatch):
    city = client.post('/api/v1/settings/cities', json={'name': '宁波', 'keywords': ['活动'], 'recent_filter': '一周内'}, headers=headers).json()['data']
    started_at = datetime(2026, 7, 17, 1, tzinfo=timezone.utc)
    task = CrawlTask(type='mixed', status='PAUSED', params={'type': 'mixed', 'city': city['code'], 'keywords': ['活动'], 'recent_filter': '一周内', 'blogger_ids': []}, total_notes=100, downloaded_notes=19, ocr_notes=19, extracted_notes=19, success_notes=19, failed_notes=2, started_at=started_at, error_message='请登录')
    db_session.add(task); db_session.commit(); queued = []
    monkeypatch.setattr('app.api.v1.tasks.OpenCLIAdapter.check_login', lambda _self: {'logged_in': True})
    monkeypatch.setattr('app.tasks.crawl_task.run_crawl.delay', lambda task_id, run_token: queued.append((task_id, run_token)))

    response = client.post(f'/api/v1/tasks/{task.id}/restart', headers=headers)

    assert response.status_code == 202
    assert response.json()['data']['id'] == task.id
    assert response.json()['data']['downloaded_notes'] == 19
    assert response.json()['data']['failed_notes'] == 2
    db_session.refresh(task)
    assert task.started_at == started_at.replace(tzinfo=None)
    assert queued == [(task.id, task.run_token)]


def test_open_login_endpoint_returns_configured_url(client: TestClient, headers, monkeypatch):
    monkeypatch.setattr('app.api.v1.settings.open_xhs_login', lambda _settings: 'https://www.xiaohongshu.com/explore')

    response = client.post('/api/v1/settings/opencli/open-login', headers=headers)

    assert response.status_code == 200
    assert response.json()['data']['url'] == 'https://www.xiaohongshu.com/explore'


def test_dashboard_summary_contains_latest_task_progress(client: TestClient, db_session: Session, headers):
    task = CrawlTask(type='mixed', status='RUNNING', params={}, total_notes=20, downloaded_notes=8, ocr_notes=7, extracted_notes=5, success_notes=5, failed_notes=1, skipped_notes=4, current_stage='OCR', current_note='周末活动')
    db_session.add(task); db_session.commit()

    latest = client.get('/api/v1/dashboard/summary', headers=headers).json()['data']['last_task']

    assert latest == pytest.approx({
        'id': task.id, 'status': 'RUNNING', 'total_notes': 20, 'downloaded_notes': 8,
        'ocr_notes': 7, 'extracted_notes': 5, 'success_notes': 5, 'failed_notes': 1,
        'skipped_notes': 4, 'skipped_activities': 0,
        'current_stage': 'OCR', 'current_note': '周末活动', 'error_message': None,
        'progress_percent': 50.0,
    })



def activity(name):
    return Activity(name=name, city_code='shanghai', start_time=datetime(2025, 7, 20, tzinfo=timezone.utc), location='徐汇', type='演出', status='APPROVED')


def test_duplicate_list_merge_and_ignore(client: TestClient, db_session: Session, headers):
    a = Note(task_id=1, platform_note_id='note-a', title='推文A', content='', source_url='https://xhs/a', city_code='shanghai', status='PROCESSED', raw_data={})
    b = Note(task_id=1, platform_note_id='note-b', title='推文B', content='', source_url='https://xhs/b', city_code='shanghai', status='PROCESSED', raw_data={})
    c = Note(task_id=1, platform_note_id='note-c', title='推文C', content='', source_url='https://xhs/c', city_code='shanghai', status='PROCESSED', raw_data={})
    db_session.add_all([a, b, c]); db_session.flush()
    first = NoteDuplicateCandidate(note_a_id=a.id, note_b_id=b.id, similarity=.82, matched_fields=['title'])
    second = NoteDuplicateCandidate(note_a_id=a.id, note_b_id=c.id, similarity=.6, matched_fields=['title'])
    db_session.add_all([first, second]); db_session.commit()
    assert client.get('/api/v1/duplicates', headers=headers).json()['pagination']['total'] == 2
    assert client.post(f'/api/v1/duplicates/{first.id}/merge', json={'keep': 'a'}, headers=headers).status_code == 200
    db_session.refresh(a); db_session.refresh(b)
    assert a.review_status == 'PENDING'
    assert b.review_status == 'MERGED'
    pending = client.get('/api/v1/duplicates', headers=headers).json()
    assert pending['pagination']['total'] == 1
    assert pending['data']['items'][0]['id'] == second.id
    assert client.post(f'/api/v1/duplicates/{second.id}/ignore', headers=headers).status_code == 200
