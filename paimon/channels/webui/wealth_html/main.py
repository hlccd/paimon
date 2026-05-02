"""岩神 · 理财（红利股追踪）面板

3 个 tab:
- 推荐选股: watchlist JOIN 最新 snapshot
- 评分排行: 最新 snapshot top 100
- 变化事件: 近 30 天 changes 时间轴

单股详情 modal: Chart.js 画 90 天评分折线 + 维度卡片 + 原始指标。
顶部: 统计卡片 + 触发扫描按钮组。
"""

from paimon.channels.webui.theme import (
    THEME_COLORS, BASE_CSS, NAVIGATION_CSS, NAV_LINKS_CSS, navigation_html,
)

# ---- chunks ----
from ._wealth_css_1 import WEALTH_CSS_1
from ._wealth_css_2 import WEALTH_CSS_2
from ._wealth_body import WEALTH_BODY
from ._wealth_script_1 import WEALTH_SCRIPT_1
from ._wealth_script_2 import WEALTH_SCRIPT_2
from ._wealth_script_3 import WEALTH_SCRIPT_3



WEALTH_CSS = WEALTH_CSS_1 + WEALTH_CSS_2


WEALTH_BODY = WEALTH_BODY


WEALTH_SCRIPT = WEALTH_SCRIPT_1 + WEALTH_SCRIPT_2 + WEALTH_SCRIPT_3


def build_wealth_html() -> str:
    return (
        """<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Paimon - 理财</title>
    <!-- 关注股资讯推送内容用 markdown 渲染（同游戏面板）-->
    <script src="https://cdn.jsdelivr.net/npm/marked/marked.min.js"></script>
    <style>"""
        + THEME_COLORS
        + BASE_CSS
        + NAVIGATION_CSS
        + NAV_LINKS_CSS
        + WEALTH_CSS
        + """</style>
</head>
<body>"""
        + navigation_html("wealth")
        + WEALTH_BODY
        + WEALTH_SCRIPT
        + """</body>
</html>"""
    )

# ---- 大 string const 切片 chunks（自动生成） ----

