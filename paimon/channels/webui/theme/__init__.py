"""WebUI 主题样式 / 导航 / 推送红点 子包 — re-export 全部对外符号。

子模块：
- _base.py            —— THEME_COLORS / BASE_CSS / NAVIGATION_CSS+HTML / GLOBAL_PUSH_BELL_* / navigation_html()
- _nav_links_css.py   —— NAV_LINKS_CSS（343 行 CSS 大块单独成文件）
"""
from __future__ import annotations

from ._base import (
    BASE_CSS,
    GLOBAL_PUSH_BELL_HTML,
    GLOBAL_PUSH_BELL_SCRIPT,
    NAVIGATION_CSS,
    NAVIGATION_HTML,
    THEME_COLORS,
    navigation_html,
)
from ._nav_links_css import NAV_LINKS_CSS

__all__ = [
    "BASE_CSS",
    "GLOBAL_PUSH_BELL_HTML",
    "GLOBAL_PUSH_BELL_SCRIPT",
    "NAVIGATION_CSS",
    "NAVIGATION_HTML",
    "NAV_LINKS_CSS",
    "THEME_COLORS",
    "navigation_html",
]
