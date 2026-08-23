"""env bootstrap:.env 初始化/敏感配置生成/缓存环境变量设置。

关联 spec: docs/superpowers/specs/2026-08-10-one-click-packaging-design.md § 13
关联 spec: docs/superpowers/specs/2026-08-23-data-dir-absolute-path-launcher-design.md
"""
from __future__ import annotations

import os
import secrets
from pathlib import Path

# 占位值,需要替换的
_SECRET_KEY_PLACEHOLDER = "replace-with-a-random-local-secret"

# macOS 规范的 Application Support 目录,推荐作为默认 DATA_DIR
# 避免升级 .app 时数据被覆盖,且 Time Machine 自动备份
# 与 status_server.py::StatusServer.DEFAULT_DATA_DIR 保持一致
DEFAULT_DATA_DIR = "~/Library/Application Support/com.xhs-info-crawl.local"


def generate_secret_key() -> str:
    """生成 32 字节随机十六进制字符串(64 字符)。"""
    return secrets.token_hex(32)


def ensure_env_file(env_path: Path, env_example_path: Path) -> None:
    """确保 .env 存在;不存在则从 .env.example 复制并生成敏感配置。

    - SECRET_KEY 为占位值时自动生成 32 字节随机密钥
    - INITIAL_ADMIN_PASSWORD 保持原样,不自动生成随机密码
      (登录统一用默认 Admin@123,由后端建库时播种,关联 spec:
       docs/superpowers/specs/2026-08-16-packaged-default-login-and-mainthread-window-design.md)

    关联 spec: docs/superpowers/specs/2026-08-16-launcher-password-visibility-design.md § 1
    """
    if env_path.exists():
        return  # 不覆盖已存在的 .env,密码可能是用户手动配置

    if not env_example_path.exists():
        env_path.write_text("# .env auto-generated\n")
        return

    content = env_example_path.read_text(encoding="utf-8")
    lines = content.splitlines()

    new_lines = []
    for line in lines:
        # SECRET_KEY 占位值替换
        if line.startswith("SECRET_KEY=") and _SECRET_KEY_PLACEHOLDER in line:
            line = f"SECRET_KEY={generate_secret_key()}"
        new_lines.append(line)

    env_path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")


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
    """从 .env 读取某个 key 的字符串值,缺失则返回 default。"""
    if not env_path.exists():
        return default
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        if k.strip() == key:
            return v.strip()
    return default


def resolve_data_dir(
    env_path: Path,
    *,
    project_root: Path,
    default: str | None = None,
) -> str:
    """把 .env 里的 DATA_DIR 解析为绝对路径,写入 .env 并返回。

    解析规则:
    - 缺失 / 空字符串 → 走 `default` 参数(DEFAULT_DATA_DIR 即
      `~/Library/Application Support/com.xhs-info-crawl.local`),展开 ~ 后返回
    - `~/xxx` → expanduser 展开
    - `./xxx` / `xxx`(无 `/` 开头)→ 以 `project_root` 为基准 resolve
    - 已是绝对路径 → 原样返回

    为什么必须有这层:backend 子进程 launcher 启时 cwd = .app/Contents/Resources/xhs-info-crawl/,
    相对路径 ./data 会解析成 .app/data/,所有日志/celery/run/全丢。
    dev 模式下 cwd = backend/,相对路径解析到 backend/data/,看似正常 — 但用户 .env 共用,
    必须由 launcher 在写入 .env 时强制绝对路径。

    关联 spec: docs/superpowers/specs/2026-08-23-data-dir-absolute-path-launcher-design.md
    """
    raw = _read_env_value(env_path, "DATA_DIR", "")
    if not raw:
        raw = default or DEFAULT_DATA_DIR

    # 展开 ~/ → 绝对路径
    candidate = Path(raw).expanduser()
    if candidate.is_absolute():
        resolved = candidate.resolve()
    else:
        # 相对路径(./data / data / foo/bar)→ 以 project_root 为基准
        resolved = (project_root / candidate).resolve()

    resolved_str = str(resolved)
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
