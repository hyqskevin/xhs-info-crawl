from hashlib import sha1
from pathlib import Path
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_db
from app.core.security import require_admin
from app.models.blogger_city import BloggerCity
from app.models.blogger_group import BloggerGroup, BloggerGroupMember
from app.models.config import Blogger, City
from app.models.keyword_group import KeywordGroup, KeywordGroupCity, KeywordGroupWord
from app.services.opencli_adapter import OpenCLIAdapter
from app.services.browser_launcher import BrowserLaunchError, open_xhs_login
from app.services.blogger_import import BloggerImportError, generate_blogger_template, import_bloggers

router = APIRouter(prefix="/settings", tags=["settings"])
Admin = Annotated[dict[str, str], Depends(require_admin)]
DB = Annotated[Session, Depends(get_db)]
RecentFilter = Literal["不限", "一天内", "一周内", "半年内"]


class CityIn(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    recent_filter: RecentFilter = "一周内"
    enabled: bool = True


class KeywordGroupIn(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    description: str | None = None
    city_codes: list[str] = Field(default_factory=list)
    words: list[str] = Field(default_factory=list)
    enabled: bool = True


class KeywordGroupUpdateIn(BaseModel):
    name: str | None = None
    description: str | None = None
    enabled: bool | None = None


class KeywordGroupWordsIn(BaseModel):
    words: list[str]


class KeywordGroupCitiesIn(BaseModel):
    city_codes: list[str]


def _dump_keyword_group(db: Session, kg: KeywordGroup) -> dict:
    city_codes = sorted(
        row.city_code for row in db.scalars(
            select(KeywordGroupCity).where(KeywordGroupCity.keyword_group_id == kg.id)
        ).all()
    )
    words = sorted(
        row.word for row in db.scalars(
            select(KeywordGroupWord).where(KeywordGroupWord.keyword_group_id == kg.id)
        ).all()
    )
    return {
        "id": kg.id,
        "name": kg.name,
        "description": kg.description,
        "enabled": kg.enabled,
        "city_codes": city_codes,
        "words": words,
        "created_at": kg.created_at,
    }


@router.get("/keyword-groups")
def list_keyword_groups(city_code: str | None = None, _: Admin = None, db: DB = None) -> dict:
    stmt = select(KeywordGroup).order_by(KeywordGroup.id)
    if city_code:
        stmt = stmt.join(
            KeywordGroupCity, KeywordGroupCity.keyword_group_id == KeywordGroup.id
        ).where(KeywordGroupCity.city_code == city_code)
    groups = db.scalars(stmt.distinct()).all()
    return {
        "code": 200,
        "message": "success",
        "data": {"items": [_dump_keyword_group(db, g) for g in groups]},
    }


@router.get("/keyword-groups/{kg_id}")
def get_keyword_group(kg_id: int, _: Admin, db: DB) -> dict:
    kg = db.get(KeywordGroup, kg_id)
    if kg is None:
        raise HTTPException(404, "关键词组不存在")
    return {"code": 200, "message": "success", "data": _dump_keyword_group(db, kg)}


@router.post("/keyword-groups")
def create_keyword_group(payload: KeywordGroupIn, _: Admin, db: DB) -> dict:
    existing = db.scalar(select(KeywordGroup).where(KeywordGroup.name == payload.name))
    if existing is not None:
        raise HTTPException(409, f"关键词组名称 '{payload.name}' 已存在")

    kg = KeywordGroup(name=payload.name, description=payload.description, enabled=payload.enabled)
    db.add(kg)
    db.flush()
    for code in dict.fromkeys(payload.city_codes):
        if db.scalar(select(City).where(City.code == code)) is None:
            raise HTTPException(422, f"城市代码 '{code}' 不存在")
        db.add(KeywordGroupCity(keyword_group_id=kg.id, city_code=code, enabled=True))
    for word in dict.fromkeys(payload.words):
        if not word.strip():
            continue
        db.add(KeywordGroupWord(keyword_group_id=kg.id, word=word.strip(), enabled=True))
    db.commit()
    db.refresh(kg)
    return {"code": 200, "message": "success", "data": _dump_keyword_group(db, kg)}


@router.put("/keyword-groups/{kg_id}/words")
def replace_keyword_group_words(kg_id: int, payload: KeywordGroupWordsIn, _: Admin, db: DB) -> dict:
    kg = db.get(KeywordGroup, kg_id)
    if kg is None:
        raise HTTPException(404, "关键词组不存在")
    db.execute(delete(KeywordGroupWord).where(KeywordGroupWord.keyword_group_id == kg_id))
    for word in dict.fromkeys(payload.words):
        if not word.strip():
            continue
        db.add(KeywordGroupWord(keyword_group_id=kg_id, word=word.strip(), enabled=True))
    db.commit()
    db.refresh(kg)
    return {"code": 200, "message": "success", "data": _dump_keyword_group(db, kg)}


@router.put("/keyword-groups/{kg_id}/cities")
def replace_keyword_group_cities(kg_id: int, payload: KeywordGroupCitiesIn, _: Admin, db: DB) -> dict:
    kg = db.get(KeywordGroup, kg_id)
    if kg is None:
        raise HTTPException(404, "关键词组不存在")
    db.execute(delete(KeywordGroupCity).where(KeywordGroupCity.keyword_group_id == kg_id))
    for code in dict.fromkeys(payload.city_codes):
        if db.scalar(select(City).where(City.code == code)) is None:
            raise HTTPException(422, f"城市代码 '{code}' 不存在")
        db.add(KeywordGroupCity(keyword_group_id=kg_id, city_code=code, enabled=True))
    db.commit()
    db.refresh(kg)
    return {"code": 200, "message": "success", "data": _dump_keyword_group(db, kg)}


@router.delete("/keyword-groups/{kg_id}")
def delete_keyword_group(kg_id: int, _: Admin, db: DB) -> dict:
    kg = db.get(KeywordGroup, kg_id)
    if kg is None:
        raise HTTPException(404, "关键词组不存在")
    db.execute(delete(KeywordGroupWord).where(KeywordGroupWord.keyword_group_id == kg_id))
    db.execute(delete(KeywordGroupCity).where(KeywordGroupCity.keyword_group_id == kg_id))
    db.delete(kg)
    db.commit()
    return {"code": 200, "message": "success", "data": {"deleted_id": kg_id}}


@router.patch("/keyword-groups/{kg_id}")
def patch_keyword_group(kg_id: int, payload: KeywordGroupUpdateIn, _: Admin, db: DB) -> dict:
    """更新关键词组基础字段（name/description/enabled）。

    name 重名返回 409；其他字段为 None 时不动。
    """
    kg = db.get(KeywordGroup, kg_id)
    if kg is None:
        raise HTTPException(404, "关键词组不存在")
    if payload.name is not None and payload.name != kg.name:
        existing = db.scalar(select(KeywordGroup).where(KeywordGroup.name == payload.name))
        if existing:
            raise HTTPException(409, "关键词组名称已存在")
        kg.name = payload.name
    if payload.description is not None:
        kg.description = payload.description
    if payload.enabled is not None:
        kg.enabled = payload.enabled
    db.commit()
    db.refresh(kg)
    return {"code": 200, "message": "success", "data": _dump_keyword_group(db, kg)}


class BloggerGroupIn(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    description: str | None = None
    blogger_ids: list[int] = Field(default_factory=list)
    enabled: bool = True


class BloggerGroupMembersIn(BaseModel):
    blogger_ids: list[int] = Field(default_factory=list)


def _dump_blogger_group(db: Session, group: BloggerGroup) -> dict:
    blogger_ids = sorted(
        row.blogger_id for row in db.scalars(
            select(BloggerGroupMember).where(BloggerGroupMember.group_id == group.id)
        ).all()
    )
    return {
        "id": group.id,
        "name": group.name,
        "description": group.description,
        "enabled": group.enabled,
        "blogger_ids": blogger_ids,
        "created_at": group.created_at,
    }


def _validate_blogger_ids(db: Session, blogger_ids: list[int]) -> None:
    for blogger_id in dict.fromkeys(blogger_ids):
        if db.get(Blogger, blogger_id) is None:
            raise HTTPException(422, f"博主 id={blogger_id} 不存在")


@router.get("/blogger-groups")
def list_blogger_groups(_: Admin = None, db: DB = None) -> dict:
    groups = db.scalars(select(BloggerGroup).order_by(BloggerGroup.id)).all()
    return {
        "code": 200,
        "message": "success",
        "data": {"items": [_dump_blogger_group(db, g) for g in groups]},
    }


@router.get("/blogger-groups/{group_id}")
def get_blogger_group(group_id: int, _: Admin, db: DB) -> dict:
    group = db.get(BloggerGroup, group_id)
    if group is None:
        raise HTTPException(404, "博主组不存在")
    return {"code": 200, "message": "success", "data": _dump_blogger_group(db, group)}


@router.post("/blogger-groups")
def create_blogger_group(payload: BloggerGroupIn, _: Admin, db: DB) -> dict:
    existing = db.scalar(select(BloggerGroup).where(BloggerGroup.name == payload.name))
    if existing is not None:
        raise HTTPException(409, f"博主组名称 '{payload.name}' 已存在")
    _validate_blogger_ids(db, payload.blogger_ids)
    group = BloggerGroup(name=payload.name, description=payload.description, enabled=payload.enabled)
    db.add(group)
    db.flush()
    for blogger_id in dict.fromkeys(payload.blogger_ids):
        db.add(BloggerGroupMember(group_id=group.id, blogger_id=blogger_id))
    db.commit()
    db.refresh(group)
    return {"code": 200, "message": "success", "data": _dump_blogger_group(db, group)}


@router.put("/blogger-groups/{group_id}/members")
def replace_blogger_group_members(group_id: int, payload: BloggerGroupMembersIn, _: Admin, db: DB) -> dict:
    group = db.get(BloggerGroup, group_id)
    if group is None:
        raise HTTPException(404, "博主组不存在")
    _validate_blogger_ids(db, payload.blogger_ids)
    db.execute(delete(BloggerGroupMember).where(BloggerGroupMember.group_id == group_id))
    for blogger_id in dict.fromkeys(payload.blogger_ids):
        db.add(BloggerGroupMember(group_id=group_id, blogger_id=blogger_id))
    db.commit()
    db.refresh(group)
    return {"code": 200, "message": "success", "data": _dump_blogger_group(db, group)}


@router.delete("/blogger-groups/{group_id}")
def delete_blogger_group(group_id: int, _: Admin, db: DB) -> dict:
    group = db.get(BloggerGroup, group_id)
    if group is None:
        raise HTTPException(404, "博主组不存在")
    db.execute(delete(BloggerGroupMember).where(BloggerGroupMember.group_id == group_id))
    db.delete(group)
    db.commit()
    return {"code": 200, "message": "success", "data": {"deleted_id": group_id}}


class BloggerIn(BaseModel):
    platform_user_id: str | None = None
    username: str
    profile_url: str | None = None
    city_codes: list[str] = Field(default_factory=list)
    enabled: bool = True
    max_notes_per_crawl: int = Field(default=0, ge=0)


MODELS = {"bloggers": Blogger}
SCHEMAS = {"bloggers": BloggerIn}


def dump(item):
    return {column.name: getattr(item, column.name) for column in item.__table__.columns}


def generate_city_code(name: str, db: Session) -> str:
    base = f"city-{sha1(name.strip().encode('utf-8')).hexdigest()[:8]}"
    code = base
    suffix = 2
    while db.scalar(select(City.id).where(City.code == code)) is not None:
        code = f"{base[:29]}-{suffix}"
        suffix += 1
    return code


def dump_city(city: City, db: Session) -> dict[str, object]:
    return dump(city)


@router.get("/cities")
def list_cities(_: Admin, db: DB):
    cities = db.scalars(select(City).order_by(City.id)).all()
    return {"code": 200, "message": "success", "data": [dump_city(city, db) for city in cities]}


@router.post("/cities", status_code=status.HTTP_201_CREATED)
def create_city(payload: CityIn, _: Admin, db: DB):
    city = City(name=payload.name.strip(), code=generate_city_code(payload.name, db), recent_filter=payload.recent_filter, enabled=payload.enabled)
    db.add(city)
    db.commit()
    db.refresh(city)
    return {"code": 201, "message": "success", "data": dump_city(city, db)}


@router.put("/cities/{item_id}")
def update_city(item_id: int, payload: CityIn, _: Admin, db: DB):
    city = db.get(City, item_id)
    if city is None:
        raise HTTPException(404, "配置不存在")
    city.name = payload.name.strip()
    city.recent_filter = payload.recent_filter
    city.enabled = payload.enabled
    db.commit()
    db.refresh(city)
    return {"code": 200, "message": "success", "data": dump_city(city, db)}


@router.delete("/cities/{item_id}")
def delete_city(item_id: int, _: Admin, db: DB):
    city = db.get(City, item_id)
    if city is not None:
        db.execute(delete(BloggerCity).where(BloggerCity.city_code == city.code))
        db.execute(delete(KeywordGroupCity).where(KeywordGroupCity.city_code == city.code))
        db.delete(city)
        db.commit()
    return {"code": 200, "message": "success", "data": {"id": item_id}}


@router.get("/opencli/config")
def opencli_config(_: Admin):
    settings = get_settings()
    return {"code": 200, "message": "success", "data": {"endpoint": settings.opencli_cdp_endpoint, "target_count": settings.xhs_search_target_count, "scroll_rounds": settings.xhs_search_scroll_max_rounds}}


@router.post("/opencli/test")
def opencli_test(_: Admin):
    try:
        data = OpenCLIAdapter(get_settings()).check_login()
        return {"code": 200, "message": "连接正常", "data": data}
    except Exception as exc:
        raise HTTPException(503, str(exc)) from exc


@router.post("/opencli/open-login")
def open_login(_: Admin):
    settings = get_settings()
    try:
        url = open_xhs_login(settings)
        return {"code": 200, "message": "已打开 Chrome 小红书登录页", "data": {"url": url}}
    except BrowserLaunchError as exc:
        raise HTTPException(503, str(exc)) from exc


def _sync_blogger_cities(db: Session, blogger_id: int, city_codes: list[str]) -> None:
    """全量替换某博主的城市绑定。"""
    db.execute(delete(BloggerCity).where(BloggerCity.blogger_id == blogger_id))
    for code in city_codes:
        if code:
            db.add(BloggerCity(blogger_id=blogger_id, city_code=code, enabled=True))


def _dump_blogger_with_cities(blogger: Blogger, db: Session) -> dict:
    data = dump(blogger)
    data["city_codes"] = list(
        db.scalars(
            select(BloggerCity.city_code)
            .where(BloggerCity.blogger_id == blogger.id)
            .order_by(BloggerCity.id)
        ).all()
    )
    return data


@router.get("/bloggers/import-template")
def download_blogger_import_template(_: Admin):
    return Response(
        generate_blogger_template(),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="blogger-import-template.xlsx"'},
    )


@router.post("/bloggers/import", status_code=status.HTTP_201_CREATED)
async def import_blogger_settings(request: Request, filename: str, _: Admin, db: DB):
    content = await request.body()
    if len(content) > 2 * 1024 * 1024:
        raise HTTPException(413, "导入文件不能超过 2 MiB")
    try:
        result = import_bloggers(db, content, filename)
    except BloggerImportError as exc:
        raise HTTPException(422, str(exc)) from exc
    return {"code": 201, "message": "success", "data": result}


# ── 系统配置（.env 读写） ──

# env 字段名 → Settings 属性名映射
_ENV_KEY_MAP: dict[str, str] = {
    "minimax_api_key": "MINIMAX_API_KEY",
    "minimax_base_url": "MINIMAX_BASE_URL",
    "minimax_model": "MINIMAX_MODEL",
    "minimax_timeout_seconds": "MINIMAX_TIMEOUT_SECONDS",
    "minimax_concurrency": "MINIMAX_CONCURRENCY",
    "ocr_enabled": "OCR_ENABLED",
    "ocr_language": "OCR_LANGUAGE",
    "ocr_min_confidence": "OCR_MIN_CONFIDENCE",
    "ocr_parallel_workers": "OCR_PARALLEL_WORKERS",
    "pipeline_stage_max_retries": "PIPELINE_STAGE_MAX_RETRIES",
    "pipeline_stage_retry_delay_seconds": "PIPELINE_STAGE_RETRY_DELAY_SECONDS",
    "xhs_search_target_count": "XHS_SEARCH_TARGET_COUNT",
    "xhs_search_scroll_max_rounds": "XHS_SEARCH_SCROLL_MAX_ROUNDS",
    "xhs_scroll_pixels": "XHS_SCROLL_PIXELS",
    "xhs_scroll_stagnant_rounds": "XHS_SCROLL_STAGNANT_ROUNDS",
    "search_limit": "SEARCH_LIMIT",
    "weekly_search_limit": "WEEKLY_SEARCH_LIMIT",
    "consecutive_note_failure_limit": "CONSECUTIVE_NOTE_FAILURE_LIMIT",
    "activity_future_window_days": "ACTIVITY_FUTURE_WINDOW_DAYS",
    "opencli_bin": "OPENCLI_BIN",
}


class SystemConfigIn(BaseModel):
    """系统配置更新请求，所有字段可选。"""
    minimax_api_key: str | None = None
    minimax_base_url: str | None = None
    minimax_model: str | None = None
    minimax_timeout_seconds: int | None = None
    minimax_concurrency: int | None = None
    ocr_enabled: bool | None = None
    ocr_language: str | None = None
    ocr_min_confidence: float | None = None
    ocr_parallel_workers: int | None = None
    pipeline_stage_max_retries: int | None = None
    pipeline_stage_retry_delay_seconds: float | None = None
    xhs_search_target_count: int | None = None
    xhs_search_scroll_max_rounds: int | None = None
    xhs_scroll_pixels: int | None = None
    xhs_scroll_stagnant_rounds: int | None = None
    search_limit: int | None = None
    weekly_search_limit: int | None = None
    consecutive_note_failure_limit: int | None = None
    activity_future_window_days: int | None = None
    opencli_bin: str | None = None


def _read_system_config(settings) -> dict[str, Any]:
    """从 Settings 实例读取所有可配置项。"""
    return {
        key: getattr(settings, key)
        for key in _ENV_KEY_MAP
    }


def _update_env_file(env_path: str, updates: dict[str, str]) -> None:
    """更新 .env 文件：已存在的 key 替换值，不存在的 key 追加到末尾。保留注释和空行。"""
    path = Path(env_path)
    lines: list[str] = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    updated_keys: set[str] = set()

    new_lines: list[str] = []
    for line in lines:
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and "=" in stripped:
            key = stripped.split("=", 1)[0].strip()
            if key in updates:
                new_lines.append(f"{key}={updates[key]}")
                updated_keys.add(key)
                continue
        new_lines.append(line)

    # 追加未覆盖的新 key
    for key, value in updates.items():
        if key not in updated_keys:
            new_lines.append(f"{key}={value}")

    path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")


def _env_path_from_settings() -> str:
    """从 Settings 的 model_config 中获取 .env 文件路径。"""
    settings = get_settings()
    env_file = settings.model_config.get("env_file", ".env")
    if isinstance(env_file, (str, Path)):
        return str(env_file)
    return ".env"


@router.get("/system-config")
def get_system_config(_: Admin):
    """返回当前所有系统配置项。"""
    settings = get_settings()
    return {"code": 200, "message": "success", "data": _read_system_config(settings)}


@router.put("/system-config")
def update_system_config(payload: SystemConfigIn, _: Admin):
    """更新系统配置，写入 .env 文件。"""
    updates: dict[str, str] = {}
    for field_name, env_key in _ENV_KEY_MAP.items():
        value = getattr(payload, field_name, None)
        if value is not None:
            updates[env_key] = str(value).lower() if isinstance(value, bool) else str(value)

    if not updates:
        raise HTTPException(422, "没有需要更新的字段")

    env_path = _env_path_from_settings()
    _update_env_file(env_path, updates)

    # 同步 os.environ：pydantic_settings 优先级 os.environ > .env，
    # 若不同步，uvicorn 启动时 source .env 注入的旧值会覆盖 .env 文件新值
    import os
    for env_key, raw_value in updates.items():
        os.environ[env_key] = raw_value

    # 重新加载 settings 以返回最新值
    from app.core.config import get_settings as _gs
    _gs.cache_clear()
    settings = get_settings()
    return {"code": 200, "message": "success", "data": _read_system_config(settings)}


@router.get("/{kind}")
def list_settings(kind: Literal["bloggers"], _: Admin, db: DB):
    if kind == "bloggers":
        rows = db.scalars(select(Blogger).order_by(Blogger.id)).all()
        return {"code": 200, "message": "success", "data": [_dump_blogger_with_cities(b, db) for b in rows]}
    rows = db.scalars(select(MODELS[kind]).order_by(MODELS[kind].id)).all()
    return {"code": 200, "message": "success", "data": [dump(row) for row in rows]}


@router.post("/{kind}", status_code=status.HTTP_201_CREATED)
def create_setting(kind: Literal["bloggers"], payload: dict, _: Admin, db: DB):
    data = SCHEMAS[kind].model_validate(payload)
    fields = data.model_dump()
    if kind == "bloggers":
        city_codes = fields.pop("city_codes", [])
        fields.pop("city_code", None)  # 兼容旧字段（如有）
        item = Blogger(**fields)
    else:
        item = MODELS[kind](**fields)
    db.add(item)
    db.flush()
    if kind == "bloggers":
        _sync_blogger_cities(db, item.id, city_codes)
    db.commit()
    db.refresh(item)
    if kind == "bloggers":
        return {"code": 201, "message": "success", "data": _dump_blogger_with_cities(item, db)}
    return {"code": 201, "message": "success", "data": dump(item)}


@router.put("/{kind}/{item_id}")
def update_setting(kind: Literal["bloggers"], item_id: int, payload: dict, _: Admin, db: DB):
    item = db.get(MODELS[kind], item_id)
    if item is None:
        raise HTTPException(404, "配置不存在")
    data = SCHEMAS[kind].model_validate(payload)
    fields = data.model_dump()
    if kind == "bloggers":
        city_codes = fields.pop("city_codes", None)
        fields.pop("city_code", None)
        for key, value in fields.items():
            setattr(item, key, value)
        if city_codes is not None:
            _sync_blogger_cities(db, item.id, city_codes)
    else:
        for key, value in fields.items():
            setattr(item, key, value)
    db.commit()
    db.refresh(item)
    if kind == "bloggers":
        return {"code": 200, "message": "success", "data": _dump_blogger_with_cities(item, db)}
    return {"code": 200, "message": "success", "data": dump(item)}


@router.post("/bloggers/{item_id}/enrich")
def enrich_blogger(item_id: int, _: Admin, db: DB):
    """按博主用户名调用 opencli search，回填 platform_user_id 与 profile_url。

    仅当 profile_url 为空时才需要补充；已配置完整的返回 200 + 不变数据。
    """
    from app.services.blogger_enricher import enrich_bloggers
    from app.services.opencli_adapter import OpenCLIAdapter

    item = db.get(Blogger, item_id)
    if item is None:
        raise HTTPException(404, "博主不存在")
    if (item.profile_url or "").strip():
        return {"code": 200, "message": "博主信息已完整，无需补充", "data": _dump_blogger_with_cities(item, db)}

    def runner(args: list[str]) -> list[dict]:
        adapter = OpenCLIAdapter(get_settings())
        result = adapter.run(args)
        if isinstance(result, list):
            return result
        if isinstance(result, dict) and "items" in result:
            return list(result["items"])
        return []

    try:
        filled = enrich_bloggers(db, [item], search_runner=runner, limit=5)
    except Exception as exc:
        raise HTTPException(503, f"补充失败：{exc}") from exc

    db.refresh(item)
    if not filled:
        raise HTTPException(422, f"未找到匹配 '{item.username}' 的博主主页")
    return {"code": 200, "message": "success", "data": _dump_blogger_with_cities(item, db)}


@router.delete("/{kind}/{item_id}")
def delete_setting(kind: Literal["bloggers"], item_id: int, _: Admin, db: DB):
    item = db.get(MODELS[kind], item_id)
    if item is not None:
        if kind == "bloggers":
            db.execute(delete(BloggerCity).where(BloggerCity.blogger_id == item.id))
            db.execute(delete(BloggerGroupMember).where(BloggerGroupMember.blogger_id == item.id))
        db.delete(item)
        db.commit()
    return {"code": 200, "message": "success", "data": {"id": item_id}}
