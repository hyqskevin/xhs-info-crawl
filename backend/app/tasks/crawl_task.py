from datetime import datetime, timezone
import shutil

from sqlalchemy import delete, select, update

from app.core.config import get_settings
from app.core.database import SessionLocal
from app.models.activity import Activity
from app.models.config import Blogger, City, Keyword
from app.models.note import Note, NoteImage
from app.models.task import CrawlTask, TaskLog
from app.services.archive import archive_task_folder, archive_task_result
from app.services.activity_window import ActivityWindow
from app.services.crawler import AuthenticationRequired, VerificationRequired
from app.services.browser_launcher import open_xhs_login
from app.services.crawl_city_guard import assert_city_code_exists
from app.services.crawl_scope import resolve_crawl_scope
from app.services.dedup import create_duplicate_candidates, create_note_duplicate_candidates
from app.services.extraction import extract_activities
from app.services.minimax import MiniMaxClient
from app.services.note_identity import extract_platform_note_id
from app.services.ocr import OCRService
from app.services.note_id_published_at import note_id_published_at
from app.services.published_at import extract_published_at
from app.services.opencli_adapter import OpenCLIAdapter
from app.services.paddleocr_adapter import PaddleOCREngine
from app.services.pipeline import deduplicate_results, run_stage, title_matches_keywords
from app.tasks.celery_app import celery_app


class ExecutionStopped(Exception):
    pass


class ExecutionSuperseded(Exception):
    pass


def assert_execution_active(db, task_id: int, run_token: str) -> None:
    row = db.execute(
        select(CrawlTask.status, CrawlTask.run_token).where(CrawlTask.id == task_id)
    ).one_or_none()
    if row is None or row.run_token != run_token:
        raise ExecutionSuperseded()
    if row.status in {"STOP_REQUESTED", "STOPPED"}:
        raise ExecutionStopped()
    if row.status != "RUNNING":
        raise ExecutionSuperseded()


def log(db, task_id: int, level: str, message: str) -> None:
    db.add(TaskLog(task_id=task_id, level=level, message=message))
    db.commit()


def set_progress(db, task: CrawlTask, run_token: str, stage: str, current_note: str | None = None) -> None:
    changed = db.execute(
        update(CrawlTask)
        .where(
            CrawlTask.id == task.id,
            CrawlTask.run_token == run_token,
            CrawlTask.status == "RUNNING",
        )
        .values(current_stage=stage, current_note=current_note)
    )
    db.commit()
    if changed.rowcount != 1:
        assert_execution_active(db, task.id, run_token)
    db.refresh(task)


def cleanup_incomplete_note(db, source_url: str) -> None:
    platform_note_id = extract_platform_note_id(source_url)
    note = db.scalar(
        select(Note).where(
            Note.platform_note_id == platform_note_id if platform_note_id else Note.source_url == source_url
        )
    )
    if note is None or note.status == "PROCESSED":
        return
    db.execute(delete(Activity).where(Activity.note_id == note.id))
    db.execute(delete(NoteImage).where(NoteImage.note_id == note.id))
    db.delete(note)
    db.commit()


def prepare_existing_note(db, source_url: str) -> bool:
    """Return True when a note is already complete; remove partial legacy rows otherwise."""
    platform_note_id = extract_platform_note_id(source_url)
    note = db.scalar(
        select(Note).where(
            Note.platform_note_id == platform_note_id if platform_note_id else Note.source_url == source_url
        )
    )
    if note is None:
        return False
    has_activity = db.scalar(select(Activity.id).where(Activity.note_id == note.id).limit(1)) is not None
    if note.status == "PROCESSED" or has_activity:
        changed = False
        if note.source_url != source_url:
            note.source_url = source_url
            changed = True
        if note.status != "PROCESSED":
            note.status = "PROCESSED"
            changed = True
        if changed:
            db.commit()
        return True
    cleanup_incomplete_note(db, source_url)
    return False


def finish_stop_if_requested(db, task_id: int, run_token: str) -> bool:
    current = db.get(CrawlTask, task_id)
    db.refresh(current)
    if current.run_token != run_token:
        raise ExecutionSuperseded()
    if current.status not in ("STOP_REQUESTED", "STOPPED"):
        return False
    if current.status != "STOPPED":
        current.status = "STOPPED"
        current.current_stage = None
        current.current_note = None
        current.finished_at = datetime.now(timezone.utc)
        db.commit()
        log(db, current.id, "INFO", "任务已安全停止")
    return True


def process_note(db, task: CrawlTask, run_token: str, city: str, item: dict, adapter: OpenCLIAdapter, settings) -> bool:
    assert_execution_active(db, task.id, run_token)
    note_url = (item.get("url") or "").strip()
    if not note_url:
        log(db, task.id, "WARNING", f"跳过笔记：url 为空 title={item.get('title', '')!r}")
        return False
    if not assert_city_code_exists(db, city):
        log(db, task.id, "ERROR", f"city_code 不在 cities 表：{city!r}，跳过该笔记 url={note_url}")
        task.skipped_activities += 1
        return False
    if prepare_existing_note(db, note_url):
        return False

    attempts = settings.pipeline_stage_max_retries
    delay = settings.pipeline_stage_retry_delay_seconds
    started_at = task.started_at or datetime.now(timezone.utc)
    set_progress(db, task, run_token, "DOWNLOADING", item.get("title") or note_url)
    detail = run_stage(lambda: adapter.note(note_url), attempts, delay)
    assert_execution_active(db, task.id, run_token)
    # 优先级 1：基于 note ID（雪花算法）反推时间戳，精度到秒，最可靠。
    # 优先级 2：DOM 文本解析（"3天前" / "07-19" 等）。
    # 优先级 3：started_at 兜底。
    snowflake_at = note_id_published_at(note_url)
    dom_at = extract_published_at(detail, fallback_now=started_at)
    if snowflake_at is not None:
        published_at = snowflake_at
    elif dom_at is not None:
        published_at = dom_at
    else:
        published_at = None
    if published_at is None:
        log(db, task.id, "INFO", f"未解析真实发布时间：{item.get('title') or note_url}")
    note = Note(
        task_id=task.id,
        platform_note_id=extract_platform_note_id(note_url) or note_url.split("/")[-1].split("?")[0],
        title=item.get("title", ""),
        content=detail.get("content", ""),
        source_url=note_url,
        city_code=city,
        status="DOWNLOADED",
        published_at=published_at,
        raw_data=detail,
    )
    db.add(note)
    db.flush()
    folder = archive_task_folder(settings.archive_dir, started_at, task.id)
    download_dir = folder / ".downloads" / note.platform_note_id
    images = run_stage(lambda: adapter.download(note_url, download_dir), attempts, delay)
    assert_execution_active(db, task.id, run_token)
    task.downloaded_notes += 1
    db.commit()

    set_progress(db, task, run_token, "OCR", note.title)
    ocr = OCRService(PaddleOCREngine(settings), settings.ocr_min_confidence) if settings.ocr_enabled else None
    ocr_texts: list[str] = []
    image_rows: list[tuple] = []
    for index, image in enumerate(images, 1):
        assert_execution_active(db, task.id, run_token)
        result = {"status": "disabled", "text": "", "error": ""}
        if ocr:
            def recognize():
                value = ocr.process(image)
                if value["status"] == "failed":
                    raise RuntimeError(value["error"] or "OCR failed")
                return value
            try:
                result = run_stage(recognize, attempts, delay)
            except Exception as exc:
                result = {"status": "failed", "text": "", "error": str(exc)}
        assert_execution_active(db, task.id, run_token)
        image_row = NoteImage(note_id=note.id, storage_key="", ocr_text=result["text"], ocr_status=result["status"], ocr_error=result["error"])
        db.add(image_row)
        image_rows.append((image, image_row))
        if result["text"]:
            ocr_texts.append(f"[IMAGE {index}]\n{result['text']}")
    note.status = "OCR_DONE" if ocr else "DOWNLOADED"
    task.ocr_notes += 1
    db.commit()

    set_progress(db, task, run_token, "EXTRACTING", note.title)
    combined = f"标题：{note.title}\n正文：{note.content}\n" + "\n".join(ocr_texts)
    # now 以 Note.published_at 为基准（如已解析），否则 fallback 到任务开始时间
    reference_now = note.published_at.replace(tzinfo=None) if note.published_at else started_at.replace(tzinfo=None)
    if settings.minimax_api_key:
        client = MiniMaxClient(settings)
        try:
            extracted = run_stage(lambda: extract_activities(combined, reference_now, lambda text: client.extract_many(text, started_at)), attempts, delay)
        except Exception as exc:
            log(db, task.id, "WARNING", f"MiniMax 提取失败，已降级规则提取：{exc}")
            extracted = extract_activities(combined, reference_now, None)
    else:
        extracted = extract_activities(combined, reference_now, None)
    assert_execution_active(db, task.id, run_token)

    from app.services.activity_validator import classify_zero_activity, validate_activities

    classification = classify_zero_activity(note, extracted)
    if classification in {"all_before_publish", "no_activity_signals"}:
        note.status = "NO_ACTIVITIES"
        log(db, task.id, "INFO", f"未提取到有效活动 原因={classification} url={note.source_url}")
        task.extracted_notes += 1
        db.commit()
        set_progress(db, task, run_token, "ARCHIVING", note.title)
        return False
    if classification == "minimax_empty_retryable":
        note.status = "EMPTY_RESULT_RETRYABLE"
        log(db, task.id, "INFO", f"MiniMax 返回空但有信号，可重试 url={note.source_url}")
        task.extracted_notes += 1
        db.commit()
        set_progress(db, task, run_token, "ARCHIVING", note.title)
        return False

    accepted, rejected = validate_activities(note, extracted)
    for reason in rejected:
        log(db, task.id, "INFO", f"跳过活动 原因={reason}")
    if not accepted:
        note.status = "NO_ACTIVITIES"
        log(db, task.id, "INFO", f"全部活动被过滤 url={note.source_url}")
        task.extracted_notes += 1
        db.commit()
        set_progress(db, task, run_token, "ARCHIVING", note.title)
        return False

    for fields in accepted:
        assert_execution_active(db, task.id, run_token)
        activity = Activity(
            note_id=note.id,
            name=fields.get("name") or note.title,
            city_code=city,
            start_time=datetime.fromisoformat(fields["start_time"]) if fields.get("start_time") else None,
            end_time=datetime.fromisoformat(fields["end_time"]) if fields.get("end_time") else None,
            location=fields.get("location") or "",
            price=fields.get("price") or "",
            type=fields.get("type") or "其他",
            source_url=note.source_url,
            source_image_indexes=fields.get("source_image_indexes") or [],
            summary=fields.get("summary") or note.content[:300],
            confidence=float(fields.get("confidence") or 0),
        )
        db.add(activity)
        db.flush()
        create_duplicate_candidates(db, activity)

    set_progress(db, task, run_token, "ARCHIVING", note.title)
    assert_execution_active(db, task.id, run_token)
    task_note_ids = select(Note.id).where(Note.task_id == task.id)
    task_activities = list(db.scalars(select(Activity).where(Activity.note_id.in_(task_note_ids)).order_by(Activity.id)).all())
    archive_task_result(settings.archive_dir, started_at, task.id, note, image_rows, task_activities)
    assert_execution_active(db, task.id, run_token)
    create_note_duplicate_candidates(db, note)
    shutil.rmtree(folder / ".downloads", ignore_errors=True)
    note.status = "PROCESSED"
    task.extracted_notes += 1
    task.success_notes = task.extracted_notes
    db.commit()
    return True


@celery_app.task(name="app.tasks.crawl_task.run", bind=True)
def run_crawl(self, task_id: int, run_token: str | None = None):
    db = SessionLocal()
    if not run_token:
        db.close()
        return
    claimed = db.execute(
        update(CrawlTask)
        .where(
            CrawlTask.id == task_id,
            CrawlTask.status == "PENDING",
            CrawlTask.run_token == run_token,
        )
        .values(status="RUNNING", current_stage="SEARCHING", current_note=None, error_message=None)
    )
    db.commit()
    if claimed.rowcount != 1:
        db.close()
        return
    task = db.get(CrawlTask, task_id)
    settings = get_settings()
    adapter = OpenCLIAdapter(settings)
    # 注册 task_id 到 adapter 让 run() 自动绑定 PID（如果 adapter 支持）
    if hasattr(adapter, "bind_task"):
        adapter.bind_task(
            task.id,
            run_token,
            execution_guard=lambda: assert_execution_active(db, task.id, run_token),
            warning_sink=lambda message: log(db, task.id, "WARNING", message),
        )
    try:
        if task.started_at is None:
            task.started_at = datetime.now(timezone.utc)
        db.commit()
        log(db, task.id, "INFO", "login check")
        results: list[tuple[str, dict]] = []
        discovery_failures = 0
        requested_cities = [task.params["city"]] if task.params.get("city") else task.params.get("cities", [])
        city_query = select(City).where(City.enabled.is_(True))
        if requested_cities:
            city_query = city_query.where(City.code.in_(requested_cities))
        cities = list(db.scalars(city_query.order_by(City.id)).all())
        if cities:
            for city in cities:
                scope = resolve_crawl_scope(db, city, task.params)
                override = "任务参数" if ("keywords" in task.params or "blogger_ids" in task.params) else "配置默认"
                log(db, task.id, "INFO", f"抓取范围生效：keywords={len(scope.keywords)} bloggers={len(scope.bloggers)} (override={override})")
                recent_filter = task.params.get("recent_filter") or city.recent_filter
                for keyword in scope.keywords:
                    for item in adapter.search_recent(f"{city.name} {keyword}", recent_filter):
                        tagged = dict(item)
                        tagged["_matched_keywords"] = [keyword]
                        results.append((city.code, tagged))
                    assert_execution_active(db, task.id, run_token)
                for blogger in scope.bloggers:
                    username = (blogger.username or "").strip()
                    if not username:
                        log(db, task.id, "WARNING", f"跳过博主：username 为空 id={blogger.id}")
                        continue
                    try:
                        items = adapter.blogger_notes(username, blogger.profile_url or "")
                    except (AuthenticationRequired, ExecutionStopped, ExecutionSuperseded):
                        raise
                    except Exception as exc:
                        discovery_failures += 1
                        task.error_message = f"博主 {username!r} 抓取失败：{exc}"
                        db.commit()
                        log(db, task.id, "ERROR", task.error_message)
                        continue
                    assert_execution_active(db, task.id, run_token)
                    log(db, task.id, "INFO", f"博主 {username!r} 命中 {len(items)} 篇（带 xsec_token 的）")
                    results.extend((city.code, item) for item in items)
        else:
            for city_code in requested_cities:
                for keyword in task.params.get("keywords", []):
                    for item in adapter.search_recent(f"{city_code} {keyword}", "一周内"):
                        tagged = dict(item)
                        tagged["_matched_keywords"] = [keyword]
                        results.append((city_code, tagged))
                    assert_execution_active(db, task.id, run_token)

        results = deduplicate_results(results)
        task.total_notes = len(results)
        db.commit()

        def processor(entry: tuple[str, dict]) -> None:
            matched_keywords = entry[1].get("_matched_keywords")
            if matched_keywords and not title_matches_keywords(entry[1].get("title", ""), matched_keywords):
                task.skipped_notes += 1
                db.commit()
                log(db, task.id, "INFO", f"标题未包含关键词，已跳过 [{entry[1]['url']}] 标题={entry[1].get('title', '')!r} 关键词={matched_keywords}")
                return
            process_note(db, task, run_token, entry[0], entry[1], adapter, settings)

        def on_failure(entry: tuple[str, dict], exc: Exception) -> None:
            db.rollback()
            cleanup_incomplete_note(db, entry[1]["url"])
            current = db.get(CrawlTask, task.id)
            current.failed_notes += 1
            current.error_message = str(exc)
            db.commit()
            log(db, current.id, "ERROR", f"笔记处理失败 [{entry[1]['url']}]：{exc}")

        for entry in results:
            if finish_stop_if_requested(db, task.id, run_token):
                return
            try:
                processor(entry)
            except ExecutionStopped:
                db.rollback()
                cleanup_incomplete_note(db, entry[1]["url"])
                finish_stop_if_requested(db, task.id, run_token)
                return
            except ExecutionSuperseded:
                db.rollback()
                return
            except AuthenticationRequired:
                raise
            except Exception as exc:
                on_failure(entry, exc)
        if finish_stop_if_requested(db, task.id, run_token):
            return
        task = db.get(CrawlTask, task.id)
        task.status = "COMPLETED_WITH_ERRORS" if task.failed_notes or discovery_failures else "COMPLETED"
        task.current_stage = None
        task.current_note = None
        task.finished_at = datetime.now(timezone.utc)
        db.commit()
        log(db, task.id, "INFO", "completed")
    except ExecutionStopped:
        db.rollback()
        finish_stop_if_requested(db, task_id, run_token)
    except ExecutionSuperseded:
        db.rollback()
    except AuthenticationRequired as exc:
        task = db.get(CrawlTask, task_id)
        task.status = "PAUSED"
        task.error_message = str(exc)
        db.commit()
        log(db, task.id, "ERROR", str(exc))
        if isinstance(exc, VerificationRequired):
            try:
                open_xhs_login(settings)
                log(db, task.id, "INFO", "已自动打开 Chrome 小红书验证页面")
            except Exception as launch_exc:
                log(db, task.id, "WARNING", f"自动打开 Chrome 失败：{launch_exc}")
    except Exception as exc:
        db.rollback()
        task = db.get(CrawlTask, task_id)
        task.status = "FAILED"
        task.error_message = str(exc)
        task.current_stage = None
        db.commit()
        log(db, task.id, "ERROR", str(exc))
    finally:
        db.close()
