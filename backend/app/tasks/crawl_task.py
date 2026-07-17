from datetime import datetime, timezone
import shutil

from sqlalchemy import delete, select

from app.core.config import get_settings
from app.core.database import SessionLocal
from app.models.activity import Activity
from app.models.config import Blogger, City, Keyword
from app.models.note import Note, NoteImage
from app.models.task import CrawlTask, TaskLog
from app.services.archive import archive_task_folder, archive_task_result
from app.services.crawler import AuthenticationRequired
from app.services.dedup import create_duplicate_candidates
from app.services.extraction import extract_activities
from app.services.minimax import MiniMaxClient
from app.services.ocr import OCRService
from app.services.opencli_adapter import OpenCLIAdapter
from app.services.paddleocr_adapter import PaddleOCREngine
from app.services.pipeline import deduplicate_results, process_with_isolation, run_stage, title_matches_keywords
from app.tasks.celery_app import celery_app


def log(db, task_id: int, level: str, message: str) -> None:
    db.add(TaskLog(task_id=task_id, level=level, message=message))
    db.commit()


def set_progress(db, task: CrawlTask, stage: str, current_note: str | None = None) -> None:
    task.current_stage = stage
    task.current_note = current_note
    db.commit()


def cleanup_incomplete_note(db, source_url: str) -> None:
    note = db.scalar(select(Note).where(Note.source_url == source_url))
    if note is None or note.status == "PROCESSED":
        return
    db.execute(delete(Activity).where(Activity.note_id == note.id))
    db.execute(delete(NoteImage).where(NoteImage.note_id == note.id))
    db.delete(note)
    db.commit()


def prepare_existing_note(db, source_url: str) -> bool:
    """Return True when a note is already complete; remove partial legacy rows otherwise."""
    note = db.scalar(select(Note).where(Note.source_url == source_url))
    if note is None:
        return False
    has_activity = db.scalar(select(Activity.id).where(Activity.note_id == note.id).limit(1)) is not None
    if note.status == "PROCESSED" or has_activity:
        if note.status != "PROCESSED":
            note.status = "PROCESSED"
            db.commit()
        return True
    cleanup_incomplete_note(db, source_url)
    return False


def process_note(db, task: CrawlTask, city: str, item: dict, adapter: OpenCLIAdapter, settings) -> bool:
    if prepare_existing_note(db, item["url"]):
        return False

    attempts = settings.pipeline_stage_max_retries
    delay = settings.pipeline_stage_retry_delay_seconds
    started_at = task.started_at or datetime.now(timezone.utc)
    set_progress(db, task, "DOWNLOADING", item.get("title") or item["url"])
    detail = run_stage(lambda: adapter.note(item["url"]), attempts, delay)
    note = Note(
        task_id=task.id,
        platform_note_id=item["url"].split("/")[-1].split("?")[0],
        title=item.get("title", ""),
        content=detail.get("content", ""),
        source_url=item["url"],
        city_code=city,
        status="DOWNLOADED",
        raw_data=detail,
    )
    db.add(note)
    db.flush()
    folder = archive_task_folder(settings.archive_dir, started_at, task.id)
    download_dir = folder / ".downloads" / note.platform_note_id
    images = run_stage(lambda: adapter.download(item["url"], download_dir), attempts, delay)
    task.downloaded_notes += 1
    db.commit()

    set_progress(db, task, "OCR", note.title)
    ocr = OCRService(PaddleOCREngine(settings), settings.ocr_min_confidence) if settings.ocr_enabled else None
    ocr_texts: list[str] = []
    image_rows: list[tuple] = []
    for index, image in enumerate(images, 1):
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
        image_row = NoteImage(note_id=note.id, storage_key="", ocr_text=result["text"], ocr_status=result["status"], ocr_error=result["error"])
        db.add(image_row)
        image_rows.append((image, image_row))
        if result["text"]:
            ocr_texts.append(f"[IMAGE {index}]\n{result['text']}")
    note.status = "OCR_DONE" if ocr else "DOWNLOADED"
    task.ocr_notes += 1
    db.commit()

    set_progress(db, task, "EXTRACTING", note.title)
    combined = f"标题：{note.title}\n正文：{note.content}\n" + "\n".join(ocr_texts)
    now = datetime.now()
    if settings.minimax_api_key:
        client = MiniMaxClient(settings)
        try:
            extracted = run_stage(lambda: extract_activities(combined, now, client.extract_many), attempts, delay)
        except Exception as exc:
            log(db, task.id, "WARNING", f"MiniMax 提取失败，已降级规则提取：{exc}")
            extracted = extract_activities(combined, now, None)
    else:
        extracted = extract_activities(combined, now, None)

    for fields in extracted:
        activity = Activity(
            note_id=note.id,
            name=fields.get("name") or note.title,
            city_code=city,
            start_time=datetime.fromisoformat(fields["start_time"]) if fields.get("start_time") else datetime.now(timezone.utc),
            end_time=datetime.fromisoformat(fields["end_time"]) if fields.get("end_time") else None,
            location=fields.get("location") or "",
            price=fields.get("price") or "",
            type=fields.get("type") or "其他",
            source_url=note.source_url,
            source_image_indexes=fields.get("source_image_indexes") or [],
            summary=fields.get("summary") or note.content[:300],
            status=fields["status"],
            confidence=float(fields.get("confidence") or 0),
        )
        db.add(activity)
        db.flush()
        create_duplicate_candidates(db, activity)

    set_progress(db, task, "ARCHIVING", note.title)
    task_note_ids = select(Note.id).where(Note.task_id == task.id)
    task_activities = list(db.scalars(select(Activity).where(Activity.note_id.in_(task_note_ids)).order_by(Activity.id)).all())
    archive_task_result(settings.archive_dir, started_at, task.id, note, image_rows, task_activities)
    shutil.rmtree(folder / ".downloads", ignore_errors=True)
    note.status = "PROCESSED"
    task.extracted_notes += 1
    task.success_notes = task.extracted_notes
    db.commit()
    return True


@celery_app.task(name="app.tasks.crawl_task.run", bind=True)
def run_crawl(self, task_id: int):
    db = SessionLocal()
    task = db.get(CrawlTask, task_id)
    settings = get_settings()
    adapter = OpenCLIAdapter(settings)
    try:
        task.status = "RUNNING"
        task.current_stage = "SEARCHING"
        task.current_note = None
        task.error_message = None
        task.started_at = datetime.now(timezone.utc)
        db.commit()
        log(db, task.id, "INFO", "login check")
        results: list[tuple[str, dict]] = []
        requested_cities = [task.params["city"]] if task.params.get("city") else task.params.get("cities", [])
        city_query = select(City).where(City.enabled.is_(True))
        if requested_cities:
            city_query = city_query.where(City.code.in_(requested_cities))
        cities = list(db.scalars(city_query.order_by(City.id)).all())
        if cities:
            for city in cities:
                configured_keywords = list(db.scalars(select(Keyword.word).where(Keyword.city_code == city.code, Keyword.enabled.is_(True)).order_by(Keyword.id)).all())
                keywords = task.params.get("keywords") or configured_keywords
                recent_filter = task.params.get("recent_filter") or city.recent_filter
                for keyword in keywords:
                    for item in adapter.search_recent(f"{city.name} {keyword}", recent_filter):
                        tagged = dict(item)
                        tagged["_matched_keywords"] = [keyword]
                        results.append((city.code, tagged))
                blogger_ids = task.params.get("blogger_ids", [])
                if blogger_ids:
                    bloggers = list(db.scalars(select(Blogger).where(Blogger.id.in_(blogger_ids), Blogger.city_code == city.code, Blogger.enabled.is_(True))).all())
                    for blogger in bloggers:
                        results.extend((city.code, item) for item in adapter.blogger_notes(blogger.profile_url))
        else:
            for city_code in requested_cities:
                for keyword in task.params.get("keywords", []):
                    for item in adapter.search_recent(f"{city_code} {keyword}", "一周内"):
                        tagged = dict(item)
                        tagged["_matched_keywords"] = [keyword]
                        results.append((city_code, tagged))

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
            process_note(db, task, entry[0], entry[1], adapter, settings)

        def on_failure(entry: tuple[str, dict], exc: Exception) -> None:
            db.rollback()
            cleanup_incomplete_note(db, entry[1]["url"])
            current = db.get(CrawlTask, task.id)
            current.failed_notes += 1
            current.error_message = str(exc)
            db.commit()
            log(db, current.id, "ERROR", f"笔记处理失败 [{entry[1]['url']}]：{exc}")

        process_with_isolation(results, processor, on_failure)
        task = db.get(CrawlTask, task.id)
        task.status = "COMPLETED_WITH_ERRORS" if task.failed_notes else "COMPLETED"
        task.current_stage = None
        task.current_note = None
        task.finished_at = datetime.now(timezone.utc)
        db.commit()
        log(db, task.id, "INFO", "completed")
    except AuthenticationRequired as exc:
        task = db.get(CrawlTask, task_id)
        task.status = "PAUSED"
        task.error_message = str(exc)
        db.commit()
        log(db, task.id, "ERROR", str(exc))
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
