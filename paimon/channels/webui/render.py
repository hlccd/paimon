"""WebUI 模板渲染 — 0 依赖轻量实现（不引 jinja2，复杂逻辑在 handler 里拼好再传 ctx）。

支持 3 种占位符：
- `{{var}}`           变量替换（HTML 转义）
- `{{var|safe}}`      变量替换（不转义，传 raw HTML）
- `{{include:name}}`  包含另一个模板（如 `{{include:_nav}}`）

模板根目录：`paimon/channels/webui/templates/`
"""
from __future__ import annotations

import html as _html
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

_TEMPLATES_DIR = Path(__file__).parent / "templates"
_PLACEHOLDER = re.compile(r"\{\{\s*([^}|:\s]+)(?:\s*\|\s*safe)?\s*\}\}")
_INCLUDE = re.compile(r"\{\{\s*include\s*:\s*([\w\-_/]+)\s*\}\}")


@lru_cache(maxsize=64)
def _read_template(name: str) -> str:
    """读模板文件内容（缓存住）。name 不带 .html 后缀也行。"""
    fname = name if name.endswith(".html") else f"{name}.html"
    path = _TEMPLATES_DIR / fname
    return path.read_text(encoding="utf-8")


def _resolve_includes(text: str, depth: int = 0) -> str:
    """把 `{{include:_nav}}` 替换为对应模板内容（递归 ≤3 层防循环）。"""
    if depth > 3:
        return text
    def _sub(m: re.Match) -> str:
        included = _read_template(m.group(1))
        return _resolve_includes(included, depth + 1)
    return _INCLUDE.sub(_sub, text)


def render(template_name: str, ctx: dict[str, Any] | None = None) -> str:
    """渲染模板，返回最终 HTML 字符串。

    ctx 里的 value：
    - `{{var}}` 走 HTML escape
    - `{{var|safe}}` 不 escape（前端 HTML 片段 / SVG / 已 escape 内容）
    """
    raw = _read_template(template_name)
    raw = _resolve_includes(raw)
    ctx = ctx or {}

    # 先处理 `{{var|safe}}`，再处理 `{{var}}`
    def _sub(m: re.Match) -> str:
        full = m.group(0)
        key = m.group(1)
        val = ctx.get(key, "")
        if val is None:
            val = ""
        if "|safe" in full:
            return str(val)
        return _html.escape(str(val))

    return _PLACEHOLDER.sub(_sub, raw)


_NAV_KEYS = (
    "chat", "dashboard", "tasks", "feed", "wealth",
    "game", "knowledge", "plugins", "selfcheck", "llm",
)


def render_warm_page(
    *, title: str, content_template: str, active: str,
    extra_css: str = "", extra_js: str = "",
    extra_ctx: dict[str, Any] | None = None,
    body_class: str = "",
) -> str:
    """温馨柔和风 page render helper — 走 _warm_layout 公共布局，简化 nav active 填充。

    Args:
        title: 浏览器 tab 标题（不含 ' · Paimon' 后缀）
        content_template: 内容模板名（如 "dashboard"、"tasks"），渲染后填进 layout
        active: 当前 page 的 nav key（须在 _NAV_KEYS 内）
        extra_css/extra_js: 注入 page-specific <link> / <script>
        extra_ctx: 内容模板自身需要的 context（透传给 content_template）
        body_class: 注入到 <body> 的额外 class（chat 全屏模式用）
    """
    content = render(content_template, extra_ctx or {})
    ctx: dict[str, Any] = {
        "title": title,
        "content": content,
        "extra_css": extra_css,
        "extra_js": extra_js,
        "body_class": body_class,
    }
    for k in _NAV_KEYS:
        ctx[f"nav_{k}_active"] = "is-active" if k == active else ""
    return render("_warm_layout", ctx)
