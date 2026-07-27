"""活动级 duplicate_candidates 停写 + 存量清理（spec: 2026-07-27-stop-activity-duplicate-candidates-design.md，TODO#5 方案 A）。

先红后绿：停写前 dedup.create_duplicate_candidates 存在且被 crawl_task 引用。
"""
import ast
from pathlib import Path

from sqlalchemy import func, select

from app.models.duplicate import DuplicateCandidate
from app.services import dedup

BACKEND_ROOT = Path(__file__).resolve().parent.parent


def test_dedup_no_longer_creates_activity_candidates() -> None:
    assert not hasattr(dedup, "create_duplicate_candidates"), "活动级候选写入函数应已删除"
    assert hasattr(dedup, "create_note_duplicate_candidates"), "推文级候选必须保留"


def test_crawl_task_does_not_reference_activity_candidates() -> None:
    tree = ast.parse((BACKEND_ROOT / "app/tasks/crawl_task.py").read_text(encoding="utf-8"))
    referenced = {
        node.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Name)
    } | {
        node.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Attribute)
    }
    assert "create_duplicate_candidates" not in referenced


def test_cleanup_script_zeroes_duplicate_candidates_idempotent(db_session) -> None:
    from scripts.cleanup_duplicate_candidates import run_cleanup

    for pair in ((1, 2), (3, 4)):
        db_session.add(DuplicateCandidate(
            activity_a_id=pair[0], activity_b_id=pair[1],
            similarity=0.8, matched_fields=["city"], status="pending",
        ))
    db_session.commit()
    before = db_session.scalar(select(func.count()).select_from(DuplicateCandidate))
    assert before == 2

    stats = run_cleanup(db_session)
    assert stats["deleted"] == 2
    assert db_session.scalar(select(func.count()).select_from(DuplicateCandidate)) == 0

    again = run_cleanup(db_session)
    assert again["deleted"] == 0
