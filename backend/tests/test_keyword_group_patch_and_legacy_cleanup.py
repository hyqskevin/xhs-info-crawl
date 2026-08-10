"""关键词组 PATCH 端点 + legacy keywords 清理测试。

关联 spec: docs/superpowers/specs/2026-08-10-keyword-group-cleanup-and-bugfix-design.md
"""
from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.core.database import SessionLocal, engine
from app.core.security import create_access_token
from app.models.config import City
from app.models.keyword_group import KeywordGroup, KeywordGroupCity, KeywordGroupWord
from sqlalchemy import delete, inspect, select


@pytest.fixture(scope="module")
def client():
    from app.main import app
    return TestClient(app)


@pytest.fixture(autouse=True)
def auth_header():
    """生成真实 JWT token 绕过鉴权。"""
    return {"Authorization": f"Bearer {create_access_token({'sub': 'admin', 'role': 'admin'})}"}


def _unique_name(prefix: str = "test") -> str:
    """生成唯一名称避免 UNIQUE 约束冲突。"""
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


API_PREFIX = "/api/v1"


# ============================================================
# 1. PATCH /keyword-groups/{id} 端点测试
# ============================================================


class TestPatchKeywordGroup:
    """验证 PATCH 端点可更新 name/description/enabled。"""

    def test_patch_updates_name(self, client, auth_header):
        """PATCH 应能更新关键词组名称。"""
        old_name = _unique_name("patch-name-old")
        new_name = _unique_name("patch-name-new")
        db = SessionLocal()
        try:
            kg = KeywordGroup(name=old_name, description="d", enabled=True)
            db.add(kg)
            db.commit()
            db.refresh(kg)
            kg_id = kg.id
        finally:
            db.close()

        resp = client.patch(
            f"{API_PREFIX}/settings/keyword-groups/{kg_id}",
            json={"name": new_name},
            headers=auth_header,
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()["data"]
        assert data["name"] == new_name

        db = SessionLocal()
        try:
            kg = db.get(KeywordGroup, kg_id)
            if kg:
                db.delete(kg)
                db.commit()
        finally:
            db.close()

    def test_patch_updates_description(self, client, auth_header):
        """PATCH 应能更新说明。"""
        db = SessionLocal()
        try:
            kg = KeywordGroup(name=_unique_name("patch-desc"), description="old", enabled=True)
            db.add(kg)
            db.commit()
            db.refresh(kg)
            kg_id = kg.id
        finally:
            db.close()

        resp = client.patch(
            f"{API_PREFIX}/settings/keyword-groups/{kg_id}",
            json={"description": "new description"},
            headers=auth_header,
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["description"] == "new description"

        db = SessionLocal()
        try:
            db.delete(db.get(KeywordGroup, kg_id))
            db.commit()
        finally:
            db.close()

    def test_patch_updates_enabled(self, client, auth_header):
        """PATCH 应能更新启用状态。"""
        db = SessionLocal()
        try:
            kg = KeywordGroup(name=_unique_name("patch-enabled"), enabled=True)
            db.add(kg)
            db.commit()
            db.refresh(kg)
            kg_id = kg.id
        finally:
            db.close()

        resp = client.patch(
            f"{API_PREFIX}/settings/keyword-groups/{kg_id}",
            json={"enabled": False},
            headers=auth_header,
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["enabled"] is False

        db = SessionLocal()
        try:
            db.delete(db.get(KeywordGroup, kg_id))
            db.commit()
        finally:
            db.close()

    def test_patch_duplicateName_returns_409(self, client, auth_header):
        """name 重名应返回 409。"""
        keep_name = _unique_name("dup-keep")
        db = SessionLocal()
        try:
            kg1 = KeywordGroup(name=keep_name, enabled=True)
            kg2 = KeywordGroup(name=_unique_name("dup-target"), enabled=True)
            db.add_all([kg1, kg2])
            db.commit()
            db.refresh(kg2)
            kg2_id = kg2.id
        finally:
            db.close()

        resp = client.patch(
            f"{API_PREFIX}/settings/keyword-groups/{kg2_id}",
            json={"name": keep_name},
            headers=auth_header,
        )
        assert resp.status_code == 409

        db = SessionLocal()
        try:
            db.execute(delete(KeywordGroup).where(KeywordGroup.id.in_([kg2_id])))
            db.commit()
        finally:
            db.close()

    def test_patch_nonexistent_returns_404(self, client, auth_header):
        """不存在的 ID 返回 404。"""
        resp = client.patch(
            f"{API_PREFIX}/settings/keyword-groups/999999",
            json={"name": "whatever"},
            headers=auth_header,
        )
        assert resp.status_code == 404


# ============================================================
# 2. legacy keywords 清理测试
# ============================================================


class TestLegacyKeywordsCleanup:
    """验证 legacy keywords 表/模型/兜底逻辑已删除。"""

    def test_keyword_model_removed(self):
        """app.models.config 不应再导出 Keyword 类。"""
        import app.models.config as config_module
        assert not hasattr(config_module, "Keyword"), "Keyword 模型应已删除"

    def test_legacy_resolve_function_removed(self):
        """crawl_scope 不应再有 _resolve_from_legacy_keyword_table 函数。"""
        import app.services.crawl_scope as scope_module
        assert not hasattr(scope_module, "_resolve_from_legacy_keyword_table"), (
            "_resolve_from_legacy_keyword_table 应已删除"
        )

    def test_resolve_effective_keywords_no_legacy_fallback(self):
        """resolve_effective_keywords 不应再走 legacy 兜底分支。"""
        from app.services.crawl_scope import resolve_effective_keywords
        db = SessionLocal()
        try:
            city = db.scalar(select(City).limit(1))
            if city is None:
                pytest.skip("无城市数据")
            # 两个键都不传时，不应再退回 legacy 表，应返回空列表
            result = resolve_effective_keywords(db, city, {})
            assert result == [], "无 keywords 和 keyword_group_ids 时应返回空列表"
        finally:
            db.close()

    def test_keywords_table_dropped(self):
        """keywords 表应已从 DB 删除。"""
        inspector = inspect(engine)
        tables = inspector.get_table_names()
        assert "keywords" not in tables, "keywords 表应已 drop"
