"""批量删除抓取任务（POST /tasks/batch/delete）。

校验：
- 一次删除多条：返回 deleted_count 与 deleted_ids 列表；
- 包含不存在的 id：返回 422 并说明哪个 id 不存在；
- ids 为空 / 超过 100：返回 422。
"""
from datetime import datetime, timezone

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.security import create_access_token
from app.models.task import CrawlTask, TaskLog


def _auth() -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token({'sub': 'admin', 'role': 'admin'})}"}


def _seed_tasks(db: Session, count: int) -> list[CrawlTask]:
    rows = []
    for i in range(count):
        task = CrawlTask(
            type='mixed',
            status='STOPPED',
            params={'city': 'nb', 'keywords': [], 'blogger_ids': []},
            run_token=f'token-{i}',
            total_notes=0,
        )
        db.add(task)
        rows.append(task)
    db.commit()
    for row in rows:
        db.refresh(row)
    return rows


def test_batch_delete_removes_all_specified_tasks(client: TestClient, db_session: Session) -> None:
    seeded = _seed_tasks(db_session, 3)
    db_session.add(TaskLog(task_id=seeded[0].id, level='INFO', message='hello'))

    response = client.request('DELETE', '/api/v1/tasks/batch', json={'ids': [seeded[0].id, seeded[1].id]}, headers=_auth())

    assert response.status_code == 200
    payload = response.json()['data']
    assert payload['deleted_count'] == 2
    assert set(payload['deleted_ids']) == {seeded[0].id, seeded[1].id}
    remaining = db_session.scalars(__import__('sqlalchemy').select(CrawlTask)).all()
    remaining_ids = [task.id for task in remaining]
    assert seeded[2].id in remaining_ids
    assert seeded[0].id not in remaining_ids
    assert seeded[1].id not in remaining_ids


def test_batch_delete_with_unknown_id_returns_422(client: TestClient, db_session: Session) -> None:
    seeded = _seed_tasks(db_session, 1)

    response = client.request(
        'DELETE',
        '/api/v1/tasks/batch',
        json={'ids': [seeded[0].id, 999_999]},
        headers=_auth(),
    )

    assert response.status_code == 422
    assert '999999' in response.text or '不存在' in response.text


def test_batch_delete_rejects_empty_list(client: TestClient, db_session: Session) -> None:
    response = client.request('DELETE', '/api/v1/tasks/batch', json={'ids': []}, headers=_auth())
    assert response.status_code == 422
    assert '请选择' in response.text or 'at least 1' in response.text or 'ids' in response.text


def test_batch_delete_rejects_over_limit(client: TestClient, db_session: Session) -> None:
    response = client.request(
        'DELETE',
        '/api/v1/tasks/batch',
        json={'ids': list(range(1, 102))},
        headers=_auth(),
    )
    assert response.status_code == 422
