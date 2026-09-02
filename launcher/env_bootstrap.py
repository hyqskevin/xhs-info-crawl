"""env bootstrap:.env 初始化/敏感配置生成/缓存环境变量设置。

关联 spec: docs/superpowers/specs/2026-08-10-one-click-packaging-design.md § 13
关联 spec: docs/superpowers/specs/2026-08-23-data-dir-absolute-path-launcher-design.md
关联 spec: docs/superpowers/specs/2026-08-24-bootstrap-env-system-keys-only-design.md
"""
from __future__ import annotations

import logging
import os
import secrets
from pathlib import Path

from launcher.env_utils import read_env_value

logger = logging.getLogger(__name__)


# ============================================================
# 异常
# ============================================================


class StaleDataDirFallbackError(Exception):
    """.env DATA_DIR 陈旧 + fallback 到默认路径也失败(默认路径不可写/不存在)。

    bootstrap_env 捕获此异常后,launcher 启动失败 + UI 报错卡。
    """

# 占位值,需要替换的
_SECRET_KEY_PLACEHOLDER = "replace-with-a-random-local-secret"

# macOS 规范的 Application Support 目录,推荐作为默认 DATA_DIR
# 避免升级 .app 时数据被覆盖,且 Time Machine 自动备份
# 与 status_server.py::StatusServer.DEFAULT_DATA_DIR 保持一致
DEFAULT_DATA_DIR = "~/Library/Application Support/com.xhs-info-crawl.local"


# v0.7.0+9:launcher 写入 .env(任一)的 key 白名单。
# 用户配置 key(LLM_*/API_KEY/SECRET_KEY/OPENCLI_BIN/INITIAL_ADMIN_PASSWORD 等)严禁写进 .app/.env,
# 否则升级 .app 时 .app/.env 会被覆盖,用户对 .app/.env 的修改丢失。
# 用户配置 key 走 DATA_DIR/.env,由 launcher 显式写或保留。
LAUNCHER_SYSTEM_KEYS: frozenset[str] = frozenset({
    "API_HOST", "API_PORT", "API_BASE_URL",
    "WEB_HOST", "WEB_PORT",
    "API_V1_PREFIX", "CORS_ORIGINS",
    "VITE_API_BASE_URL", "VITE_API_TIMEOUT_MS",
    "DATA_DIR", "LOG_DIR",
    "DATABASE_URL", "IMAGE_DIR", "EXPORT_DIR", "ARCHIVE_DIR",
    "BACKUP_DIR", "TMP_DIR", "TASK_REGISTRY_PATH",
    "CELERY_FOLDER", "CELERY_BEAT_SCHEDULE_PATH",
    "CHROME_USER_DATA_DIR",
    "PADDLE_PDX_CACHE_HOME", "HF_HOME",
    "CELERY_BROKER_URL", "CELERY_TIMEZONE", "CELERY_LOG_LEVEL",
    "APP_ENV",
})

# 用户配置 key 类别(全部不在白名单,由 launcher 显式处理写哪个文件)
# 仅用于 ensure_data_dir_env 从 .env.example 复制时识别"哪些是用户配置"
LAUNCHER_USER_KEYS: frozenset[str] = frozenset({
    "SECRET_KEY",             # launcher 生成,写 DATA_DIR/.env
    "INITIAL_ADMIN_PASSWORD", # 不自动写,留给用户/后端 migration
    "MINIMAX_API_KEY",
    "MINIMAX_BASE_URL",
    "MINIMAX_MODEL",
    "MINIMAX_VISION_MODEL",
    "MINIMAX_CHAT_PATH",
    "MINIMAX_TIMEOUT_SECONDS",
    "MINIMAX_CONCURRENCY",
    "OPENCLI_BIN",
    "OPENCLI_CDP_ENDPOINT",
    "OPENCLI_BROWSER_COMMAND_TIMEOUT",
    "XHS_LOGIN_URL",
    "XHS_LOGIN_BROWSER",
    "XHS_SEARCH_TARGET_COUNT",
    "XHS_SEARCH_SCROLL_MAX_ROUNDS",
    "XHS_DETAIL_SCROLL_MAX_ROUNDS",
    "XHS_SCROLL_PIXELS",
    "XHS_SCROLL_STAGNANT_ROUNDS",
    "PIPELINE_STAGE_MAX_RETRIES",
    "PIPELINE_STAGE_RETRY_DELAY_SECONDS",
    "OCR_ENABLED", "OCR_LANGUAGE", "OCR_MIN_CONFIDENCE",
    "OCR_USE_DOC_ORIENTATION_CLASSIFY", "OCR_USE_DOC_UNWARPING",
    "OCR_USE_TEXTLINE_ORIENTATION", "OCR_PARALLEL_WORKERS",
    "WEEKLY_CRAWL_DAY_OF_WEEK", "WEEKLY_CRAWL_HOUR", "WEEKLY_CRAWL_MINUTE",
    "SEARCH_INTERVAL_MIN", "SEARCH_INTERVAL_MAX", "SEARCH_LIMIT",
    "WEEKLY_SEARCH_LIMIT", "CONSECUTIVE_NOTE_FAILURE_LIMIT",
    "ACTIVITY_FUTURE_WINDOW_DAYS",
})


def generate_secret_key() -> str:
    """生成 32 字节随机十六进制字符串(64 字符)。"""
    return secrets.token_hex(32)


def _is_system_key(line: str) -> bool:
    """判断 .env 的一行是否是 launcher 系统级 key(白名单内的)。

    仅识别 `KEY=VALUE` 格式的非注释行,KEY 在 LAUNCHER_SYSTEM_KEYS 集合内。
    """
    stripped = line.strip()
    if not stripped or stripped.startswith("#") or "=" not in stripped:
        return False
    key = stripped.partition("=")[0].strip()
    return key in LAUNCHER_SYSTEM_KEYS


def _is_user_key(line: str) -> bool:
    """判断 .env 的一行是否是用户配置 key(在 LAUNCHER_USER_KEYS 白名单内)。"""
    stripped = line.strip()
    if not stripped or stripped.startswith("#") or "=" not in stripped:
        return False
    key = stripped.partition("=")[0].strip()
    return key in LAUNCHER_USER_KEYS


def _has_user_keys(env_path: Path) -> bool:
    """检测现有 .env 文件是否含用户配置 key(白名单内的)。

    用于 v0.7.0+9 升级检测:老版本 .app/.env 含 SECRET_KEY / MINIMAX_* 等,
    需要备份后重生成,否则会污染 .app/.env(用户配置 key 不该出现在 .app/.env)。
    """
    if not env_path.exists():
        return False
    for line in env_path.read_text(encoding="utf-8").splitlines():
        if _is_user_key(line):
            return True
    return False


def _extract_system_keys(env_path: Path) -> dict[str, str]:
    """从 .env 文件提取所有 LAUNCHER_SYSTEM_KEYS 的值。

    v0.7.0+10 新增:升级 .app 时,ensure_env_file 备份老 .env 后,
    用此函数提取用户改过的系统 key(覆盖 .env.example 默认值)。
    - 跳过: 注释行、空行、用户配置 key(LAUNCHER_USER_KEYS)、未识别 key
    - 解析失败 (无 = 号) 跳过该行,继续提取其他 key
    - 后出现的同名 key 覆盖前出现的(与 Python dict 语义一致)

    关联 spec: docs/superpowers/specs/2026-09-01-launcher-env-preserve-system-keys-on-upgrade-design.md
    """
    result: dict[str, str] = {}
    if not env_path.exists():
        return result
    for line in env_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, _, value = stripped.partition("=")
        key = key.strip()
        if not key or key not in LAUNCHER_SYSTEM_KEYS:
            continue
        # 用户配置 key 也在 system 白名单里的极端情况防御(目前没有交集)
        if key in LAUNCHER_USER_KEYS:
            continue
        result[key] = value.strip()
    return result


def _merge_system_keys(target_lines: list[str], preserved: dict[str, str]) -> list[str]:
    """把 preserved 字典里 key 对应的 target_lines 行,用 preserved 的 value 覆盖。

    v0.7.0+10 新增:升级 .app 时,把 preserved(老 .env 的系统 key 值)合并到
    新生成的 .env 行里。
    - 保留 target_lines 里的所有行(注释、空行、其他 key)
    - 对每行 KEY=VALUE 格式,如果 KEY 在 preserved 里 → 用 preserved 值覆盖
    - preserved 里的 key 如果 target_lines 没有 → 不插入(本 spec 范围外)

    关联 spec: docs/superpowers/specs/2026-09-01-launcher-env-preserve-system-keys-on-upgrade-design.md
    """
    if not preserved:
        return target_lines
    new_lines: list[str] = []
    for line in target_lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            new_lines.append(line)
            continue
        key, _, _ = stripped.partition("=")
        key = key.strip()
        if key in preserved:
            new_lines.append(f"{key}={preserved[key]}")
        else:
            new_lines.append(line)
    return new_lines


def ensure_env_file(env_path: Path, env_example_path: Path) -> None:
    """确保 .env(.app/.env)存在,只含 launcher 系统级 key。

    v0.7.0+9 行为变更:
    - 不存在 → 从 .env.example 复制,只保留 LAUNCHER_SYSTEM_KEYS 内的 key
    - 已存在 + 含用户配置 key(老版本 v0.7.0+8 及更早生成的)→
      备份为 .env.v0.7.0.bak 后重生成(用户对老 .app/.env 的修改已经丢,
      但实际上用户应该改 DATA_DIR/.env,所以不影响)
    - 已存在 + 不含用户配置 key(新版本生成的)→ 不动,保留 launcher 后续写
      (force_local_host / resolve_data_dir / 端口等)

    v0.7.0+10 行为变更:
    - 备份路径里改用 _extract_system_keys 提取老 .env 的 LAUNCHER_SYSTEM_KEYS 值,
      在新生成的 .env 上合并,保留用户改过的 DATA_DIR / API_PORT / CORS_ORIGINS 等

    用户配置 key(SECRET_KEY / MINIMAX_API_KEY / OPENCLI_BIN / OCR_* 等)
    走 DATA_DIR/.env,由 ensure_secret_key / ensure_data_dir_env 显式处理。

    关联 spec:
    - docs/superpowers/specs/2026-08-24-bootstrap-env-system-keys-only-design.md (v0.7.0+9)
    - docs/superpowers/specs/2026-09-01-launcher-env-preserve-system-keys-on-upgrade-design.md (v0.7.0+10)
    """
    preserved: dict[str, str] = {}
    # 升级检测:老版本 .app/.env 含用户配置 key → 备份 + 重生成
    if env_path.exists() and _has_user_keys(env_path):
        # .env → .env.v0.7.0.bak(不能 with_suffix 因为 .env 整段是 filename)
        backup_path = env_path.with_name(env_path.name + ".v0.7.0.bak")
        if not backup_path.exists():
            env_path.replace(backup_path)
        else:
            # 已经有备份,直接删掉老的(用户早就升级过了,不需要多次备份)
            env_path.unlink()
        # v0.7.0+10: 从 backup 提取用户改过的系统 key(覆盖 .env.example 默认值)
        preserved = _extract_system_keys(backup_path)

    if env_path.exists():
        return  # 已存在(纯系统 key),不覆盖

    if not env_example_path.exists():
        # 写一个最小可用 .env,让后续 bootstrap_env 能正常工作
        env_path.write_text(
            "API_HOST=127.0.0.1\n"
            "API_PORT=8000\n"
            "WEB_PORT=5173\n"
            "VITE_API_BASE_URL=/api/v1\n"
            "DATA_DIR=./data\n"
            "LOG_DIR=./logs\n",
            encoding="utf-8",
        )
        return

    content = env_example_path.read_text(encoding="utf-8")
    # 只保留系统级 key 行(过滤掉用户配置 key 和纯注释)
    # 注意:注释行(`# xxx`)一律保留,因为 .env.example 的注释是有意义的文档
    new_lines = []
    for line in content.splitlines():
        stripped = line.strip()
        # 注释行 / 空行 → 保留(launcher 不需要修改它们)
        if not stripped or stripped.startswith("#"):
            new_lines.append(line)
            continue
        # 用户配置 key 行 → 跳过(不进 .app/.env)
        if _is_user_key(line):
            continue
        # 系统 key / 未知 key(可能是 .env.example 里的扩展)→ 保留
        new_lines.append(line)

    # v0.7.0+10: 用 preserved(老 .env 的系统 key 值)覆盖新生成的对应行
    if preserved:
        new_lines = _merge_system_keys(new_lines, preserved)
        logger.info(
            "升级 .env 已保留用户改过的系统 key: %s",
            ", ".join(f"{k}={v}" for k, v in sorted(preserved.items())),
        )

    env_path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")


def ensure_data_dir_env(data_dir_env_path: Path, env_example_path: Path) -> None:
    """确保 <DATA_DIR>/.env 存在;不存在则从 .env.example 复制用户配置 key 部分。

    v0.7.0+9 新增:launcher 显式负责 DATA_DIR/.env 的初始化,避免:
    - 用户第一次启动时 DATA_DIR/.env 不存在,Settings 拿不到 SECRET_KEY / LLM_API_KEY 等
    - 用户手动建 DATA_DIR/.env 但忘了复制用户配置 key 模板

    行为:
    - 不存在 → 从 .env.example 复制**只复制用户配置 key**(LAUNCHER_USER_KEYS 内的)
    - 已存在 → 不动(用户可能改过)
    - 系统 key 不在这里复制(launcher 在 .app/.env 写)

    关联 spec: docs/superpowers/specs/2026-08-24-bootstrap-env-system-keys-only-design.md
    """
    if data_dir_env_path.exists():
        return  # 已存在,用户可能改过

    data_dir_env_path.parent.mkdir(parents=True, exist_ok=True)

    if not env_example_path.exists():
        # 写空 .env(后续 ensure_secret_key 也会写 SECRET_KEY)
        data_dir_env_path.write_text("# DATA_DIR/.env auto-generated by launcher\n", encoding="utf-8")
        return

    content = env_example_path.read_text(encoding="utf-8")
    # 复制逻辑:保留注释行 + 用户配置 key 行,跳过系统 key 行
    new_lines = []
    for line in content.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            new_lines.append(line)
            continue
        # 系统 key 行 → 跳过(由 .app/.env 承载)
        if _is_system_key(line):
            continue
        # 用户配置 key / 未知 key → 保留
        new_lines.append(line)

    data_dir_env_path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")


def ensure_secret_key(data_dir_env_path: Path) -> str:
    """确保 SECRET_KEY 在 DATA_DIR/.env 中是有效随机密钥,返回最终值。

    v0.7.0+9 新增:launcher 启动时显式保证 DATA_DIR/.env 含有效 SECRET_KEY。
    修前: SECRET_KEY 写在 .app/.env,被 DATA_DIR/.env(占位值)覆盖,Settings 拿占位。
    修后: 写 DATA_DIR/.env(用户持久化主源),DataDir 源胜出,Settings 拿真实密钥。

    行为:
    - 读 DATA_DIR/.env 的 SECRET_KEY
    - 缺 / 空 / 占位值 → 生成 32 字节随机 hex 写回,返回新值
    - 已有真实值(非占位、非空)→ 不动,返回原值

    关联 spec: docs/superpowers/specs/2026-08-24-bootstrap-env-system-keys-only-design.md
    """
    current = _read_env_value(data_dir_env_path, "SECRET_KEY", "")

    if current and current != _SECRET_KEY_PLACEHOLDER:
        return current

    new_key = generate_secret_key()
    update_env_value(data_dir_env_path, "SECRET_KEY", new_key)
    return new_key


def _resolve_data_dir_in_data_dir_env(
    data_dir_env_path: Path,
    project_root: Path,
    *,
    fallback_absolute: str = "",
) -> str:
    """确保 DATA_DIR/.env 的 DATA_DIR 字段是绝对路径(与 .app/.env 同步)。

    v0.7.0+9 新增:防止 .app/.env 写了绝对路径,但 DATA_DIR/.env 还是相对路径,
    Settings 走 DataDir 源时又解析回相对路径(cwd=.app 内部)。

    DATA_DIR/.env 本身可能不含 DATA_DIR 字段(因为 ensure_data_dir_env 复制 .env.example 时
    把 DATA_DIR 当作系统 key 跳过了)。此时:
    - 如果调用方传了 fallback_absolute(从 .app/.env 拿到的绝对路径)→ 用它写回 DATA_DIR/.env
    - 否则保持现状(由 Settings 走 cwd/.env fallback 解析)
    """
    raw = _read_env_value(data_dir_env_path, "DATA_DIR", "")
    if not raw:
        if not fallback_absolute:
            return ""
        raw = fallback_absolute

    candidate = Path(raw).expanduser()
    if candidate.is_absolute():
        resolved = candidate.resolve()
    else:
        resolved = (project_root / candidate).resolve()

    resolved_str = str(resolved)
    update_env_value(data_dir_env_path, "DATA_DIR", resolved_str)
    return resolved_str


def force_local_host(env_path: Path) -> None:
    """强制 API_HOST=127.0.0.1,防止局域网暴露。"""
    if not env_path.exists():
        return

    content = env_path.read_text(encoding="utf-8")
    lines = content.splitlines()
    new_lines = []
    for line in lines:
        if line.startswith("API_HOST="):
            line = "API_HOST=127.0.0.1"
        new_lines.append(line)
    env_path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")


def set_cache_env_vars(project_root: Path) -> None:
    """设置 PADDLE_PDX_CACHE_HOME 和 HF_HOME 环境变量到项目内。

    用 setdefault,不覆盖已存在值。同时创建目录。
    """
    paddlex_dir = project_root / "data" / "paddlex"
    hf_dir = project_root / "data" / "huggingface"

    paddlex_dir.mkdir(parents=True, exist_ok=True)
    hf_dir.mkdir(parents=True, exist_ok=True)

    os.environ.setdefault("PADDLE_PDX_CACHE_HOME", str(paddlex_dir))
    os.environ.setdefault("HF_HOME", str(hf_dir))


def update_env_value(env_path: Path, key: str, value: str) -> None:
    """更新 .env 文件中某个 key 的值(不存在则追加)。"""
    if not env_path.exists():
        env_path.write_text(f"{key}={value}\n", encoding="utf-8")
        return

    content = env_path.read_text(encoding="utf-8")
    lines = content.splitlines()
    found = False
    new_lines = []
    for line in lines:
        if line.startswith(f"{key}="):
            new_lines.append(f"{key}={value}")
            found = True
        else:
            new_lines.append(line)
    if not found:
        new_lines.append(f"{key}={value}")
    env_path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")


def _read_env_value(env_path: Path, key: str, default: str) -> str:
    """兼容 shim:转发到 launcher.env_utils.read_env_value。

    抽出动机:6 个 launcher 文件各自内联同一份 .env 解析逻辑,行为漂移埋坑。
    保留 _read_env_value 别名是为了不改 11 个调用点 + main.py 的 import。
    新代码请直接用 launcher.env_utils.read_env_value。
    """
    return read_env_value(env_path, key, default)


def _resolve_and_write(
    env_path: Path,
    target_path: str,
    project_root: Path,
    *,
    _check_writable: bool = False,
) -> str:
    """把 target_path 解析为绝对路径,可选校验可写,写回 env_path。

    Args:
        env_path: .env 文件路径
        target_path: 目标 DATA_DIR 字面值(可能是 default 字符串)
        project_root: launcher project_root(用于解析相对路径)
        _check_writable: True 时校验 target_path 解析后可写,失败抛 StaleDataDirFallbackError

    Returns:
        解析后的绝对路径字符串

    Raises:
        StaleDataDirFallbackError: _check_writable=True 且路径不可写/不存在时
    """
    candidate = Path(target_path).expanduser()
    if candidate.is_absolute():
        resolved = candidate.resolve()
    else:
        # 相对路径(./data / data / foo/bar)→ 以 project_root 为基准
        resolved = (project_root / candidate).resolve()

    if _check_writable:
        # 校验路径可写:目录不存在 → mkdir(parents=True, exist_ok=True);不可写 → 抛异常
        if not resolved.exists():
            try:
                resolved.mkdir(parents=True, exist_ok=True)
            except (OSError, PermissionError) as exc:
                raise StaleDataDirFallbackError(
                    f"陈旧 DATA_DIR fallback 失败:默认路径 {resolved} 不可创建({exc})。"
                    f"请手动检查磁盘权限或 .env 的 DATA_DIR 字段"
                ) from exc
        if not os.access(str(resolved), os.W_OK):
            raise StaleDataDirFallbackError(
                f"陈旧 DATA_DIR fallback 失败:默认路径 {resolved} 不可写。"
                f"请手动检查磁盘权限或 .env 的 DATA_DIR 字段"
            )

    resolved_str = str(resolved)
    update_env_value(env_path, "DATA_DIR", resolved_str)
    return resolved_str


def is_data_dir_stale(raw_value: str, *, project_root: Path) -> tuple[bool, str]:
    """检测 .app/.env 的 DATA_DIR 字面值是否指向"陈旧"路径(目录不存在)。

    陈旧定义(2026-08-24 spec):
    - 路径解析后物理上不存在(目录不存在)
    - 路径解析后存在但不是目录(指向文件)
    - 路径解析失败(OSError / RuntimeError,如循环 symlink)

    Returns:
        (stale, reason) 元组
        - stale=True:陈旧,reason 说明原因(供 logger.warning 输出)
        - stale=False:路径存在且是目录,reason 为空
    """
    if not raw_value:
        return True, "DATA_DIR 字段缺失/空"
    try:
        candidate = Path(raw_value).expanduser()
        if candidate.is_absolute():
            resolved = candidate.resolve()
        else:
            resolved = (project_root / candidate).resolve()
    except (OSError, RuntimeError) as exc:
        return True, f"DATA_DIR 解析失败: {exc}"

    if not resolved.exists():
        return True, f"DATA_DIR 路径不存在: {resolved}"
    if not resolved.is_dir():
        return True, f"DATA_DIR 不是目录: {resolved}"

    return False, ""


def resolve_data_dir(
    env_path: Path,
    *,
    project_root: Path,
    default: str | None = None,
) -> str:
    """把 .env 里的 DATA_DIR 解析为绝对路径,写入 .env 并返回。

    解析规则(v0.7.0+6 + 2026-08-24 陈旧 fallback):
    - 缺失 / 空字符串 → 走 `default` 参数(DEFAULT_DATA_DIR),展开 ~ 后返回
    - 字面值指向目录物理不存在 → 视为陈旧,logger.warning 输出原因,fallback 到默认路径
      (并校验默认路径可写;不可写则抛 StaleDataDirFallbackError)
    - `~/xxx` → expanduser 展开
    - `./xxx` / `xxx`(无 `/` 开头)→ 以 `project_root` 为基准 resolve
    - 已是绝对路径且存在 → 原样返回

    为什么必须有这层:backend 子进程 launcher 启时 cwd = .app/Contents/Resources/xhs-info-crawl/,
    相对路径 ./data 会解析成 .app/data/,所有日志/celery/run/全丢。
    dev 模式下 cwd = backend/,相对路径解析到 backend/data/,看似正常 — 但用户 .env 共用,
    必须由 launcher 在写入 .env 时强制绝对路径。

    关联 spec:
    - docs/superpowers/specs/2026-08-23-data-dir-absolute-path-launcher-design.md
    - docs/superpowers/specs/2026-08-24-launcher-detect-stale-data-dir-and-fallback-default-design.md
    """
    raw = _read_env_value(env_path, "DATA_DIR", "")
    fallback_target = default or DEFAULT_DATA_DIR

    if not raw:
        # 缺失/空 → 走 fallback,沿用 v0.7.0+6 行为
        return _resolve_and_write(env_path, fallback_target, project_root)

    # 已有字面值 → 先检测是否陈旧
    stale, reason = is_data_dir_stale(raw, project_root=project_root)
    if stale:
        # 陈旧 → fallback 到默认,带可写性校验
        logger.warning(
            ".env DATA_DIR=%r 已陈旧(%s),fallback 到默认路径 %s",
            raw, reason, fallback_target,
        )
        return _resolve_and_write(
            env_path, fallback_target, project_root, _check_writable=True
        )

    # 路径有效 → 原样返回(沿用 v0.7.0+6 行为)
    candidate = Path(raw).expanduser()
    if candidate.is_absolute():
        resolved = candidate.resolve()
    else:
        resolved = (project_root / candidate).resolve()
    resolved_str = str(resolved)
    # 仅当 .env 字面值未写成绝对路径时才写回(v0.7.0+6 行为)
    if _read_env_value(env_path, "DATA_DIR", "") != resolved_str:
        update_env_value(env_path, "DATA_DIR", resolved_str)
    return resolved_str


def build_api_base_url(env_path: Path) -> str:
    """从 .env 拼出后端 API base URL:http://<API_HOST>:<API_PORT>。

    缺失 key 时用默认 127.0.0.1:8000,而不是抛异常,保证启动器在 .env 未就绪时也能拿到合理 URL。
    """
    host = _read_env_value(env_path, "API_HOST", "127.0.0.1")
    port = _read_env_value(env_path, "API_PORT", "8000")
    return f"http://{host}:{port}"


def build_cors_origins(env_path: Path) -> list[str]:
    """从 .env 的 WEB_PORT 推导允许的 CORS origin 列表。

    默认包含 5173-5199 范围内所有 host(127.0.0.1 + localhost),保证端口自适应后前端仍能 fetch。
    .env 中的 WEB_PORT 即使落在 5173-5199 之外也会被加入(防止端口冲突跳出去)。
    """
    host = _read_env_value(env_path, "API_HOST", "127.0.0.1")
    web_port = _read_env_value(env_path, "WEB_PORT", "5173")
    origins: set[str] = set()
    # 默认范围 5173-5199:同时支持 127.0.0.1 和 localhost
    for port in range(5173, 5200):
        origins.add(f"http://127.0.0.1:{port}")
        origins.add(f"http://localhost:{port}")
    # .env 里的 WEB_PORT 即使在范围外也加入
    origins.add(f"http://{host}:{web_port}")
    origins.add(f"http://localhost:{web_port}")
    return sorted(origins)
