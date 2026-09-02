"""launcher 项目路径解析集中定义。

为 process_manager / ocr_installer 等模块提供统一的 base-dir 解析,
避免每个模块各自重复 "读 .env → 退化" 逻辑。

优先级约定:
- DATA_DIR 默认从 project_root/.env 读取,缺失时退化到 project_root/data
- LOG_DIR / CELERY_FOLDER / PADDLE_PDX_CACHE_HOME 等显式配置优先
- 未显式配置时,各业务路径从 DATA_DIR 派生
"""
from __future__ import annotations

from pathlib import Path

from launcher.env_utils import read_env_value


def _resolve_path(raw: str, base: Path) -> Path:
    """把 .env 中的路径字符串解析为绝对 Path。

    - ``~`` 展开为用户主目录
    - 绝对路径直接 resolve
    - 相对路径与 base 拼接后 resolve
    """
    p = Path(raw).expanduser()
    return p.resolve() if p.is_absolute() else (base / p).resolve()


def resolve_data_dir(project_root: Path) -> Path:
    """解析 DATA_DIR。

    顺序:
    1. project_root/.env 中 DATA_DIR 显式值
    2. 退化到 project_root/data

    相对路径以 project_root 为基准。
    """
    env_path = project_root / ".env"
    raw = read_env_value(env_path, "DATA_DIR", "")
    if raw:
        return _resolve_path(raw, project_root)
    return (project_root / "data").resolve()


def resolve_log_dir(project_root: Path) -> Path:
    """解析日志目录。

    顺序:
    1. project_root/.env 中 LOG_DIR 显式值
    2. 退化到 DATA_DIR/logs
    """
    env_path = project_root / ".env"
    raw = read_env_value(env_path, "LOG_DIR", "")
    if raw:
        return _resolve_path(raw, project_root)
    return resolve_data_dir(project_root) / "logs"


def resolve_celery_dir(project_root: Path) -> Path:
    """解析 Celery beat schedule 所在目录。

    顺序:
    1. project_root/.env 中 CELERY_FOLDER 显式值
    2. 退化到 DATA_DIR/celery
    """
    env_path = project_root / ".env"
    raw = read_env_value(env_path, "CELERY_FOLDER", "")
    if raw:
        return _resolve_path(raw, project_root)
    return resolve_data_dir(project_root) / "celery"


def resolve_paddlex_dir(project_root: Path) -> Path:
    """解析 PaddleOCR/PaddleX 模型缓存目录。

    顺序:
    1. 当前进程环境变量 PADDLE_PDX_CACHE_HOME
    2. project_root/.env 中 PADDLE_PDX_CACHE_HOME 显式值
    3. 退化到 DATA_DIR/paddlex

    os.environ 优先是为了让 launcher 子进程继承已设置好的路径,
    与 backend Settings.get_settings() 行为一致。
    """
    import os

    env_paddlex = os.environ.get("PADDLE_PDX_CACHE_HOME")
    if env_paddlex:
        return Path(env_paddlex)

    env_path = project_root / ".env"
    file_paddlex = read_env_value(env_path, "PADDLE_PDX_CACHE_HOME", "")
    if file_paddlex:
        return _resolve_path(file_paddlex, project_root)

    return resolve_data_dir(project_root) / "paddlex"
