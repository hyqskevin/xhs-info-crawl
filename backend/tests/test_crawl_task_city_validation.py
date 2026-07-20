"""入库硬校验：city_code 必须存在于 cities 表，否则跳过 + ERROR 日志。"""

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from sqlalchemy.orm import Session

from app.models.activity import Activity
from app.models.config import City
from app.models.task import CrawlTask, TaskLog
from app.services.crawl_city_guard import assert_city_code_exists
from app.tasks.crawl_task import process_note


def test_assert_city_code_exists_returns_true_for_known_code(db_session: Session):
    db_session.add(City(name="上海", code="city-99f1e469", enabled=True))
    db_session.commit()
    assert assert_city_code_exists(db_session, "city-99f1e469") is True


def test_assert_city_code_exists_returns_false_for_unknown_code(db_session: Session):
    db_session.add(City(name="上海", code="city-99f1e469", enabled=True))
    db_session.commit()
    assert assert_city_code_exists(db_session, "火星") is False


def test_assert_city_code_exists_returns_false_for_empty_string(db_session: Session):
    db_session.add(City(name="上海", code="city-99f1e469", enabled=True))
    db_session.commit()
    assert assert_city_code_exists(db_session, "") is False


def test_process_note_skips_when_city_code_unknown(db_session: Session, tmp_path):
    """防御：城市 code 不在 cities 表时，process_note 直接跳过并记 ERROR 日志。"""
    task = CrawlTask(type="mixed", status="RUNNING", params={"city": "火星"})
    db_session.add(task)
    db_session.flush()
    settings = SimpleNamespace(
        pipeline_stage_max_retries=1,
        pipeline_stage_retry_delay_seconds=0,
        activity_future_window_days=60,
        celery_timezone="Asia/Shanghai",
        archive_dir=tmp_path,
    )
    adapter = SimpleNamespace(
        note=lambda url: {"content": "正文", "title": "标题"},
        download=lambda url, out_dir: [],
    )
    item = {"url": "https://www.xiaohongshu.com/explore/abc", "title": "标题"}

    process_note(db_session, task, task.run_token, "火星", item, adapter, settings)

    logs = db_session.query(TaskLog).filter(TaskLog.task_id == task.id).all()
    messages = [log.message for log in logs]
    assert any("city_code 不在 cities 表" in m and "'火星'" in m for m in messages), messages
    assert task.skipped_activities == 1
