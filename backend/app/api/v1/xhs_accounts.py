"""多小红书账号配置 CRUD + check-login 端点。

关联 spec:
- docs/superpowers/specs/2026-08-10-multi-xhs-account-design.md
- docs/superpowers/specs/2026-08-12-xhs-account-registration.md
"""
import re
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_db
from app.core.security import require_admin
from app.models.xhs_account import XhsAccount
from app.services.audit import record_audit
from app.services.crawler import AuthenticationRequired, VerificationRequired
from app.services.opencli_adapter import OpenCLIAdapter
from app.services.chrome_pool import ChromePool, ChromeLaunchError, get_global_chrome_pool

router = APIRouter(prefix="/xhs-accounts", tags=["xhs-accounts"])
Admin = Annotated[dict[str, str], Depends(require_admin)]


# ── 工具函数 ──────────────────────────────────────────────────────────────


_SLUG_RE = re.compile(r"[^a-z0-9]+")


def _slugify(name: str) -> str:
    """从 name 派生 session_name 候选：小写 + 仅保留 [a-z0-9] + 折叠连续分隔符 + 去首尾分隔符。

    例: "hanamaki" → "hanamaki"；"测试 账号" → ""；"My Account!" → "my-account"
    """
    slug = _SLUG_RE.sub("-", name.strip().lower()).strip("-")
    return slug


def _next_available_session_name(db: Session, name: str) -> str:
    """根据 name 自动生成不重复的 session_name（xhs-<slug> 或 xhs-<slug>-N）。

    - 第一个同名：xhs-<slug>
    - 重名：xhs-<slug>-2、-3、...
    - 若 name slugify 后为空（纯中文/空格）：使用 xhs-account-<id> 兜底
    """
    base_slug = _slugify(name)
    if not base_slug:
        # name 全部是非 ASCII 字符（中文）→ 取 XhsAccount 表当前最大 id + 1 作为兜底后缀
        max_id = db.scalar(select(XhsAccount.id).order_by(XhsAccount.id.desc())) or 0
        base_slug = f"account-{max_id + 1}"
    candidate = f"xhs-{base_slug}"
    existing = set(
        db.scalars(
            select(XhsAccount.session_name).where(XhsAccount.session_name.like(f"{candidate}%"))
        ).all()
    )
    if candidate not in existing:
        return candidate
    n = 2
    while f"{candidate}-{n}" in existing:
        n += 1
    return f"{candidate}-{n}"
DB = Annotated[Session, Depends(get_db)]


_CDP_PORT_START = 9223
_CDP_PORT_RANGE = 100  # 与 chrome_pool.py 同口径：9223-9322 范围分配


def _next_available_cdp_port(db: Session) -> int:
    """从 9223 开始扫描，跳过已被占用的端口，返回第一个空闲端口。"""
    used = set(
        db.scalars(
            select(XhsAccount.cdp_port).where(XhsAccount.cdp_port.is_not(None))
        ).all()
    )
    for offset in range(_CDP_PORT_RANGE):
        candidate = _CDP_PORT_START + offset
        if candidate not in used:
            return candidate
    raise HTTPException(507, "CDP 端口池（9223-9322）已用尽，请先禁用部分账号")


class XhsAccountIn(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    remark: str = Field(default="", max_length=256)
    # 可选：不填则按 name 自动生成 xhs-<slug>（重名追加 -2/-3）
    session_name: str | None = Field(default=None, min_length=1, max_length=64)
    # 小红书用户 ID；可手动填，也可由 check-login 调 whoami 自动覆盖
    platform_user_id: str | None = Field(default=None, max_length=64)
    enabled: bool = True
    priority: int = 0


class XhsAccountUpdateIn(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=64)
    remark: str | None = Field(default=None, max_length=256)
    # 高级字段：允许用户事后绑定/修改小红书用户 ID
    platform_user_id: str | None = Field(default=None, max_length=64)
    enabled: bool | None = None
    priority: int | None = None


def _dump(account: XhsAccount) -> dict[str, Any]:
    return {
        "id": account.id,
        "name": account.name,
        "remark": account.remark,
        "session_name": account.session_name,
        "platform_user_id": account.platform_user_id,
        "login_status": account.login_status,
        "enabled": account.enabled,
        "priority": account.priority,
        "created_at": account.created_at,
        "updated_at": account.updated_at,
    }


@router.get("")
def list_xhs_accounts(_: Admin, db: DB) -> dict:
    rows = db.scalars(
        select(XhsAccount).order_by(XhsAccount.priority, XhsAccount.id)
    ).all()
    # 与 /settings/{kind} 口径一致：data 直接返回数组，前端 rows.value = res.data.data
    return {"code": 200, "message": "success", "data": [_dump(r) for r in rows]}


@router.post("", status_code=status.HTTP_201_CREATED)
def create_xhs_account(payload: XhsAccountIn, _: Admin, db: DB) -> dict:
    # session_name 不填 → 自动按 name 生成 xhs-<slug>（重名追加 -2/-3）
    # 显式传入 → 校验唯一性
    if payload.session_name:
        existing = db.scalar(
            select(XhsAccount).where(XhsAccount.session_name == payload.session_name)
        )
        if existing is not None:
            raise HTTPException(409, f"session_name '{payload.session_name}' 已存在")
        session_name = payload.session_name
    else:
        session_name = _next_available_session_name(db, payload.name)
    account = XhsAccount(
        name=payload.name,
        remark=payload.remark,
        session_name=session_name,
        platform_user_id=payload.platform_user_id,
        enabled=payload.enabled,
        priority=payload.priority,
        cdp_port=_next_available_cdp_port(db),
    )
    db.add(account)
    db.commit()
    db.refresh(account)
    return {"code": 201, "message": "success", "data": _dump(account)}


@router.put("/{account_id}")
def update_xhs_account(account_id: int, payload: XhsAccountUpdateIn, _: Admin, db: DB) -> dict:
    account = db.get(XhsAccount, account_id)
    if account is None:
        raise HTTPException(404, "账号不存在")
    if payload.name is not None:
        account.name = payload.name
    if payload.remark is not None:
        account.remark = payload.remark
    if payload.platform_user_id is not None:
        account.platform_user_id = payload.platform_user_id or None
    if payload.enabled is not None:
        account.enabled = payload.enabled
    if payload.priority is not None:
        account.priority = payload.priority
    db.commit()
    db.refresh(account)
    return {"code": 200, "message": "success", "data": _dump(account)}


@router.delete("/{account_id}")
def delete_xhs_account(account_id: int, _: Admin, db: DB) -> dict:
    account = db.get(XhsAccount, account_id)
    if account is None:
        # 修复(2026-09-01 P2 #5): 与 batch_delete_xhs_accounts 404 语义对齐,
        # 不存在资源直接 404,避免前端误以为删除成功。
        raise HTTPException(404, "账号不存在")
    db.delete(account)
    db.commit()
    return {"code": 200, "message": "success", "data": {"id": account_id}}


# ── 批量删除 ──────────────────────────────────────────────────────────────


class BatchDeleteIdsIn(BaseModel):
    ids: list[int] = Field(min_length=1, max_length=500)


class BatchDeleteOut(BaseModel):
    deleted_count: int


@router.post("/batch-delete", response_model=BatchDeleteOut)
def batch_delete_xhs_accounts(
    payload: BatchDeleteIdsIn,
    request: Request,
    actor: Admin,
    db: DB,
):
    """批量删除小红书账号配置。

    无关联表清理（XhsAccount 无外键关联）。部分 id 不存在 → 404 整体回滚。

    关联 spec: docs/superpowers/specs/2026-08-13-settings-batch-delete-design.md §2.1
    """
    rows = db.scalars(select(XhsAccount).where(XhsAccount.id.in_(payload.ids))).all()
    if len(rows) != len(set(payload.ids)):
        raise HTTPException(404, "部分账号不存在，已取消")
    deleted_ids = [r.id for r in rows]
    for r in rows:
        db.delete(r)
    db.commit()
    record_audit(
        actor_user_id=None,
        actor_username=actor["username"],
        action="xhs_accounts_batch_deleted",
        resource_type="xhs_account",
        target_label=f"batch of {len(deleted_ids)}",
        method="POST",
        path="/api/v1/xhs-accounts/batch-delete",
        status_code=200,
        client_ip=request.client.host if request.client else "127.0.0.1",
        extra={"deleted_ids": deleted_ids, "deleted_count": len(deleted_ids)},
    )
    return BatchDeleteOut(deleted_count=len(rows))


@router.post("/{account_id}/check-login")
def check_login(account_id: int, _: Admin, db: DB) -> dict:
    """检查指定账号的登录状态（2026-08-24 改用 profile_alias 走 opencli --profile 通道）。

    流程：
    1. 设 login_status='logging_in'（中间态,前端可轮询显示「正在检查」）
    2. 构造 OpenCLIAdapter: session=account.session_name, profile_alias=account.session_name
       （session_name 直接作为 opencli profile 别名;零 schema 改动）
    3. 调 adapter.check_login() —— 经 browser <session> eval 读 RWP_LOGIN_TOKEN.uid
       （不再依赖 xiaohongshu whoami,实测后者返回硬编码假账号）
    4. 成功：login_status='logged_in' + 自动落库 platform_user_id
       未登录：login_status='logged_out'
       其他异常：503

    cdp_endpoint / ChromePool 仍保留作为向后兼容 fallback —— 当 profile_alias 通道
    失败或 ChromePool 路线被强制启用时,cdp_endpoint 仍可用。
    """
    account = db.get(XhsAccount, account_id)
    if account is None:
        raise HTTPException(404, "账号不存在")
    settings = get_settings()

    # 2. profile_alias 通道:session_name 直接当 opencli alias 用
    # （spec 2026-08-24 §3.1 决定 — 零 schema 改动）
    profile_alias = account.session_name
    # 向后兼容:如有 cdp_port 也仍可走 CDP 通道作为兜底（不影响主路径）
    cdp_endpoint = (
        f"http://127.0.0.1:{account.cdp_port}"
        if account.cdp_port is not None
        else None
    )
    if account.cdp_port is not None:
        # 探测只读：用 .get()（不启动 Chrome）。没实例时先探测 DB 端口——
        # 后端重启会清 pool 内存态，但账号的 Chrome 可能还活着（持久化登录态仍在），
        # 此时 adopt 复用后走真实探测；端口确实无活 Chrome → not_started。
        # 用户主动「扫码登录」才走 acquire() 启动 Chrome。
        chrome_pool = get_global_chrome_pool()
        existing = chrome_pool.get(account.session_name)
        if existing is None or not existing.alive():
            from app.services.opencli_extension import cdp_version_ok
            if cdp_version_ok(account.cdp_port):
                chrome_pool.adopt_existing(account.session_name, account.cdp_port)
            else:
                # not_started ≠ 未登录：Chrome 关了不代表登录态丢了（profile 持久）。
                # 已有 logged_in 时不覆盖，避免"明明登录了却显示未登录"
                if account.login_status != "logged_in":
                    account.login_status = "not_started"
                    db.commit()
                    db.refresh(account)
                return {
                    "code": 200, "message": "success",
                    "data": {
                        **_dump(account),
                        "logged_in": False,
                        "reason": "not_started",
                    },
                }
    try:
        # 走真实探测才设 logging_in 中间态（not_started 快路径不碰登录态）
        account.login_status = "logging_in"
        db.commit()
        db.refresh(account)
        adapter = OpenCLIAdapter(
            settings,
            session=account.session_name,
            cdp_endpoint=cdp_endpoint,
            profile_alias=profile_alias,
        )
        raw = adapter.check_login(foreground=True, timeout=8)
        account.login_status = "logged_in"
        # check_login 现在返 {logged_in, uid, user_id, ...} —— user_id 由实现映射自 uid
        user_id = (raw or {}).get("user_id") or (raw or {}).get("uid")
        if user_id and not account.platform_user_id:
            account.platform_user_id = str(user_id)
        db.commit()
        db.refresh(account)
        return {
            "code": 200, "message": "success",
            "data": {**_dump(account), "logged_in": True, "raw": raw},
        }
    except (AuthenticationRequired, VerificationRequired) as exc:
        account.login_status = "logged_out"
        db.commit()
        db.refresh(account)
        return {
            "code": 200, "message": "success",
            "data": {**_dump(account), "logged_in": False, "error": str(exc)},
        }
    except Exception as exc:
        # 异常时不改 login_status（保留 logging_in 让前端继续轮询?或者改回 unknown）
        # 这里改回 unknown — 用户下次手动重试
        account.login_status = "unknown"
        db.commit()
        db.refresh(account)
        raise HTTPException(503, f"登录检查失败：{exc}") from exc


@router.post("/{account_id}/open-login")
def open_login(account_id: int, _: Admin, db: DB) -> dict:
    """打开小红书登录页（让用户扫码登录该账号）。

    强制路由到该账号的独立 Chrome 实例（ChromePool）——保证扫码后 cookie
    写入该账号对应的 user-data-dir，下次抓取自动使用。
    """
    account = db.get(XhsAccount, account_id)
    if account is None:
        raise HTTPException(404, "账号不存在")
    settings = get_settings()
    cdp_endpoint = (
        f"http://127.0.0.1:{account.cdp_port}"
        if account.cdp_port is not None
        else None
    )
    if account.cdp_port is not None:
        from app.services.opencli_extension import cdp_version_ok, wait_browser_session_ready
        # DB 记录端口上有活 Chrome（后端重启后 pool 内存态丢失的常见场景）→ adopt 复用，
        # 避免 acquire 重分配端口与 DB cdp_port 错位（UNIQUE 冲突 500）
        if cdp_version_ok(account.cdp_port):
            chrome_pool = get_global_chrome_pool()
            instance = chrome_pool.adopt_existing(account.session_name, account.cdp_port)
            # adopt 的实例可能不健康（所有 tab 已关 → No current window）：
            # 短超时健康检查不过 → release 后重启全新实例
            if not wait_browser_session_ready(settings, account.session_name, timeout_s=5.0):
                chrome_pool.release(account.session_name)
                instance = chrome_pool.acquire(account.session_name, preferred_port=account.cdp_port)
        else:
            try:
                chrome_pool = get_global_chrome_pool()
                # preferred_port = 账号自己的 DB 端口：空闲时优先复用，
                # 写回 DB 不会撞其他账号的 cdp_port UNIQUE 约束
                instance = chrome_pool.acquire(account.session_name, preferred_port=account.cdp_port)
            except ChromeLaunchError as exc:
                raise HTTPException(503, f"Chrome 实例启动失败：{exc}") from exc
        # 同步端口回 DB
        if instance.port != account.cdp_port:
            account.cdp_port = instance.port
            db.commit()
        # pool 实际分配端口可能与 DB 记录不同（跨进程端口冲突后重分配）——
        # 端点必须在 acquire 之后按实例动态端口解析，用旧端口会打开错误的 Chrome 实例
        cdp_endpoint = f"http://127.0.0.1:{instance.port}"
        # Chrome 新启动后 Browser Bridge 扩展连接 daemon 有几秒延迟——
        # 必须等扩展就绪再 open，否则命令落在 about:blank（2026-09-03 现场根因）
        if not wait_browser_session_ready(settings, account.session_name, timeout_s=15.0):
            raise HTTPException(503, "浏览器扩展尚未连接，请稍后重试（Chrome 刚启动需要几秒完成扩展连接）")
    # 打开小红书登录页（在 Chrome 实例中打开，foreground=True 拉前台）
    try:
        adapter = OpenCLIAdapter(
            settings,
            session=account.session_name,
            cdp_endpoint=cdp_endpoint,
            profile_alias=account.session_name,
        )
        ok = adapter.run(["browser", account.session_name, "open", settings.xhs_login_url, "--window", "foreground"])
        if not ok:
            raise HTTPException(503, "opencli 打开登录页失败")
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(503, f"打开登录页失败：{exc}") from exc
    return {"code": 200, "message": "success", "data": {"url": settings.xhs_login_url, "session": account.session_name}}


@router.get("/{account_id}/extension-status")
def extension_status(account_id: int, _: Admin, db: DB) -> dict:
    """检测账号 Chrome 实例运行状态与 opencli Browser Bridge 扩展加载状态。

    - chrome_running：ChromePool 中实例存活 或 CDP /json/version 可达
    - extension_installed：CDP /json/list 存在该扩展的 chrome-extension:// 条目
      （Chrome 未运行时为 False）

    关联 spec: docs/superpowers/specs/2026-09-02-extension-autodiscovery-bind-flow-design.md
    """
    from app.services import opencli_extension
    from app.services.chrome_pool import get_global_chrome_pool

    account = db.get(XhsAccount, account_id)
    if account is None:
        raise HTTPException(404, "账号不存在")

    chrome_running = False
    instance = None
    if account.cdp_port is not None:
        try:
            instance = get_global_chrome_pool().get(account.session_name)
        except Exception:  # noqa: BLE001 - pool 不可用时退回 CDP 探测
            instance = None
        chrome_running = bool(instance is not None and instance.alive()) or (
            instance is None and opencli_extension.cdp_version_ok(account.cdp_port)
        )
        extension_installed = (
            opencli_extension.cdp_has_extension(account.cdp_port)
            if chrome_running
            else False
        )
    else:
        extension_installed = False

    return {
        "code": 200,
        "message": "success",
        "data": {
            "chrome_running": chrome_running,
            "extension_installed": extension_installed,
            "cdp_port": account.cdp_port,
            "session_name": account.session_name,
        },
    }


@router.post("/{account_id}/logout")
def logout_account(account_id: int, _: Admin, db: DB) -> dict:
    """手动登出指定账号：清 cookie + 释放其 Chrome 实例，login_status='logged_out'。

    幂等友好：opencli/CDP 不可用时仍返回成功并标记状态（登出失败不阻断）。
    前端账号配置页也可由该端点在抓取前主动登出并换绑下一账号。
    """
    account = db.get(XhsAccount, account_id)
    if account is None:
        raise HTTPException(404, "账号不存在")
    settings = get_settings()
    cdp_endpoint = (
        f"http://127.0.0.1:{account.cdp_port}"
        if account.cdp_port is not None
        else None
    )
    adapter = OpenCLIAdapter(
        settings,
        session=account.session_name,
        cdp_endpoint=cdp_endpoint,
        profile_alias=account.session_name,
    )
    adapter.logout()
    try:
        get_global_chrome_pool().release(account.session_name)
    except Exception:  # noqa: BLE001 - 释放实例失败不影响登出状态
        pass
    account.login_status = "logged_out"
    db.commit()
    db.refresh(account)
    return {"code": 200, "message": "success", "data": _dump(account)}
