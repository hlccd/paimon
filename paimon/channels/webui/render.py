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


def clear_cache() -> None:
    """开发期热重载用 — 清模板缓存让下次 render 重新读盘。"""
    _read_template.cache_clear()
