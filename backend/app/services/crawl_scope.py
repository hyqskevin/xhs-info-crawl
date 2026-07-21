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
from app.models.keyword_group import KeywordGroup, KeywordGroupCity, KeywordGroupWord


@dataclass
class CrawlScope:
    keywords: list[str]
    bloggers: list[Blogger]


def _resolve_from_legacy_keyword_table(db: Session, city: City) -> list[str]:
    stmt = (
        select(Keyword.word)
        .where(Keyword.city_code == city.code, Keyword.enabled.is_(True))
        .order_by(Keyword.id)
    )
    return list(db.scalars(stmt).all())


def _resolve_from_keyword_groups(
    db: Session, city: City, keyword_group_ids: list[int]
) -> list[str]:
    """根据 keyword_group_ids 求并集；只包含挂在当前城市下的组。"""
    if not keyword_group_ids:
        return []
    stmt = (
        select(KeywordGroupWord.word)
        .join(
            KeywordGroupCity,
            KeywordGroupCity.keyword_group_id == KeywordGroupWord.keyword_group_id,
        )
        .where(
            KeywordGroupWord.keyword_group_id.in_(keyword_group_ids),
            KeywordGroupCity.city_code == city.code,
            KeywordGroupWord.enabled.is_(True),
            KeywordGroupCity.enabled.is_(True),
            KeywordGroup.enabled.is_(True),
        )
        .join(
            KeywordGroup,
            KeywordGroup.id == KeywordGroupWord.keyword_group_id,
        )
    )
    return list(dict.fromkeys(db.scalars(stmt).all()))


def resolve_effective_keywords(db: Session, city: City, task_params: dict) -> list[str]:
    """规则：
    - task_params 含 "keywords" 键（旧字段） → 用任务参数
    - 否则若含 "keyword_group_ids" → 取这些组在该城市下的关键词并集
    - 都不存在 → 退回城市 enabled 关键词（兼容老调用）
    """
    if "keywords" in task_params:
        return list(task_params["keywords"] or [])
    if "keyword_group_ids" in task_params:
        ids = task_params.get("keyword_group_ids") or []
        if not isinstance(ids, list):
            return []
        words = _resolve_from_keyword_groups(db, city, ids)
        # 若 keyword_group_ids 为空列表（前端显式传空）→ 不要退回到 keyword 表
        if ids:
            return words
        return []
    return _resolve_from_legacy_keyword_table(db, city)


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
