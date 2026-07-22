"""海报渲染：组装 HTML、调 Playwright 或 opencli 截图。

关联 spec: docs/superpowers/specs/2026-07-21-poster-generation-design.md

路径：
- assemble_html(template, task) -> str    纯函数，便于测试与 preview
- render_task_to_png(template, task, path) -> str  Playwright 优先，
  失败回退到 opencli。

运行时依赖：
- Playwright（可选）
- opencli（系统 CLI）作为兜底
"""
import base64
import html as html_lib
import json
import shutil
import subprocess
import tempfile
from pathlib import Path

from app.models.poster import PosterTask, PosterTemplate


VIEWPORT = (1242, 2208)


def _escape(value: str | None) -> str:
    return html_lib.escape(value or "")


def _render_item_html(item: dict) -> str:
    fields = item.get("fields") or {}
    time_range = _escape(fields.get("time_range"))
    location = _escape(fields.get("location"))
    fee = _escape(fields.get("fee"))
    content = _escape(fields.get("content"))
    title = _escape(item.get("title") or fields.get("content") or "")
    image_url = item.get("image_url") or ""
    img_html = (
        f'<img class="row-image" src="{_escape(image_url)}" alt=""/>' if image_url else ""
    )
    return f"""
      <section class="row-card">
        <div class="row-banner"><span class="row-title">{title}</span></div>
        <div class="row-body">
          <div class="row-meta">
            <p class="meta-time">🕐 {time_range}</p>
            <p class="meta-location">📍 {location}</p>
            <p class="meta-fee">🎫 {fee}</p>
            {f'<p class="meta-content">{content}</p>' if content else ''}
          </div>
          {img_html}
        </div>
      </section>""".strip()


def render_poster_preview_html(template: PosterTemplate, task: PosterTask) -> str:
    """纯函数。返回用于 iframe 预览 / 文件落盘的完整 HTML。"""
    items = task.items or []
    items_html = "\n".join(_render_item_html(item) for item in items)
    css = template.css_text or ""
    body_html = template.html_template or ""
    # 简易替换：把 {{title}} {{items}} 这两个占位符替换
    body_html = body_html.replace("{{title}}", _escape(task.name))
    body_html = body_html.replace("{{items}}", items_html)
    base_css = (
        "body{margin:0;padding:0;font-family:'PingFang SC','Noto Sans CJK SC',sans-serif;}"
        "*{box-sizing:border-box;}"
    )
    title_block = (
        f'<div class="poster-title"><h1>{_escape(task.name)}</h1></div>'
        if "{{title}}" not in (template.html_template or "") else ""
    )
    return f"""<!doctype html>
<html lang="zh">
<head>
<meta charset='utf-8'>
<style>{base_css}{css}</style>
</head>
<body>
{title_block}
{body_html}
</body>
</html>"""


def _playwright_available() -> bool:
    try:
        from playwright.sync_api import sync_playwright  # noqa: F401
        return True
    except Exception:
        return False


def _playwright_render(html: str, path: str) -> None:
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(args=["--no-sandbox"])
        context = browser.new_context(viewport={"width": VIEWPORT[0], "height": VIEWPORT[1]})
        page = context.new_page()
        page.set_content(html, wait_until="networkidle")
        page.screenshot(path=path, full_page=True)
        browser.close()


def _opencli_render(html: str, path: str) -> None:
    """通过 opencli browser bridge 渲染 HTML → PNG。

    步骤：
    1. 写临时 html；
    2. opencli browser open file://...
    3. opencli browser screenshot --output path --full-page
    """
    if shutil.which("opencli") is None:
        raise RuntimeError("opencli 未安装；安装 opencli 后重试")
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", suffix=".html", delete=False, encoding="utf-8") as tmp:
        tmp.write(html)
        tmp_name = tmp.name
    url = f"file://{tmp_name}"
    try:
        open_proc = subprocess.run(
            ["opencli", "browser", "default", "open", url],
            capture_output=True,
            text=True,
            timeout=180,
        )
        if open_proc.returncode != 0:
            raise RuntimeError(f"opencli browser open 失败: {open_proc.stderr or open_proc.stdout}")
        screenshot_proc = subprocess.run(
            ["opencli", "browser", "default", "screenshot", "--output", path, "--full-page"],
            capture_output=True,
            text=True,
            timeout=180,
        )
        if screenshot_proc.returncode != 0:
            raise RuntimeError(
                f"opencli browser screenshot 失败: {screenshot_proc.stderr or screenshot_proc.stdout}"
            )
    finally:
        try:
            Path(tmp_name).unlink()
        except OSError:
            pass


def render_task_to_png(template: PosterTemplate, task: PosterTask, output_path: str) -> str:
    """Playwright 优先，失败 fallback opencli；output_path 已确定。"""
    html = render_poster_preview_html(template, task)
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    if _playwright_available():
        try:
            _playwright_render(html, str(output))
            return str(output)
        except Exception:
            # 走 fallback
            pass
    _opencli_render(html, str(output))
    return str(output)
