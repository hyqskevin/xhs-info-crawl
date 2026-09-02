"""死代码清理静态断言（spec: 2026-07-27-dead-code-cleanup-design.md，TODO#6）。

先红后绿：清理前这些断言应失败，清理后通过。
"""
import ast
import importlib
from pathlib import Path

import pytest

BACKEND_ROOT = Path(__file__).resolve().parent.parent


def test_crawler_exposes_only_exceptions_and_verification() -> None:
    from app.services import crawler

    for gone in (
        "ScrollPolicy", "collect_with_scroll", "check_login",
        "filter_recent_notes", "search_recent_notes", "map_opencli_error", "search_notes",
    ):
        assert not hasattr(crawler, gone), f"crawler.{gone} 应已删除"
    for kept in (
        "OpenCLIError", "OpenCLITimeout", "AuthenticationRequired",
        "VerificationRequired", "is_verification_required",
    ):
        assert hasattr(crawler, kept), f"crawler.{kept} 必须保留（生产在用）"


def test_pipeline_drops_process_with_isolation() -> None:
    from app.services import pipeline

    assert not hasattr(pipeline, "process_with_isolation")
    for kept in ("title_matches_keywords", "run_stage", "deduplicate_results"):
        assert hasattr(pipeline, kept)


def test_task_lock_module_removed() -> None:
    with pytest.raises(ModuleNotFoundError):
        importlib.import_module("app.services.task_lock")


def test_report_exposes_only_note_level_exports() -> None:
    from app.services import report

    for gone in (
        "visible_activities",
        "generate_markdown",
        "generate_xlsx",
        # P2-4 (2026-09-02 audit batch 3): 旧版 generate_note_xlsx 无封面, 无生产调用方
        "generate_note_xlsx",
    ):
        assert not hasattr(report, gone), f"report.{gone} 应已删除"
    # format_activity_markdown 被 generate_note_markdown 引用, 必须保留
    # generate_note_xlsx_with_cover 是新版 (2026-08-18 用户反馈加封面图), 生产在用
    for kept in (
        "generate_note_markdown",
        "generate_note_xlsx_with_cover",
        "format_activity_markdown",
    ):
        assert hasattr(report, kept), f"report.{kept} 必须保留（生产在用）"


def test_reports_api_drops_select_activities() -> None:
    from app.api.v1 import reports

    assert not hasattr(reports, "select_activities")


def _imported_names(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.asname or alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            names.update(alias.asname or alias.name for alias in node.names)
    return names


@pytest.mark.parametrize("rel_path,forbidden", [
    ("app/tasks/crawl_task.py", {"Keyword", "ActivityWindow"}),
    ("app/api/v1/poster_tasks.py", {"City"}),
    ("app/api/v1/reports.py", {"BytesIO", "func"}),
    ("app/services/poster_renderer.py", {"json"}),
])
def test_unused_imports_removed(rel_path: str, forbidden: set[str]) -> None:
    names = _imported_names(BACKEND_ROOT / rel_path)
    assert not (names & forbidden), f"{rel_path} 仍导入未使用符号：{names & forbidden}"
