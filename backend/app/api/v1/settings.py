from hashlib import sha1
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_db
from app.core.security import require_admin
from app.models.blogger_city import BloggerCity
from app.models.config import Blogger, City, Keyword
from app.services.opencli_adapter import OpenCLIAdapter
from app.services.browser_launcher import BrowserLaunchError, open_xhs_login

router = APIRouter(prefix="/settings", tags=["settings"])
Admin = Annotated[dict[str, str], Depends(require_admin)]
DB = Annotated[Session, Depends(get_db)]
RecentFilter = Literal["不限", "一天内", "一周内", "半年内"]


class CityIn(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    keywords: list[str] = Field(default_factory=list)
    recent_filter: RecentFilter = "一周内"
    enabled: bool = True


class KeywordIn(BaseModel):
    word: str
    city_code: str
    enabled: bool = True


class BloggerIn(BaseModel):
    platform_user_id: str | None = None
    username: str
    profile_url: str | None = None
    city_codes: list[str] = Field(default_factory=list)
    enabled: bool = True


MODELS = {"keywords": Keyword, "bloggers": Blogger}
SCHEMAS = {"keywords": KeywordIn, "bloggers": BloggerIn}


def dump(item):
    return {column.name: getattr(item, column.name) for column in item.__table__.columns}


def normalize_keywords(values: list[str]) -> list[str]:
    return list(dict.fromkeys(value.strip() for value in values if value.strip()))


def generate_city_code(name: str, db: Session) -> str:
    base = f"city-{sha1(name.strip().encode('utf-8')).hexdigest()[:8]}"
    code = base
    suffix = 2
    while db.scalar(select(City.id).where(City.code == code)) is not None:
        code = f"{base[:29]}-{suffix}"
        suffix += 1
    return code


def dump_city(city: City, db: Session) -> dict[str, object]:
    data = dump(city)
    data["keywords"] = list(db.scalars(select(Keyword.word).where(Keyword.city_code == city.code).order_by(Keyword.id)).all())
    return data


def sync_keywords(db: Session, city_code: str, words: list[str], enabled: bool) -> None:
    db.execute(delete(Keyword).where(Keyword.city_code == city_code))
    db.add_all(Keyword(word=word, city_code=city_code, enabled=enabled) for word in normalize_keywords(words))


@router.get("/cities")
def list_cities(_: Admin, db: DB):
    cities = db.scalars(select(City).order_by(City.id)).all()
    return {"code": 200, "message": "success", "data": [dump_city(city, db) for city in cities]}


@router.post("/cities", status_code=status.HTTP_201_CREATED)
def create_city(payload: CityIn, _: Admin, db: DB):
    city = City(name=payload.name.strip(), code=generate_city_code(payload.name, db), recent_filter=payload.recent_filter, enabled=payload.enabled)
    db.add(city)
    db.flush()
    sync_keywords(db, city.code, payload.keywords, payload.enabled)
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
    sync_keywords(db, city.code, payload.keywords, payload.enabled)
    db.commit()
    db.refresh(city)
    return {"code": 200, "message": "success", "data": dump_city(city, db)}


@router.delete("/cities/{item_id}")
def delete_city(item_id: int, _: Admin, db: DB):
    city = db.get(City, item_id)
    if city is not None:
        db.execute(delete(Keyword).where(Keyword.city_code == city.code))
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


@router.get("/{kind}")
def list_settings(kind: Literal["keywords", "bloggers"], _: Admin, db: DB):
    if kind == "bloggers":
        rows = db.scalars(select(Blogger).order_by(Blogger.id)).all()
        return {"code": 200, "message": "success", "data": [_dump_blogger_with_cities(b, db) for b in rows]}
    rows = db.scalars(select(MODELS[kind]).order_by(MODELS[kind].id)).all()
    return {"code": 200, "message": "success", "data": [dump(row) for row in rows]}


@router.post("/{kind}", status_code=status.HTTP_201_CREATED)
def create_setting(kind: Literal["keywords", "bloggers"], payload: dict, _: Admin, db: DB):
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
def update_setting(kind: Literal["keywords", "bloggers"], item_id: int, payload: dict, _: Admin, db: DB):
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
def delete_setting(kind: Literal["keywords", "bloggers"], item_id: int, _: Admin, db: DB):
    item = db.get(MODELS[kind], item_id)
    if item is not None:
        db.delete(item)
        db.commit()
    return {"code": 200, "message": "success", "data": {"id": item_id}}
