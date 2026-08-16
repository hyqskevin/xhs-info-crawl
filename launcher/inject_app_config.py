"""把 .env 中的端口信息注入到 frontend/dist/index.html,供前端运行时读取。

关联 spec: docs/superpowers/specs/2026-08-16-packaged-frontend-static-serving-design.md

在 index.html 的 </head> 之前注入:

    <script>
    window.__APP_CONFIG__ = {
      apiBaseUrl: "http://127.0.0.1:8001",
      webPort: 5174
    };
    </script>

重复注入是幂等的:已注入则替换,未注入则插入。
"""
from __future__ import annotations

import json
import re
from pathlib import Path


_INJECTED_RE = re.compile(
    r"<script>\s*window\.__APP_CONFIG__\s*=\s*\{[^}]*\};?\s*</script>",
    re.DOTALL,
)


def _read_env_value(env_file: Path, key: str, default: str) -> str:
    """从 .env 文件读取指定 key 的值,找不到返回 default。"""
    if not env_file.exists():
        return default
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        if k.strip() == key:
            return v.strip()
    return default


def inject_app_config(dist: Path, env_file: Path) -> None:
    """把 .env 中的 API_PORT/WEB_PORT 注入到 dist/index.html 的 </head> 之前。

    Args:
        dist: 前端 dist 目录(含 index.html)
        env_file: .env 文件路径

    Returns:
        None;直接修改 index.html

    副作用:
        - 修改 dist/index.html(找不到 index.html 时静默跳过)
        - 重复调用幂等:已注入会替换旧块,未注入会插入新块
    """
    index_html = dist / "index.html"
    if not index_html.exists():
        return

    api_host = _read_env_value(env_file, "API_HOST", "127.0.0.1")
    api_port = _read_env_value(env_file, "API_PORT", "8000")
    web_port = _read_env_value(env_file, "WEB_PORT", "5173")

    # apiBaseUrl 包含 /api/v1 路径前缀,前端 axios baseURL 直接拼
    # (避免开发/生产两套 baseURL 逻辑;VITE_API_BASE_URL=/api/v1 配合 vite proxy 仅开发用)
    config_block = (
        '<script>\n'
        'window.__APP_CONFIG__ = '
        + json.dumps(
            {
                "apiBaseUrl": f"http://{api_host}:{api_port}/api/v1",
                "webPort": int(web_port),
            },
            ensure_ascii=False,
        )
        + ';\n'
        '</script>'
    )

    content = index_html.read_text(encoding="utf-8")

    # 已有注入则替换
    if _INJECTED_RE.search(content):
        content = _INJECTED_RE.sub(config_block, content)
    else:
        # 在 </head> 之前插入
        if "</head>" in content:
            content = content.replace("</head>", f"{config_block}\n</head>", 1)
        else:
            # 没有 </head>:追加到文件开头
            content = config_block + "\n" + content

    index_html.write_text(content, encoding="utf-8")