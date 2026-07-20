"""抓取范围计算：根据 task_params 与城市 enabled 配置生成最终的
关键词列表与博主列表。

调用方：
- run_crawl：拿到 effective_keywords / effective_bloggers 后真正执行抓取。
- tasks.py:crawl：入口校验，二者都为空时 422。
"""

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.blogger_city import BloggerCity
from app.models.config import Blogger, City, Keyword


@dataclass
class CrawlScope:
    keywords: list[str]
    bloggers: list[Blogger]


def resolve_effective_keywords(db: Session, city: City, task_params: dict) -> list[str]:
    """规则：
    - task_params 含 "keywords" 键（无论值是否为空列表） → 用任务参数
    - 否则 → 取城市 enabled 关键词
    """
    if "keywords" in task_params:
        return list(task_params["keywords"] or [])
    stmt = (
        select(Keyword.word)
        .where(Keyword.city_code == city.code, Keyword.enabled.is_(True))
        .order_by(Keyword.id)
    )
    return list(db.scalars(stmt).all())


def resolve_effective_bloggers(db: Session, city: City, task_params: dict) -> list[Blogger]:
    """规则：
    - task_params 含 "blogger_ids" 键 → 按 ID 过滤并校验 blogger_cities + enabled
    - 否则 → 取城市 enabled 博主（基于 blogger_cities 多对多表）
    """
    if "blogger_ids" in task_params:
        ids = task_params["blogger_ids"] or []
        if not ids:
            return []
        stmt = (
            select(Blogger)
            .join(BloggerCity, BloggerCity.blogger_id == Blogger.id)
            .where(
                Blogger.id.in_(ids),
                BloggerCity.city_code == city.code,
                BloggerCity.enabled.is_(True),
                Blogger.enabled.is_(True),
            )
            .order_by(Blogger.id)
        )
    else:
        stmt = (
            select(Blogger)
            .join(BloggerCity, BloggerCity.blogger_id == Blogger.id)
            .where(
                BloggerCity.city_code == city.code,
                BloggerCity.enabled.is_(True),
                Blogger.enabled.is_(True),
            )
            .order_by(Blogger.id)
        )
    return list(db.scalars(stmt).all())


def resolve_crawl_scope(db: Session, city: City, task_params: dict) -> CrawlScope:
    return CrawlScope(
        keywords=resolve_effective_keywords(db, city, task_params),
        bloggers=resolve_effective_bloggers(db, city, task_params),
    )
