"""env bootstrap:.env 初始化/敏感配置生成/缓存环境变量设置。

关联 spec: docs/superpowers/specs/2026-08-10-one-click-packaging-design.md § 13
"""
from __future__ import annotations

import os
import secrets
import string
from pathlib import Path

# 占位值,需要替换的
_SECRET_KEY_PLACEHOLDER = "replace-with-a-random-local-secret"


def generate_secret_key() -> str:
    """生成 32 字节随机十六进制字符串(64 字符)。"""
    return secrets.token_hex(32)


def generate_admin_password() -> str:
    """生成 12 位随机密码(字母+数字)。"""
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(12))


def ensure_env_file(env_path: Path, env_example_path: Path) -> None:
    """确保 .env 存在;不存在则从 .env.example 复制并生成敏感配置。

    - SECRET_KEY 为占位值时自动生成 32 字节随机密钥
    - INITIAL_ADMIN_PASSWORD 为空时自动生成 12 位密码
    """
    if env_path.exists():
        return  # 不覆盖已存在的 .env

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
        # INITIAL_ADMIN_PASSWORD 为空时生成
        elif line.startswith("INITIAL_ADMIN_PASSWORD=") and not line.split("=", 1)[1].strip():
            line = f"INITIAL_ADMIN_PASSWORD={generate_admin_password()}"
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
