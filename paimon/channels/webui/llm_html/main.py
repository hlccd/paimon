"""神之心 · LLM Profile 管理面板 + 路由配置

M1：profile 存储 + 面板（增删改 + 测连接 + 设默认）
M2：新增路由 tab —— 按 (component, purpose) 把调用路由到 profile；点击保
存即 publish leyline 事件，Gnosis 感知后热切换 provider 缓存。

docs/todo.md §LLM 分层调度
"""

from paimon.channels.webui.theme import (
    BASE_CSS, NAV_LINKS_CSS, NAVIGATION_CSS, THEME_COLORS, navigation_html,
)

# ---- chunks ----
from ._llm_css import LLM_CSS
from ._llm_body import LLM_BODY
from ._llm_script_1 import LLM_SCRIPT_1
from ._llm_script_2 import LLM_SCRIPT_2



LLM_CSS = LLM_CSS


LLM_BODY = LLM_BODY


LLM_SCRIPT = LLM_SCRIPT_1 + LLM_SCRIPT_2


def build_llm_html() -> str:
    return (
        """<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Paimon · 神之心 模型管理</title>
    <style>"""
        + THEME_COLORS
        + BASE_CSS
        + NAVIGATION_CSS
        + NAV_LINKS_CSS
        + LLM_CSS
        + """</style>
</head>
<body>"""
        + navigation_html("llm")
        + LLM_BODY
        + LLM_SCRIPT
        + """</body>
</html>"""
    )

# ---- 大 string const 切片 chunks（自动生成） ----

