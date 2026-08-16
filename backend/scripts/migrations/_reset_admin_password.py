"""一次性脚本:重置 admin 密码为 Admin@123。

使用场景:用户忘记 admin 密码(尤其打包版启动器自动生成随机密码后),
无法登录管理后台。

执行方式:
    cd backend && .venv/bin/python scripts/migrations/_reset_admin_password.py

幂等:可重复执行,每次都把 admin 密码重置为 Admin@123。

关联 spec: docs/superpowers/specs/2026-08-10-one-click-packaging-design.md § 14.3
(打包版启动器自动生成 INITIAL_ADMIN_PASSWORD 但展示不友好)
"""
from __future__ import annotations

import sys
from pathlib import Path

# 把 backend 加进 sys.path
BACKEND_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BACKEND_ROOT))

from app.core.database import SessionLocal
from app.core.security import hash_password
from app.models.user import User


def main() -> int:
    session = SessionLocal()
    try:
        admin = session.query(User).filter(User.username == "admin").first()
        if admin is None:
            print("ERROR: admin 用户不存在。请先执行 alembic upgrade head", file=sys.stderr)
            return 1

        admin.password_hash = hash_password("Admin@123")
        # 顺手把 enabled=1(防止之前被某个迁移脚本禁用)
        admin.enabled = True
        session.commit()
        print("已重置 admin 密码为: Admin@123")
        print("请登录后立刻修改密码(管理后台 -> 操作账号 -> admin -> 修改密码)")
        return 0
    except Exception as exc:
        session.rollback()
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    finally:
        session.close()


if __name__ == "__main__":
    raise SystemExit(main())