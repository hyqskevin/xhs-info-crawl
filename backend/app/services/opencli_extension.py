"""opencli Browser Bridge 扩展自动发现。

spec: docs/superpowers/specs/2026-09-02-extension-autodiscovery-bind-flow-design.md

优先级：
1. 显式配置 settings.opencli_extension_dir（用户配置最高优先）
2. 缓存命中 settings.data_dir / "opencli-extension" / <version>/（随 DATA_DIR 切换）
3. 从 chrome-pool 任一已装实例的 Default/Extensions 提取 → copytree 到缓存目录
4. 找不到返回 None（ChromePool 保持 headless 兼容行为）

另提供 CDP 探测辅助（extension-status 端点使用，测试可 monkeypatch）。
"""
from __future__ import annotations

import logging
import shutil
import urllib.request
from pathlib import Path

from app.core.config import Settings

logger = logging.getLogger(__name__)

# opencli Browser Bridge 扩展 ID（Chrome Web Store / 未打包安装通用）
BROWSER_BRIDGE_EXTENSION_ID = "ildkmabpimmkaediidaifkhjpohdnifk"


def _has_manifest(path: Path) -> bool:
    return (path / "manifest.json").is_file()


def _latest_version_dir(base: Path) -> Path | None:
    """base 下含 manifest.json 的版本子目录中取名字序最大的一个。"""
    if not base.is_dir():
        return None
    candidates = sorted(
        (d for d in base.iterdir() if d.is_dir() and _has_manifest(d)),
        key=lambda d: d.name,
    )
    return candidates[-1] if candidates else None


def _extract_to_cache(source: Path, cache_root: Path) -> Path:
    """把已安装扩展 copytree 到缓存目录 <EXT_ID>-<version>/，返回缓存路径。"""
    cache_root.mkdir(parents=True, exist_ok=True)
    target = cache_root / f"{BROWSER_BRIDGE_EXTENSION_ID}-{source.name}"
    if target.exists():
        shutil.rmtree(target)
    shutil.copytree(source, target)
    logger.info("已从 %s 提取 opencli 扩展到缓存 %s", source, target)
    return target


def resolve_extension_dir(settings: Settings) -> Path | None:
    """解析 opencli Browser Bridge 扩展目录；找不到返回 None。"""
    explicit = settings.opencli_extension_dir
    if explicit is not None:
        return explicit

    cache_root = settings.data_dir / "opencli-extension"
    cached = _latest_version_dir(cache_root)
    if cached is not None:
        return cached

    # 从 chrome-pool 任一已装实例提取（用户曾手动装过一次即可）
    pool_root = settings.resolve_project_path(settings.chrome_user_data_dir)
    if pool_root.is_dir():
        for installed in sorted(pool_root.glob(f"*/Default/Extensions/{BROWSER_BRIDGE_EXTENSION_ID}/*")):
            if _has_manifest(installed):
                return _extract_to_cache(installed, cache_root)
    return None


# ── CDP 探测辅助（extension-status 端点用）──────────────────────────────────


def _cdp_get_json(port: int, path: str, timeout: float = 2.0) -> list | dict | None:
    import json

    url = f"http://127.0.0.1:{port}{path}"
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            if resp.status != 200:
                return None
            return json.loads(resp.read().decode("utf-8"))
    except Exception:  # noqa: BLE001 - 探测失败一律视为不可用
        return None


def cdp_version_ok(port: int, timeout: float = 2.0) -> bool:
    """CDP /json/version 可达即 Chrome 实例运行中。"""
    return _cdp_get_json(port, "/json/version", timeout) is not None


def cdp_has_extension(port: int, timeout: float = 2.0, extension_id: str = BROWSER_BRIDGE_EXTENSION_ID) -> bool:
    """/json/list 存在该扩展的 chrome-extension:// 条目即已加载。"""
    targets = _cdp_get_json(port, "/json/list", timeout)
    if not isinstance(targets, list):
        return False
    prefix = f"chrome-extension://{extension_id}/"
    return any(str(t.get("url", "")).startswith(prefix) for t in targets if isinstance(t, dict))


def wait_browser_session_ready(settings: Settings, session_name: str, timeout_s: float = 15.0) -> bool:
    """轮询 ``browser <session> state`` 直到扩展响应（Chrome 新启动后有时序延迟）。

    ChromePool.acquire 启动 Chrome 后，Browser Bridge 扩展需几秒才连上 opencli daemon，
    此间所有 browser 命令都会 OpenCLITimeout。调用方（扫码登录/打开登录页）应先等就绪。

    返回 True=就绪；False=超时仍无响应（调用方返回 503 提示用户稍后重试）。
    """
    import time

    from app.services.crawler import OpenCLIError, OpenCLITimeout
    from app.services.opencli_adapter import OpenCLIAdapter

    adapter = OpenCLIAdapter(settings, session=session_name)
    deadline = time.monotonic() + max(timeout_s, 0)
    while True:
        try:
            adapter.run(["browser", session_name, "state"], timeout=3)
            return True
        except OpenCLITimeout:
            pass
        except OpenCLIError:
            pass
        except Exception as exc:  # pragma: no cover - 兜底
            logger.warning("wait_browser_session_ready %s unexpected error: %s", session_name, exc)
        if time.monotonic() >= deadline:
            return False
        time.sleep(1)
