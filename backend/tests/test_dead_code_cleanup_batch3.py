"""P2-2/3/4 死代码清理断言（spec: 2026-09-02-audit-batch-3-redundant-design.md §P2-2/3/4）。

审计批次 3 发现以下函数已无生产调用方,只剩测试覆盖,应当删除:

- app.services.dedup: similarity_score / classify_similarity / merge_activities
  - 仅 test_pipeline_services.py + test_activity_status_removal.py 使用
- app.services.archive.resolve_storage_path
  - 仅 test_multi_activity_archive.py 使用
- app.services.report.strip_report_images
  - 仅 test_reports.py 使用
- app.services.report.generate_note_xlsx(旧版,无封面)
  - 仅 test_note_weekly_reports.py + test_dead_code_cleanup.py 使用
  - 注意:generate_note_xlsx_with_cover 是新版生产在用,必须保留

TDD 顺序:
1. RED:本文件先断言「这些函数不应再存在」,因未删除,RED 全失败
2. GREEN:删源 + 删依赖它们的测试 → 本文件 GREEN

不动:
- record_initial_password / status_server.get_initial_password(P2-5/11,见 launcher/tests)
- test_dead_code_cleanup.py 仍断言 generate_note_xlsx 在 keep 列表 → 本 commit 同步改
"""
import pytest


def test_dedup_drops_legacy_similarity_helpers() -> None:
    """dedup 模块不再暴露 similarity_score / classify_similarity / merge_activities。

    这三个函数在 audit 批次 3 之前已无生产调用方,只剩测试。删它们连带删测试。
    """
    from app.services import dedup

    for gone in ("similarity_score", "classify_similarity", "merge_activities"):
        assert not hasattr(dedup, gone), f"dedup.{gone} 应已删除(无生产调用方)"


def test_archive_drops_resolve_storage_path() -> None:
    """archive 模块不再暴露 resolve_storage_path(只剩 test_multi_activity_archive 调用)。"""
    from app.services import archive

    assert not hasattr(archive, "resolve_storage_path"), (
        "archive.resolve_storage_path 应已删除;"
        " archive_task_folder / archive_task_result / write_activity_exports 才是生产在用"
    )


def test_report_drops_strip_report_images() -> None:
    """report 模块不再暴露 strip_report_images(只剩 test_reports 调用)。"""
    from app.services import report

    assert not hasattr(report, "strip_report_images"), (
        "report.strip_report_images 应已删除;前端/后端无任何生产调用方"
    )


def test_report_drops_legacy_generate_note_xlsx() -> None:
    """report 模块不再暴露旧版 generate_note_xlsx(无封面)。

    新版 generate_note_xlsx_with_cover 在 production,必须保留。
    旧版只剩 test_note_weekly_reports.py:47 + test_dead_code_cleanup.py:48。
    """
    from app.services import report

    assert not hasattr(report, "generate_note_xlsx"), (
        "report.generate_note_xlsx(旧版无封面)应已删除;新版 generate_note_xlsx_with_cover 保留"
    )


def test_report_keeps_covered_xlsx_and_markdown() -> None:
    """反向断言:删除旧版时不要误伤新版。"""
    from app.services import report

    for kept in (
        "generate_note_markdown",
        "generate_note_xlsx_with_cover",
        "build_report_zip",
    ):
        assert hasattr(report, kept), f"report.{kept} 必须保留(生产在用)"