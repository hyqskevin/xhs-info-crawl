from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.security import create_access_token
from app.models.activity import Activity
from app.models.duplicate import DuplicateCandidate
from app.models.task import CrawlTask, TaskLog


@pytest.fixture
def headers():
    return {"Authorization": f"Bearer {create_access_token({'sub': 'admin', 'role': 'admin'})}"}


def test_city_keyword_blogger_crud(client: TestClient, headers):
    city = client.post('/api/v1/settings/cities', json={'name': '上海', 'code': 'shanghai'}, headers=headers)
    assert city.status_code == 201
    assert client.get('/api/v1/settings/cities', headers=headers).json()['data'][0]['code'] == 'shanghai'
    assert client.post('/api/v1/settings/keywords', json={'word': '周末活动', 'city_code': 'shanghai'}, headers=headers).status_code == 201
    assert client.post('/api/v1/settings/bloggers', json={'platform_user_id': 'u1', 'username': '博主', 'profile_url': 'https://example.com/u1', 'city_code': 'shanghai'}, headers=headers).status_code == 201
    assert client.delete(f"/api/v1/settings/cities/{city.json()['data']['id']}", headers=headers).status_code == 200


def test_tasks_list_logs_and_reject_concurrent_trigger(client: TestClient, db_session: Session, headers):
    running = CrawlTask(type='keyword', status='RUNNING', params={})
    db_session.add(running); db_session.flush(); db_session.add(TaskLog(task_id=running.id, level='INFO', message='running')); db_session.commit()
    assert client.post('/api/v1/tasks/crawl', json={'type': 'keyword', 'cities': ['shanghai'], 'keywords': ['活动']}, headers=headers).status_code == 409
    assert client.get('/api/v1/tasks', headers=headers).json()['pagination']['total'] == 1
    assert client.get(f'/api/v1/tasks/{running.id}/logs', headers=headers).json()['data'][0]['message'] == 'running'


def test_manual_task_created_when_idle(client: TestClient, headers):
    response = client.post('/api/v1/tasks/crawl', json={'type': 'keyword', 'cities': ['shanghai'], 'keywords': ['活动']}, headers=headers)
    assert response.status_code == 202 and response.json()['data']['status'] == 'PENDING'


def activity(name):
    return Activity(name=name, city_code='shanghai', start_time=datetime(2025, 7, 20, tzinfo=timezone.utc), location='徐汇', type='演出', status='APPROVED')


def test_duplicate_list_merge_and_ignore(client: TestClient, db_session: Session, headers):
    a, b = activity('活动A'), activity('活动B'); db_session.add_all([a, b]); db_session.flush()
    first = DuplicateCandidate(activity_a_id=a.id, activity_b_id=b.id, similarity=.82, matched_fields=['city', 'date'])
    second = DuplicateCandidate(activity_a_id=a.id, activity_b_id=b.id, similarity=.6, matched_fields=['city'])
    db_session.add_all([first, second]); db_session.commit()
    assert client.get('/api/v1/duplicates', headers=headers).json()['pagination']['total'] == 2
    assert client.post(f'/api/v1/duplicates/{first.id}/merge', json={'keep': 'a'}, headers=headers).status_code == 200
    assert client.post(f'/api/v1/duplicates/{second.id}/ignore', headers=headers).status_code == 200
