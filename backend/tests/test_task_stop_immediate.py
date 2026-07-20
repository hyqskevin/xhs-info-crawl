"""stop_task 接口立即停当前子进程：

- 用户点"停止抓取" → 后端 kill 当前正在跑的 note 子进程
- RUNNING 任务状态先变 STOP_REQUESTED，worker 检测到后再变为 STOPPED
- PENDING 任务状态直接变 STOPPED
- worker 进程不退出
"""

from unittest.mock import patch
import signal

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.config import Blogger
from app.models.task import CrawlTask, TaskLog


def _create_running_task(db_session: Session) -> CrawlTask:
    """创建一个 RUNNING 任务用于测试。"""
    t = CrawlTask(
        type="mixed",
        status="RUNNING",
        params={"city": "nb", "keywords": [], "blogger_ids": []},
    )
    db_session.add(t)
    db_session.commit()
    db_session.refresh(t)
    return t


def _create_pending_task(db_session: Session) -> CrawlTask:
    """创建一个 PENDING 任务用于测试。"""
    t = CrawlTask(
        type="mixed",
        status="PENDING",
        params={"city": "nb", "keywords": [], "blogger_ids": []},
    )
    db_session.add(t)
    db_session.commit()
    db_session.refresh(t)
    return t


def _auth():
    from app.core.security import create_access_token
    return {"Authorization": f"Bearer {create_access_token({'sub': 'admin', 'role': 'admin'})}"}


def test_stop_kills_registered_child_pid(client: TestClient, db_session: Session):
    """stop_task 应该向 registry 中记录的子进程 PID 发 SIGTERM。"""
    task = _create_running_task(db_session)

    import subprocess
    proc = subprocess.Popen(["sleep", "60"])
    from app.services.task_registry import register, unregister
    register(task.id, proc.pid, run_token=task.run_token)

    try:
        response = client.post(f"/api/v1/tasks/{task.id}/stop", headers=_auth())
        assert response.status_code == 202, response.text

        proc.wait(timeout=10)
        assert proc.returncode is not None
        assert proc.returncode != 0
    finally:
        unregister(task.id, run_token=task.run_token)
        if proc.poll() is None:
            proc.kill()


def test_stop_running_task_sets_stop_requested(client: TestClient, db_session: Session):
    """RUNNING 任务调用 stop 后，状态应变为 STOP_REQUESTED（等待 worker 确认）。"""
    task = _create_running_task(db_session)

    response = client.post(f"/api/v1/tasks/{task.id}/stop", headers=_auth())
    assert response.status_code == 202

    db_session.refresh(task)
    assert task.status == "STOP_REQUESTED"


def test_stop_pending_task_sets_stopped(client: TestClient, db_session: Session):
    """PENDING 任务调用 stop 后，状态应立即变为 STOPPED。"""
    task = _create_pending_task(db_session)

    response = client.post(f"/api/v1/tasks/{task.id}/stop", headers=_auth())
    assert response.status_code == 202

    db_session.refresh(task)
    assert task.status == "STOPPED"
    assert task.finished_at is not None


def test_stop_writes_log_entry(client: TestClient, db_session: Session):
    """stop 接口应该写 '已请求停止抓取' 日志。"""
    task = _create_running_task(db_session)

    client.post(f"/api/v1/tasks/{task.id}/stop", headers=_auth())

    logs = db_session.query(TaskLog).filter(TaskLog.task_id == task.id).all()
    messages = [l.message for l in logs]
    assert any("已请求停止抓取" in m for m in messages)


def test_stop_handles_no_registered_pid(client: TestClient, db_session: Session):
    """如果 registry 没记录（任务还没启动或已退出），stop 应正常返回。"""
    task = _create_running_task(db_session)

    response = client.post(f"/api/v1/tasks/{task.id}/stop", headers=_auth())
    assert response.status_code == 202

    db_session.refresh(task)
    assert task.status == "STOP_REQUESTED"


def test_stop_404_when_task_not_found(client: TestClient):
    response = client.post("/api/v1/tasks/99999/stop", headers=_auth())
    assert response.status_code == 404


def test_stop_idempotent_when_already_stopped(client: TestClient, db_session: Session):
    """STOPPED 状态再 stop 应幂等返回 202。"""
    task = _create_running_task(db_session)
    task.status = "STOPPED"
    db_session.commit()

    response = client.post(f"/api/v1/tasks/{task.id}/stop", headers=_auth())
    assert response.status_code == 202


def test_stop_idempotent_when_stop_requested(client: TestClient, db_session: Session):
    """STOP_REQUESTED 状态再 stop 应幂等返回 202。"""
    task = _create_running_task(db_session)
    task.status = "STOP_REQUESTED"
    db_session.commit()

    response = client.post(f"/api/v1/tasks/{task.id}/stop", headers=_auth())
    assert response.status_code == 202
