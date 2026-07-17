from hashlib import sha1
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_db
from app.core.security import require_admin
from app.models.config import Blogger, City, Keyword
from app.services.opencli_adapter import OpenCLIAdapter

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
    platform_user_id: str
    username: str
    profile_url: str
    city_code: str
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


@router.get("/{kind}")
def list_settings(kind: Literal["keywords", "bloggers"], _: Admin, db: DB):
    rows = db.scalars(select(MODELS[kind]).order_by(MODELS[kind].id)).all()
    return {"code": 200, "message": "success", "data": [dump(row) for row in rows]}


@router.post("/{kind}", status_code=status.HTTP_201_CREATED)
def create_setting(kind: Literal["keywords", "bloggers"], payload: dict, _: Admin, db: DB):
    data = SCHEMAS[kind].model_validate(payload)
    item = MODELS[kind](**data.model_dump())
    db.add(item)
    db.commit()
    db.refresh(item)
    return {"code": 201, "message": "success", "data": dump(item)}


@router.put("/{kind}/{item_id}")
def update_setting(kind: Literal["keywords", "bloggers"], item_id: int, payload: dict, _: Admin, db: DB):
    item = db.get(MODELS[kind], item_id)
    if item is None:
        raise HTTPException(404, "配置不存在")
    data = SCHEMAS[kind].model_validate(payload)
    for key, value in data.model_dump().items():
        setattr(item, key, value)
    db.commit()
    db.refresh(item)
    return {"code": 200, "message": "success", "data": dump(item)}


@router.delete("/{kind}/{item_id}")
def delete_setting(kind: Literal["keywords", "bloggers"], item_id: int, _: Admin, db: DB):
    item = db.get(MODELS[kind], item_id)
    if item is not None:
        db.delete(item)
        db.commit()
    return {"code": 200, "message": "success", "data": {"id": item_id}}
