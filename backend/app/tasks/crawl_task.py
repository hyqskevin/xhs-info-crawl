from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from collections.abc import Callable
from dataclasses import dataclass
from types import SimpleNamespace
import logging
import shutil
import time

from sqlalchemy import delete, func, select, update

from app.core.config import get_settings
from app.core.database import SessionLocal
from app.models.activity import Activity
from app.models.blogger_city import BloggerCity
from app.models.blogger_group import BloggerGroup, BloggerGroupMember
from app.models.config import Blogger, City
from app.models.keyword_group import KeywordGroupCity
from app.models.note import Note, NoteImage
from app.models.schedule import ScheduledCrawl
from app.models.task import CrawlTask, TaskLog
from app.models.xhs_account import XhsAccount
from app.services.archive import archive_task_folder, archive_task_result
from app.services.crawler import AuthenticationRequired, CrawlHalted, VerificationRequired
from app.services.browser_launcher import open_xhs_login
from app.services.crawl_city_guard import assert_city_code_exists
from app.services.crawl_scope import resolve_crawl_scope
from app.services.dedup import create_note_duplicate_candidates
from app.services.extraction import extract_activities
from app.services.minimax import MiniMaxClient
from app.services.note_identity import extract_platform_note_id
from app.services.ocr import OCRService
from app.services.note_id_published_at import note_id_published_at
from app.services.published_at import extract_published_at
from app.services.search_rate_limit import (
    SearchRateLimiter,
    increment_weekly_search,
    iso_week_key,
    weekly_search_count,
)
from app.services.opencli_adapter import OpenCLIAdapter
from app.services.paddleocr_adapter import PaddleOCREngine
from app.services.pipeline import deduplicate_results, run_stage, title_matches_keywords
from app.services.chrome_pool import ChromePool, ChromeLaunchError, get_global_chrome_pool
from app.tasks.celery_app import celery_app


def find_opencli(bin_name: str) -> str | None:
    """解析 opencli 可执行文件路径（shutil.which 的薄封装，测试可 patch）。"""
    return shutil.which(bin_name)


def _extract_engagement(detail: dict, field: str) -> int | None:
    """从 opencli note 详情中提取互动数。

    字段名映射：opencli 实际返回可能是 liked_count / collected_count 等。
    实施时若已确认实际字段名，替换候选列表。
    """
    if not isinstance(detail, dict):
        return None
    candidates = {
        "like_count": ("like_count", "liked_count", "likes"),
        "collect_count": ("collect_count", "collected_count", "collects"),
        "comment_count": ("comment_count", "comments"),
    }.get(field, (field,))
    for key in candidates:
        if key in detail and detail[key] is not None:
            try:
                return int(detail[key])
            except (TypeError, ValueError):
                return None
    return None


def rate_limit_sleep(seconds: float, guard: Callable[[], None] | None = None) -> None:
    """可中断的频率控制 sleep：0.5s 分片，每片执行 guard（执行栅栏），stop 请求 0.5s 内响应。"""
    deadline = time.monotonic() + max(0.0, seconds)
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return
        time.sleep(min(0.5, remaining))
        if guard:
            guard()


class ExecutionStopped(Exception):
    pass


class ExecutionSuperseded(Exception):
    pass


@dataclass
class StagedNote:
    """阶段 1 产出、阶段 2 消费的中间结构。

    - note：已写入 DB 的 Note（状态为 OCR_DONE / DOWNLOADED）
    - combined_text：标题+正文+OCR 拼接文本，供 MiniMax/规则提取
    - reference_now：活动日期推断基准（Note.published_at 或 task.started_at）
    - started_at：任务开始时间，用于归档目录
    - image_rows：[(image_path, NoteImage)]，归档时复制图片用
    """

    note: Note
    combined_text: str
    reference_now: datetime
    started_at: datetime
    image_rows: list[tuple]


logger = logging.getLogger(__name__)

_DISPATCH_TZ = ZoneInfo("Asia/Shanghai")
_BUSY_STATUSES = ("PENDING", "RUNNING", "STOP_REQUESTED")


def _collect_cities_from_groups(db, task_params: dict) -> list[str]:
    """不限城市（city 为空）时，从博主组/关键词组挂的城市合并出抓取城市列表。

    - 博主组 → 从 BloggerCity 取组内博主挂的城市（去重保留顺序）
    - 关键词组 → 从 KeywordGroupCity 取组挂的城市
    """
    city_codes: list[str] = []
    seen: set[str] = set()

    # 博主组：组内所有博主挂的城市
    blogger_group_ids = task_params.get("blogger_group_ids") or []
    if blogger_group_ids:
        stmt = (
            select(BloggerCity.city_code)
            .join(BloggerGroupMember, BloggerGroupMember.blogger_id == BloggerCity.blogger_id)
            .where(
                BloggerGroupMember.group_id.in_(blogger_group_ids),
                BloggerCity.enabled.is_(True),
            )
            .distinct()
        )
        for code in db.scalars(stmt).all():
            if code not in seen:
                seen.add(code)
                city_codes.append(code)

    # 关键词组：组挂的城市
    keyword_group_ids = task_params.get("keyword_group_ids") or []
    if keyword_group_ids:
        stmt = (
            select(KeywordGroupCity.city_code)
            .where(
                KeywordGroupCity.keyword_group_id.in_(keyword_group_ids),
                KeywordGroupCity.enabled.is_(True),
            )
            .distinct()
        )
        for code in db.scalars(stmt).all():
            if code not in seen:
                seen.add(code)
                city_codes.append(code)

    return city_codes


def _expand_blogger_groups(db, city_code: str | None, group_ids: list[int]) -> list[int]:
    """博主组展开。

    - city_code 给出：组内 enabled 博主 ∩ 该城市 blogger_cities.enabled 博主
    - city_code=None：组内 enabled 博主（不限城市）
    """
    if not group_ids:
        return []
    stmt = (
        select(Blogger.id)
        .join(BloggerGroupMember, BloggerGroupMember.blogger_id == Blogger.id)
        .join(BloggerGroup, BloggerGroup.id == BloggerGroupMember.group_id)
        .where(
            BloggerGroupMember.group_id.in_(group_ids),
            BloggerGroup.enabled.is_(True),
            Blogger.enabled.is_(True),
        )
    )
    if city_code:
        stmt = stmt.join(
            BloggerCity, BloggerCity.blogger_id == Blogger.id
        ).where(
            BloggerCity.city_code == city_code,
            BloggerCity.enabled.is_(True),
        )
    stmt = stmt.order_by(Blogger.id)
    return list(dict.fromkeys(db.scalars(stmt).all()))


def load_xhs_accounts(db) -> list:
    """加载已启用的 XhsAccount 列表，按 priority 升序、id 升序排列。

    无账号配置时返回空列表，调用方负责回退到默认 session 'xhs-crawler'。
    """
    return list(db.scalars(
        select(XhsAccount)
        .where(XhsAccount.enabled.is_(True))
        .order_by(XhsAccount.priority, XhsAccount.id)
    ).all())


def _account_cdp_endpoint(account) -> str | None:
    """从 XhsAccount.cdp_port 推导 CDP 端点（仅基于账号行静态推导，不依赖 pool 实例）；None 表示回退默认 Chrome Browser Bridge。"""
    port = getattr(account, "cdp_port", None)
    if port is None:
        return None
    return f"http://127.0.0.1:{port}"


def _resolve_cdp_endpoint_for_account(account, chrome_pool) -> str | None:
    """优先用 chrome_pool 中已启动实例的端点（动态端口）；fallback 到账号行的 cdp_port。"""
    if chrome_pool is not None:
        instance = chrome_pool.get(account.session_name)
        if instance is not None:
            return instance.cdp_endpoint
    return _account_cdp_endpoint(account)


def _make_chrome_pool_for_task(settings, db, accounts) -> ChromePool:
    """为当前任务启动 ChromePool（每个有 cdp_port 的账号一个实例）。

    使用全局 ChromePool 单例——API 端点（如 check-login）和 crawl_task 共享同一池，
    避免重复启动 Chrome 实例导致端口冲突。
    """
    pool = get_global_chrome_pool()
    # 同步端口到 DB（持久化，供下次复用）
    for account in accounts:
        port = getattr(account, "cdp_port", None)
        if port is None:
            continue
        try:
            instance = pool.acquire(account.session_name)
        except ChromeLaunchError:
            raise
        # 同步实际分配端口（避免 ChromePool 分配与 cdp_port 不一致）
        if instance.port != port:
            account.cdp_port = instance.port
            db.commit()
    return pool


@celery_app.task(name="app.tasks.crawl_task.scheduled_dispatch")
def scheduled_dispatch(now: datetime | None = None) -> None:
    """每分钟由 beat 触发：匹配到点的 enabled 定时任务并创建抓取任务。

    - slot 幂等：last_fired_slot == 当前分钟则跳过（防 beat 重启/重复 tick 重发）；
    - 单任务约束：已有 PENDING/RUNNING/STOP_REQUESTED 任务时跳过本次触发
      （保守语义：定时任务不打断人工任务，与手动 crawl 的"顶替"语义刻意不同）。
    """
    now = (now or datetime.now(_DISPATCH_TZ)).astimezone(_DISPATCH_TZ)
    slot = now.strftime("%Y-%m-%dT%H:%M")
    db = SessionLocal()
    try:
        schedules = db.scalars(
            select(ScheduledCrawl).where(
                ScheduledCrawl.enabled.is_(True),
                ScheduledCrawl.day_of_week == now.isoweekday(),
                ScheduledCrawl.hour == now.hour,
                ScheduledCrawl.minute == now.minute,
            )
        ).all()
        if not schedules:
            return
        busy = db.scalar(
            select(func.count()).select_from(CrawlTask).where(CrawlTask.status.in_(_BUSY_STATUSES))
        )
        for schedule in schedules:
            if schedule.last_fired_slot == slot:
                continue
            if busy:
                logger.warning(
                    "scheduled_dispatch: 任务进行中，跳过 schedule id=%s slot=%s", schedule.id, slot
                )
                continue
            params: dict = {
                "type": "scheduled",
                "city": schedule.city_code,
                "keyword_group_ids": schedule.keyword_group_ids or [],
                "blogger_ids": _expand_blogger_groups(db, schedule.city_code, schedule.blogger_group_ids or []),
                "schedule_id": schedule.id,
                "schedule_name": schedule.name,
                "fired_slot": slot,
            }
            if schedule.recent_filter:
                params["recent_filter"] = schedule.recent_filter
            task = CrawlTask(type="scheduled", status="PENDING", params=params)
            db.add(task)
            db.commit()
            db.refresh(task)
            schedule.last_fired_slot = slot
            db.commit()
            run_crawl.delay(task.id, task.run_token)
            busy = True  # 同一 tick 后续 schedule 不再叠加任务
    finally:
        db.close()


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


def throttled_search(db, settings, task, adapter, query, recent, run_token=None, rate_limiter=None) -> list[dict] | None:
    """模块级 throttled_search：搜索的频率与周配额闸门；返回 None 表示本周超限。

    注：原位于 run_crawl 闭包内，提取为模块级以便测试 monkeypatch；行为完全等价。
    rate_limiter 必须由调用方复用同一个实例，否则 monkeypatch 不生效。
    """
    week_key = iso_week_key()
    if weekly_search_count(db, week_key) >= settings.weekly_search_limit:
        log(db, task.id, "WARNING", f"本周搜索量已达上限（{settings.weekly_search_limit}），跳过 {query!r} 及后续关键词搜索")
        return None
    if rate_limiter is None:
        rate_limiter = SearchRateLimiter(settings.search_interval_min, settings.search_interval_max)
    delay = rate_limiter.next_delay()
    if delay and run_token is not None:
        rate_limit_sleep(delay, guard=lambda: assert_execution_active(db, task.id, run_token))
    found = adapter.search_recent(query, recent)
    increment_weekly_search(db, week_key)
    return found


def _collect_crawl_results(
    db,
    settings,
    task: CrawlTask,
    adapter: OpenCLIAdapter,
    throttled_search: Callable[[str, str], list[dict] | None],
    run_token: str,
) -> tuple[list[tuple[str, dict]], int]:
    """执行搜索/博主发现阶段，返回 (results, discovery_failures)。

    - results: list of (city_code, item)；item 含 _matched_keywords 字段
    - discovery_failures: 博主层失败计数（连续失败熔断在调用方处理）
    - CrawlHalted 由博主层连续失败触发，由调用方捕获
    """
    results: list[tuple[str, dict]] = []
    discovery_failures = 0
    consecutive_failures = 0
    # city/cities 优先级：city 优先；若 city 为 ''（不限城市）→ 视为未指定，按 keyword_group_ids/blogger_group_ids 各自挂的城市展开
    requested_cities: list[str] = []
    if task.params.get("city"):
        requested_cities = [task.params["city"]]
    elif task.params.get("cities"):
        requested_cities = task.params["cities"]
    else:
        # city='' 或未设置：从博主组挂的城市 / 关键词组挂的城市合并
        group_cities = _collect_cities_from_groups(db, task.params)
        if group_cities:
            requested_cities = group_cities
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
                found = throttled_search(f"{city.name} {keyword}", recent_filter)
                if found is None:
                    break
                for item in found:
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
                    consecutive_failures += 1
                    if consecutive_failures >= settings.consecutive_note_failure_limit:
                        raise CrawlHalted(
                            f"已连续 {consecutive_failures} 次抓取失败（最近一次：博主 {username!r}）。"
                            f"CDP session / 浏览器标签页可能已过期，请在 Chrome 重新打开小红书后"
                            f"点击「检测登录并继续」，或「结束抓取」。最后一次错误：{exc}"
                        )
                    continue
                consecutive_failures = 0
                assert_execution_active(db, task.id, run_token)
                log(db, task.id, "INFO", f"博主 {username!r} 命中 {len(items)} 篇（带 xsec_token 的）")
                if blogger.max_notes_per_crawl and blogger.max_notes_per_crawl > 0 and len(items) > blogger.max_notes_per_crawl:
                    log(db, task.id, "INFO", f"博主 {username!r} 抓取上限 {blogger.max_notes_per_crawl}，截断至 {blogger.max_notes_per_crawl} 篇")
                    items = items[:blogger.max_notes_per_crawl]
                for item in items:
                    tagged = dict(item)
                    tagged["_matched_blogger_id"] = blogger.id
                    tagged["_matched_blogger_username"] = blogger.username
                    results.append((city.code, tagged))
    else:
        for city_code in requested_cities:
            quota_exceeded = False
            for keyword in task.params.get("keywords", []):
                found = throttled_search(f"{city_code} {keyword}", "一周内")
                if found is None:
                    quota_exceeded = True
                    break
                for item in found:
                    tagged = dict(item)
                    tagged["_matched_keywords"] = [keyword]
                    results.append((city_code, tagged))
                assert_execution_active(db, task.id, run_token)
            if quota_exceeded:
                break
    return results, discovery_failures


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


def download_and_ocr(db, task: CrawlTask, run_token: str, city: str, item: dict, adapter: OpenCLIAdapter, settings) -> StagedNote | None:
    """阶段 1：下载笔记详情 + 图片 + OCR，返回 StagedNote 或 None（跳过/失败）。

    不调用 MiniMax，不写 Activity。保留 assert_execution_active / set_progress 调用。
    """
    assert_execution_active(db, task.id, run_token)
    note_url = (item.get("url") or "").strip()
    if not note_url:
        log(db, task.id, "WARNING", f"跳过笔记：url 为空 title={item.get('title', '')!r}")
        return None
    if not assert_city_code_exists(db, city):
        log(db, task.id, "ERROR", f"city_code 不在 cities 表：{city!r}，跳过该笔记 url={note_url}")
        task.skipped_activities += 1
        return None
    if prepare_existing_note(db, note_url):
        return None

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
        matched_keywords=item.get("_matched_keywords") or [],
        matched_blogger_id=item.get("_matched_blogger_id"),
        matched_blogger_username=item.get("_matched_blogger_username"),
        like_count=_extract_engagement(detail, "like_count"),
        collect_count=_extract_engagement(detail, "collect_count"),
        comment_count=_extract_engagement(detail, "comment_count"),
    )
    db.add(note)
    db.flush()
    folder = archive_task_folder(settings.archive_dir, started_at, task.id, city)
    download_dir = folder / ".downloads" / note.platform_note_id
    images = run_stage(lambda: adapter.download(note_url, download_dir), attempts, delay)
    assert_execution_active(db, task.id, run_token)
    task.downloaded_notes += 1
    db.commit()

    set_progress(db, task, run_token, "OCR", note.title)
    ocr = OCRService(PaddleOCREngine(settings), settings.ocr_min_confidence) if settings.ocr_enabled else None
    ocr_texts: list[str] = []
    image_rows: list[tuple] = []
    assert_execution_active(db, task.id, run_token)
    if ocr:
        # 并行 OCR：process_batch 用 ThreadPoolExecutor 并行处理所有图片，子线程内含重试
        ocr_results = ocr.process_batch(
            images,
            workers=settings.ocr_parallel_workers,
            attempts=attempts,
            delay=delay,
        )
        assert_execution_active(db, task.id, run_token)
        for index, (image, result) in enumerate(zip(images, ocr_results), 1):
            image_row = NoteImage(note_id=note.id, storage_key="", ocr_text=result["text"], ocr_status=result["status"], ocr_error=result["error"])
            db.add(image_row)
            image_rows.append((image, image_row))
            if result["text"]:
                ocr_texts.append(f"[IMAGE {index}]\n{result['text']}")
    else:
        for index, image in enumerate(images, 1):
            result = {"status": "disabled", "text": "", "error": ""}
            image_row = NoteImage(note_id=note.id, storage_key="", ocr_text=result["text"], ocr_status=result["status"], ocr_error=result["error"])
            db.add(image_row)
            image_rows.append((image, image_row))
    note.status = "OCR_DONE" if ocr else "DOWNLOADED"
    task.ocr_notes += 1
    db.commit()

    combined = f"标题：{note.title}\n正文：{note.content}\n" + "\n".join(ocr_texts)
    # now 以 Note.published_at 为基准（如已解析），否则 fallback 到任务开始时间
    reference_now = note.published_at.replace(tzinfo=None) if note.published_at else started_at.replace(tzinfo=None)
    return StagedNote(
        note=note,
        combined_text=combined,
        reference_now=reference_now,
        started_at=started_at,
        image_rows=image_rows,
    )


def extract_and_save(db, task: CrawlTask, run_token: str, staged: StagedNote, extracted, settings) -> bool:
    """阶段 2：校验活动 + 写 Activity + 归档 + 更新 Note 状态。

    接收已提取的 extracted（list[dict]），不调用 MiniMax。
    返回 True 表示 PROCESSED，False 表示无活动被过滤。
    """
    note = staged.note
    city = note.city_code
    started_at = staged.started_at
    image_rows = staged.image_rows
    set_progress(db, task, run_token, "EXTRACTING", note.title)
    assert_execution_active(db, task.id, run_token)

    from app.services.activity_validator import classify_zero_activity, validate_activities

    classification = classify_zero_activity(note, extracted)
    if classification in {"all_before_publish", "no_activity_signals"}:
        note.status = "NO_ACTIVITIES"
        log(db, task.id, "INFO", f"未提取到有效活动 原因={classification} url={note.source_url}")
        if classification == "all_before_publish" and extracted:
            preview = "; ".join(
                f"{a.get('name')!r}@{a.get('start_time')}" for a in extracted[:5]
            )
            suffix = "" if len(extracted) <= 5 else f" (共 {len(extracted)} 条)"
            log(db, task.id, "INFO", f"被拒绝活动预览：{preview}{suffix}")
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

    set_progress(db, task, run_token, "ARCHIVING", note.title)
    assert_execution_active(db, task.id, run_token)
    task_note_ids = select(Note.id).where(Note.task_id == task.id)
    task_activities = list(db.scalars(select(Activity).where(Activity.note_id.in_(task_note_ids)).order_by(Activity.id)).all())
    archive_task_result(settings.archive_dir, started_at, task.id, note, image_rows, task_activities, city)
    assert_execution_active(db, task.id, run_token)
    create_note_duplicate_candidates(db, note)
    folder = archive_task_folder(settings.archive_dir, started_at, task.id, city)
    shutil.rmtree(folder / ".downloads", ignore_errors=True)
    note.status = "PROCESSED"
    task.extracted_notes += 1
    task.success_notes = task.extracted_notes
    db.commit()
    return True


def process_note(db, task: CrawlTask, run_token: str, city: str, item: dict, adapter: OpenCLIAdapter, settings) -> bool:
    """向后兼容包装：download_and_ocr + 单篇 MiniMax 提取 + extract_and_save。

    供直接调用 process_note 的旧路径使用；run_crawl 已改为两阶段流水线，不再走这里。
    """
    staged = download_and_ocr(db, task, run_token, city, item, adapter, settings)
    if staged is None:
        return False
    attempts = settings.pipeline_stage_max_retries
    delay = settings.pipeline_stage_retry_delay_seconds
    if settings.minimax_api_key:
        client = MiniMaxClient(settings)
        try:
            extracted = run_stage(lambda: extract_activities(staged.combined_text, staged.reference_now, lambda text: client.extract_many(text, staged.started_at)), attempts, delay)
        except Exception as exc:
            log(db, task.id, "WARNING", f"MiniMax 提取失败，已降级规则提取：{exc}")
            extracted = extract_activities(staged.combined_text, staged.reference_now, None)
    else:
        extracted = extract_activities(staged.combined_text, staged.reference_now, None)
    return extract_and_save(db, task, run_token, staged, extracted, settings)


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
    if find_opencli(settings.opencli_bin) is None:
        message = (
            f"opencli 不可用：未找到命令 {settings.opencli_bin!r}"
            "（请运行 npm install -g @jackwener/opencli 或在 .env 配置 OPENCLI_BIN 指向其绝对路径）"
        )
        task.status = "FAILED"
        task.error_message = message
        task.current_stage = None
        task.finished_at = datetime.now(timezone.utc)
        db.commit()
        log(db, task.id, "ERROR", message)
        db.close()
        return
    accounts = load_xhs_accounts(db)
    if not accounts:
        accounts = [SimpleNamespace(name="默认", session_name="xhs-crawler", id=None)]
    # 为每个有 cdp_port 的账号启动独立 Chrome 实例（ChromePool）
    # 缺 cdp_port 的账号回退默认 Chrome Browser Bridge（向后兼容）
    chrome_pool: ChromePool | None = None
    if any(getattr(a, "cdp_port", None) is not None for a in accounts):
        try:
            chrome_pool = _make_chrome_pool_for_task(settings, db, accounts)
        except ChromeLaunchError as exc:
            log(db, task_id, "ERROR", f"Chrome 实例启动失败：{exc}")
            chrome_pool = None  # 退化为默认 CDP（向原 Chrome Browser Bridge）
    account_index = 0
    adapter = OpenCLIAdapter(
        settings,
        session=accounts[0].session_name,
        cdp_endpoint=_resolve_cdp_endpoint_for_account(accounts[0], chrome_pool),
    )
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
        log(db, task.id, "INFO", "登录预检：检查小红书登录状态")
        adapter.check_login()
        log(db, task.id, "INFO", "登录预检通过")
        results: list[tuple[str, dict]] = []
        discovery_failures = 0
        consecutive_failures = 0

        rate_limiter = SearchRateLimiter(settings.search_interval_min, settings.search_interval_max)

        def _run_throttled_search(query: str, recent: str) -> list[dict] | None:
            return throttled_search(db, settings, task, adapter, query, recent, run_token, rate_limiter)

        results, discovery_failures = _collect_crawl_results(
            db, settings, task, adapter, _run_throttled_search, run_token,
        )

        results = deduplicate_results(results)
        task.total_notes = len(results)
        db.commit()

        def on_failure(entry: tuple[str, dict], exc: Exception) -> None:
            db.rollback()
            cleanup_incomplete_note(db, entry[1]["url"])
            current = db.get(CrawlTask, task.id)
            current.failed_notes += 1
            current.error_message = str(exc)
            db.commit()
            log(db, current.id, "ERROR", f"笔记处理失败 [{entry[1]['url']}]：{exc}")

        def reset_adapter_session(current_adapter: OpenCLIAdapter, reason: str) -> OpenCLIAdapter:
            """强制重建 CDP 连接，释放 Chrome profile 状态。失败仅 WARNING，不中断任务。"""
            try:
                current_adapter.close_session()
            except Exception as exc:
                log(db, task.id, "WARNING", f"adapter.close_session 失败（{reason}，忽略继续）：{exc}")
            new_adapter = OpenCLIAdapter(
                settings,
                session=accounts[account_index].session_name,
                cdp_endpoint=_resolve_cdp_endpoint_for_account(accounts[account_index], chrome_pool),
            )
            if hasattr(new_adapter, "bind_task"):
                new_adapter.bind_task(
                    task.id,
                    run_token,
                    execution_guard=lambda: assert_execution_active(db, task.id, run_token),
                    warning_sink=lambda message: log(db, task.id, "WARNING", message),
                )
            return new_adapter

        def refresh_token_pool(entry: tuple[str, dict]) -> None:
            """token 池刷新：用 entry 的 _matched_keywords 重新跑 throttled_search，按 platform_note_id 匹配替换 URL。"""
            matched_keywords = entry[1].get("_matched_keywords") or []
            if not matched_keywords:
                return
            query = f"{entry[0]} {matched_keywords[0]}"
            log(db, task.id, "INFO", f"触发 token 池刷新：重新搜索 {query!r}")
            new_items = throttled_search(db, settings, task, adapter, query, "")
            if not new_items:
                log(db, task.id, "WARNING", "token 池刷新失败：throttled_search 返回空，跳过替换")
                return
            current_note_id = extract_platform_note_id(entry[1].get("url", ""))
            if not current_note_id:
                return
            for new_item in new_items:
                new_note_id = extract_platform_note_id(new_item.get("url", ""))
                if new_note_id == current_note_id:
                    entry[1]["url"] = new_item["url"]
                    log(db, task.id, "INFO", f"token 池刷新成功：note_id={current_note_id[:8]}... 替换为新 URL")
                    return

        attempts = settings.pipeline_stage_max_retries
        delay = settings.pipeline_stage_retry_delay_seconds

        # 阶段 1：逐篇下载 + OCR（串行，opencli 不支持并发），暂存 StagedNote
        staged_notes: list[StagedNote] = []
        empty_streak = 0  # 连续空详情熔断计数器
        empty_threshold = max(1, settings.crawl_empty_detail_threshold)  # 防 0/负数
        reset_interval = max(0, settings.crawl_session_reset_interval)  # 0 表示禁用
        for entry in results:
            if finish_stop_if_requested(db, task.id, run_token):
                return
            try:
                matched_keywords = entry[1].get("_matched_keywords")
                if matched_keywords and not title_matches_keywords(entry[1].get("title", ""), matched_keywords):
                    task.skipped_notes += 1
                    db.commit()
                    log(db, task.id, "INFO", f"标题未包含关键词，已跳过 [{entry[1]['url']}] 标题={entry[1].get('title', '')!r} 关键词={matched_keywords}")
                    continue
                staged = download_and_ocr(db, task, run_token, entry[0], entry[1], adapter, settings)
                if staged is not None:
                    # 连续空详情熔断：note.content 视为空触发风控熔断
                    if not staged.note.content or not staged.note.content.strip():
                        empty_streak += 1
                        log(db, task.id, "WARNING", f"详情为空 {empty_streak}/{empty_threshold} url={entry[1]['url']}")
                        # 阈值 - 2 时尝试 token 池刷新（默认 5 - 2 = 3），早介入避免浪费剩余缓冲
                        # 仅当 entry 带 _matched_keywords（搜索结果）才刷新；博主条目无关键词，无刷新意义
                        if empty_streak == empty_threshold - 2 and entry[1].get("_matched_keywords"):
                            old_url = entry[1]["url"]
                            refresh_token_pool(entry)
                            if entry[1]["url"] != old_url:
                                # 刷新成功：用新 URL 重抓当前 entry
                                db.rollback()
                                cleanup_incomplete_note(db, old_url)
                                retry_staged = download_and_ocr(db, task, run_token, entry[0], entry[1], adapter, settings)
                                if retry_staged is not None:
                                    if retry_staged.note.content and retry_staged.note.content.strip():
                                        log(db, task.id, "INFO", f"token 池刷新后重抓成功 url={entry[1]['url']}")
                                        empty_streak = 0
                                        staged_notes.append(retry_staged)
                                        continue
                                    else:
                                        # 重抓仍空，按空详情继续累计
                                        staged = retry_staged
                                        empty_streak += 1
                                        log(db, task.id, "WARNING", f"token 池刷新后重抓仍为空 {empty_streak}/{empty_threshold} url={entry[1]['url']}")
                        if empty_streak >= empty_threshold:
                            raise CrawlHalted(
                                f"连续 {empty_streak} 篇笔记详情为空，疑似触发小红书风控。"
                                "请在 Chrome 重新打开小红书后点击「继续抓取」"
                            )
                    else:
                        empty_streak = 0
                    staged_notes.append(staged)
                    # 周期性重置 adapter 释放 Chrome profile 累积
                    if reset_interval and len(staged_notes) % reset_interval == 0:
                        log(db, task.id, "INFO", f"已处理 {len(staged_notes)} 篇，重置 adapter 释放 Chrome profile")
                        adapter = reset_adapter_session(adapter, f"周期性 reset @ {len(staged_notes)} 篇")
                    # 多账号轮询：每抓 N 篇主动切到下一个账号（避免触发频率限制）
                    # 仅当 ≥2 个账号时切；单账号 / 默认 session 时跳过
                    rotation_n = getattr(settings, "account_rotation_notes", 25) or 0
                    if (
                        rotation_n > 0
                        and len(accounts) >= 2
                        and all(getattr(a, "cdp_port", None) is not None for a in accounts)
                        and len(staged_notes) % rotation_n == 0
                    ):
                        next_idx = (account_index + 1) % len(accounts)
                        old_name = accounts[account_index].name
                        new_name = accounts[next_idx].name
                        log(
                            db,
                            task.id,
                            "INFO",
                            f"账号轮询：每 {rotation_n} 篇切换一次，{old_name!r} → {new_name!r}（已抓 {len(staged_notes)} 篇）",
                        )
                        account_index = next_idx
                        adapter = OpenCLIAdapter(
                            settings,
                            session=accounts[account_index].session_name,
                            cdp_endpoint=_resolve_cdp_endpoint_for_account(accounts[account_index], chrome_pool),
                        )
                        if hasattr(adapter, "bind_task"):
                            adapter.bind_task(
                                task.id,
                                run_token,
                                execution_guard=lambda: assert_execution_active(db, task.id, run_token),
                                warning_sink=lambda message: log(db, task.id, "WARNING", message),
                            )
                # 正常返回（含标题不匹配/已存在等跳过）说明链路健康，连续失败计数清零
                consecutive_failures = 0
            except ExecutionStopped:
                db.rollback()
                cleanup_incomplete_note(db, entry[1]["url"])
                finish_stop_if_requested(db, task.id, run_token)
                return
            except ExecutionSuperseded:
                db.rollback()
                return
            except CrawlHalted:
                # 详情空值熔断等 CrawlHalted 由 for 循环抛出；阶段 1 不吞咽，重新向上传播
                # 让 run_crawl 顶部 except (CrawlHalted) 处理（写 PAUSED + error_message）
                raise
            except (AuthenticationRequired, VerificationRequired) as exc:
                # 当前账号失效（未登录/扫码超时/风控验证），切换到下一个账号并重试当前笔记一次。
                # 每篇笔记最多切换一次，避免死循环；retry 再失效则跳过本篇，下一篇继续用新账号。
                db.rollback()
                cleanup_incomplete_note(db, entry[1]["url"])
                account_index += 1
                if account_index >= len(accounts):
                    raise CrawlHalted(f"所有账号均已失效，请扫码登录后继续。最近错误：{exc}")
                old_name = accounts[account_index - 1].name
                new_name = accounts[account_index].name
                log(db, task.id, "INFO", f"账号 {old_name!r} 失效（{exc}），切换到 {new_name!r}")
                adapter = OpenCLIAdapter(
                    settings,
                    session=accounts[account_index].session_name,
                    cdp_endpoint=_resolve_cdp_endpoint_for_account(accounts[account_index], chrome_pool),
                )
                if hasattr(adapter, "bind_task"):
                    adapter.bind_task(
                        task.id,
                        run_token,
                        execution_guard=lambda: assert_execution_active(db, task.id, run_token),
                        warning_sink=lambda message: log(db, task.id, "WARNING", message),
                    )
                # 重试当前笔记一次
                try:
                    staged = download_and_ocr(db, task, run_token, entry[0], entry[1], adapter, settings)
                    if staged is not None:
                        staged_notes.append(staged)
                    consecutive_failures = 0
                except (AuthenticationRequired, VerificationRequired) as retry_exc:
                    # 新账号也失效，跳过本篇，下一篇继续用新账号（account_index 已增）
                    db.rollback()
                    cleanup_incomplete_note(db, entry[1]["url"])
                    log(db, task.id, "WARNING", f"切换到账号 {new_name!r} 后仍失效：{retry_exc}，跳过该笔记")
                    continue
                except ExecutionStopped:
                    db.rollback()
                    cleanup_incomplete_note(db, entry[1]["url"])
                    finish_stop_if_requested(db, task.id, run_token)
                    return
                except ExecutionSuperseded:
                    db.rollback()
                    return
                except Exception as retry_exc:
                    on_failure(entry, retry_exc)
                    continue
            except Exception as exc:
                consecutive_failures += 1
                on_failure(entry, exc)
                # 连续失败达到阈值视为系统性问题（登录态掉线/风控/opencli 异常），
                # 熔断为 PAUSED 交给用户决策，避免整批笔记逐篇失败空跑
                if consecutive_failures >= settings.consecutive_note_failure_limit:
                    raise CrawlHalted(
                        f"已连续 {consecutive_failures} 篇笔记处理失败，疑似登录态失效或触发风控。"
                        f"最近一次错误：{exc}。请检查浏览器登录/验证状态后点「检测登录并继续」，或「结束抓取」。"
                    )

        # 阶段 2：批量并行 MiniMax + 写 DB
        if staged_notes:
            if settings.minimax_api_key:
                client = MiniMaxClient(settings)
                texts = [s.combined_text for s in staged_notes]
                reference = staged_notes[0].reference_now
                try:
                    payloads = run_stage(
                        lambda: client.extract_many_parallel(texts, reference),
                        attempts, delay,
                    )
                except Exception as exc:
                    log(db, task.id, "WARNING", f"MiniMax 批量提取失败，降级规则提取：{exc}")
                    extracted_list = [extract_activities(s.combined_text, s.reference_now, None) for s in staged_notes]
                else:
                    # 复用 extract_activities 的 normalize 逻辑：llm callable 直接返回预提取的 payload
                    extracted_list = [
                        extract_activities(s.combined_text, s.reference_now, lambda _text, p=payload: p)
                        for s, payload in zip(staged_notes, payloads)
                    ]
            else:
                extracted_list = [extract_activities(s.combined_text, s.reference_now, None) for s in staged_notes]

            for staged, extracted in zip(staged_notes, extracted_list):
                if finish_stop_if_requested(db, task.id, run_token):
                    return
                try:
                    extract_and_save(db, task, run_token, staged, extracted, settings)
                except ExecutionStopped:
                    db.rollback()
                    finish_stop_if_requested(db, task.id, run_token)
                    return
                except ExecutionSuperseded:
                    db.rollback()
                    return
                except AuthenticationRequired:
                    raise
                except Exception as exc:
                    db.rollback()
                    current = db.get(CrawlTask, task.id)
                    current.failed_notes += 1
                    current.error_message = str(exc)
                    db.commit()
                    log(db, task.id, "ERROR", f"笔记保存失败 [{staged.note.source_url}]：{exc}")
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
    except (AuthenticationRequired, CrawlHalted) as exc:
        task = db.get(CrawlTask, task_id)
        task.status = "PAUSED"
        task.error_message = str(exc)
        db.commit()
        log(db, task.id, "ERROR", str(exc))
        # 未登录（whoami 超时归类）、安全验证与连续失败熔断都需要用户在浏览器里
        # 检查并完成扫码/验证，统一自动打开登录页；打开失败不影响 PAUSED 状态。
        page_kind = "验证页面" if isinstance(exc, VerificationRequired) else "登录页面，请完成扫码后点击「继续抓取」"
        try:
            open_xhs_login(settings)
            log(db, task.id, "INFO", f"已自动打开 Chrome 小红书{page_kind}")
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
        # 不释放 chrome_pool——它是全局单例，由 atexit 在后端退出时统一 release
        # 这样账号已启动的 Chrome 实例可在任务间持续运行（用户已登录的 cookie 保持有效）
        db.close()
