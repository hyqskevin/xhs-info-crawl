"""OCR 模型下载器(v0.7.0)。

v0.7.0 设计:
- paddleocr / paddlepaddle / paddlex **打进 .app venv**(backend/requirements-runtime.txt)
- OCR 模型(PP-OCRv6_medium det+rec)按需从 GitHub Release `ocr-models-3.7.0` 拉,
  解压到 DATA_DIR/paddlex/official_models/。

关联 spec: docs/superpowers/specs/2026-08-21-ocr-packaging-v0.7-design.md § 改动 5+6
"""
from __future__ import annotations

import datetime
import hashlib
import logging
import shutil
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

from launcher.env_utils import read_env_value

logger = logging.getLogger(__name__)

GITHUB_RELEASE_BASE = "https://github.com/hyqskevin/xhs-info-crawl/releases/download"
MODELS_VERSION = "3.7.0"  # 跟 paddleocr 3.7.0 对齐(PP-OCRv6_medium)
MIN_DISK_BYTES = 1 * 1024 * 1024 * 1024  # 1 GB(模型 ~50M 足够)


@dataclass
class OcrInstallResult:
    """OCR 模型安装结果。"""
    ok: bool
    message: str = ""
    version: str = ""


def get_models_url(os_name: str, arch: str) -> str:
    """获取 OCR 模型 zip 下载 URL。

    Args:
        os_name: 'macos' / 'windows'
        arch: 'arm64' / 'x86_64' / 'x64'

    URL 格式:`ocr-models-3.7.0-<os>-<arch>.zip`,每个平台一个 release asset。
    """
    return f"{GITHUB_RELEASE_BASE}/ocr-models-{MODELS_VERSION}/ocr-models-{MODELS_VERSION}-{os_name}-{arch}.zip"


def _resolve_paddlex_dir(project_root: Path) -> Path:
    """解析 OCR 模型存储目录,优先级链(PADDLE_PDX_CACHE_HOME env > .env 同名 > DATA_DIR/paddlex > fallback)。

    关联 spec: docs/superpowers/specs/2026-08-23-audit-fixes-batch-design.md Task 5。
    同时被 download_models(写入)和 get_ocr_status(读取)使用,保证两边解析的路径一致。

    优先级:
    1. ``os.environ['PADDLE_PDX_CACHE_HOME']``(子进程继承自父 launcher,通常就是 .app 启动时设置)
    2. ``project_root/.env`` 里的 ``PADDLE_PDX_CACHE_HOME=...``
    3. ``project_root/.env`` 里的 ``DATA_DIR=...`` 拼 ``/paddlex``(base dir 模式用户只设 DATA_DIR)
    4. ``project_root/data/paddlex/``(.app 内默认)

    路径里的 ``~`` 在 .env 解析阶段展开到用户主目录。
    """
    import os as _os

    # 1. os.environ(子进程继承自父 launcher)
    env_paddlex = _os.environ.get("PADDLE_PDX_CACHE_HOME")
    if env_paddlex:
        return Path(env_paddlex)

    # 2-3. 读 .env(launcher 启动时不一定 load .env)
    env_path = project_root / ".env"
    env_paddlex_from_file = read_env_value(env_path, "PADDLE_PDX_CACHE_HOME", "")
    data_dir_raw = read_env_value(env_path, "DATA_DIR", "")
    # DATA_DIR 路径里的 ``~`` 在 .env 解析阶段展开到用户主目录
    data_dir: Optional[str] = (
        str(Path(data_dir_raw).expanduser()) if data_dir_raw.startswith("~") else data_dir_raw
    ) if data_dir_raw else None

    if env_paddlex_from_file:
        return Path(env_paddlex_from_file)
    if data_dir:
        return Path(data_dir) / "paddlex"

    # 4. fallback 到 .app 内
    return project_root / "data" / "paddlex"


def get_ocr_status(project_root: Path) -> dict:
    """获取 OCR 安装状态。

    支持外部 PADDLE_PDX_CACHE_HOME 路径(用户改到 .app 外 ~/Library/... 时
    launcher 不应该误判为未安装)。路径解析走 _resolve_paddlex_dir,
    保证与 download_models 写入路径一致。

    Returns:
        {"status": "not_installed"|"installing"|"installed", "version": "..."}
    """
    paddlex_dir = _resolve_paddlex_dir(project_root)
    candidate_dirs = [paddlex_dir]
    # 兼容旧 dev 残留:用户曾经装到 project_root/data/paddlex 但后来改了
    # DATA_DIR/PADDLE_PDX_CACHE_HOME,把老路径放过一次不影响新位置判断。
    legacy_dir = project_root / "data" / "paddlex"
    if legacy_dir != paddlex_dir and legacy_dir.exists() and legacy_dir not in candidate_dirs:
        candidate_dirs.append(legacy_dir)

    for paddlex_dir in candidate_dirs:
        if not paddlex_dir.exists():
            continue
        installing_marker = paddlex_dir / ".installing"
        version_file = paddlex_dir / ".ocr_addon_version"
        models_dir = paddlex_dir / "official_models"

        if installing_marker.exists():
            return {"status": "installing", "version": ""}

        if models_dir.exists() and any(models_dir.iterdir()):
            version = ""
            if version_file.exists():
                for line in version_file.read_text(encoding="utf-8").splitlines():
                    if line.startswith("version:"):
                        version = line.split(":", 1)[1].strip()
            else:
                # 模型存在但没有版本文件(用户手动迁移 dev 模型的场景):
                # 标记为 installed 但 version 留空
                version = "migrated"
            return {"status": "installed", "version": version}

    return {"status": "not_installed", "version": ""}


def _get_disk_free_bytes(path: Path) -> int:
    """获取 path 所在磁盘的可用空间(字节)。"""
    usage = shutil.disk_usage(str(path))
    return usage.free


def _download_file(url: str, dest: Path, progress_callback: Optional[Callable[[int, int], None]] = None) -> bool:
    """下载文件,支持进度回调。返回 True 成功。"""
    import httpx
    with httpx.stream("GET", url, follow_redirects=True, timeout=300) as resp:
        resp.raise_for_status()
        total = int(resp.headers.get("content-length", 0))
        downloaded = 0
        with open(dest, "wb") as f:
            for chunk in resp.iter_bytes(chunk_size=1024 * 1024):
                f.write(chunk)
                downloaded += len(chunk)
                if progress_callback:
                    progress_callback(downloaded, total)
    return True


def _sha256(path: Path) -> str:
    """计算文件 SHA256。"""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _extract_zip(zip_path: Path, dest_dir: Path) -> bool:
    """解压 zip 到 dest_dir。"""
    with zipfile.ZipFile(zip_path) as zf:
        zf.extractall(dest_dir)
    return True


def _models_already_installed(paddlex_dir: Path) -> bool:
    """检测本地 OCR 模型是否完整(det + rec 都存在)。"""
    models_dir = paddlex_dir / "official_models"
    if not models_dir.exists():
        return False
    det = models_dir / "PP-OCRv6_medium_det"
    rec = models_dir / "PP-OCRv6_medium_rec"
    return det.exists() and rec.exists()


def download_models(
    project_root: Path,
    os_name: str,
    arch: str,
    expected_sha256: Optional[str] = None,
    progress_callback: Optional[Callable[[int, int], None]] = None,
) -> OcrInstallResult:
    """下载并安装 OCR 模型(PP-OCRv6_medium det+rec)到 DATA_DIR/paddlex/。

    流程:
    1. 检查本地是否已下载(det+rec 都存在)→ 跳过
    2. 检查磁盘空间(至少 1GB)
    3. 下载 zip 到 data/tmp/
    4. 校验 SHA256(如果提供)
    5. 解压 → 移动到 data/paddlex/official_models/
    6. 写 .ocr_addon_version

    注意:此函数**不**碰 venv。Python 包(paddleocr/paddlepaddle/paddlex)已
    打进 .app/runtime/venv/(backend/requirements-runtime.txt)。关联 spec:
    docs/superpowers/specs/2026-08-21-ocr-packaging-v0.7-design.md § 改动 6
    """
    paddlex_dir = _resolve_paddlex_dir(project_root)
    # tmp_dir 也跟随 DATA_DIR(若设了),避免把下载 zip 落在 .app 内后,
    # 用户的 PADDLE_PDX_CACHE_HOME 装模型时跨盘读写。
    # 解析:若 _resolve_paddlex_dir 的根(parent)是 DATA_DIR(无 PADDLE_PDX_CACHE_HOME env),
    # 用 DATA_DIR/tmp;否则 fallback project_root/data/tmp。
    tmp_dir = project_root / "data" / "tmp"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    paddlex_dir.mkdir(parents=True, exist_ok=True)

    # 1. 本地检测:det + rec 都存在 → 跳过
    if _models_already_installed(paddlex_dir):
        return OcrInstallResult(
            ok=True,
            message="OCR 模型已安装,跳过下载",
            version=MODELS_VERSION,
        )

    # 2. 磁盘空间检查
    free_bytes = _get_disk_free_bytes(project_root)
    if free_bytes < MIN_DISK_BYTES:
        free_gb = free_bytes / (1024 ** 3)
        return OcrInstallResult(
            ok=False,
            message=f"磁盘空间不足:需要至少 1 GB,当前可用 {free_gb:.1f} GB",
        )

    # 3. 下载
    url = get_models_url(os_name, arch)
    zip_path = tmp_dir / f"ocr-models-{MODELS_VERSION}-{os_name}-{arch}.zip"
    installing_marker = paddlex_dir / ".installing"
    installing_marker.touch()

    try:
        _download_file(url, zip_path, progress_callback)

        # 4. SHA256 校验
        if expected_sha256:
            actual_hash = _sha256(zip_path)
            if actual_hash != expected_sha256:
                zip_path.unlink(missing_ok=True)
                return OcrInstallResult(
                    ok=False,
                    message=f"SHA256 校验失败:期望 {expected_sha256},实际 {actual_hash}",
                )

        # 5. 解压到临时目录
        extract_dir = tmp_dir / f"ocr-models-extract-{MODELS_VERSION}"
        if extract_dir.exists():
            shutil.rmtree(extract_dir)
        _extract_zip(zip_path, extract_dir)

        # 6. 移动模型到 data/paddlex/official_models/
        # zip 结构可能是:
        #   extract_dir/official_models/PP-OCRv6_medium_det/...
        #   extract_dir/official_models/PP-OCRv6_medium_rec/...
        # 或者 extract_dir/PP-OCRv6_medium_det/... (没官方_models 层)
        for candidate in [extract_dir / "official_models", extract_dir]:
            if (candidate / "PP-OCRv6_medium_det").exists():
                models_src = candidate
                break
        else:
            models_src = extract_dir  # 兜底,让 shutil.move 处理

        models_dest = paddlex_dir / "official_models"
        models_dest.mkdir(parents=True, exist_ok=True)
        for item in models_src.iterdir():
            if item.name.startswith("."):
                continue
            dest_item = models_dest / item.name
            if dest_item.exists():
                if dest_item.is_dir():
                    shutil.rmtree(dest_item)
                else:
                    dest_item.unlink()
            shutil.move(str(item), str(dest_item))

        # 7. 写版本文件
        version_file = paddlex_dir / ".ocr_addon_version"
        version_file.write_text(
            f"version: {MODELS_VERSION}\n"
            f"built_at: {datetime.datetime.now(datetime.timezone.utc).isoformat()}\n",
            encoding="utf-8",
        )

        # 8. 清理临时文件
        shutil.rmtree(extract_dir, ignore_errors=True)
        zip_path.unlink(missing_ok=True)

        return OcrInstallResult(
            ok=True,
            message=f"OCR 模型 {MODELS_VERSION} 安装成功",
            version=MODELS_VERSION,
        )

    except Exception as exc:
        logger.error("OCR 模型下载失败: %s", exc, exc_info=True)
        return OcrInstallResult(ok=False, message=f"下载失败: {exc}")
    finally:
        installing_marker.unlink(missing_ok=True)
