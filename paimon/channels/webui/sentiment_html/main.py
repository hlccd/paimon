"""风神 · 舆情看板（L1 事件级）

# ---- 大 string const 切片 chunks（自动生成） ----

docs/archons/venti.md §L1
布局：
- 顶部 4 张统计卡（7 天事件数 / p0+p1 数 / 整体情感 / 活跃订阅数）
- 左主列 60%：事件时间线（按 last_seen_at 倒序，可按 severity / sub 过滤）
- 右上 40%：情感折线（Chart.js，按天聚合 avg_sentiment）
- 右中：严重度矩阵（7 天 × 4 级 div grid 热图）
- 右下：信源 Top（域名 + 计数）
- 事件卡片点开 → Modal 抽屉显示完整 timeline + 关联 items

数据来自 6 个 /api/sentiment/* 路由。
"""

from paimon.channels.webui.theme import (
    BASE_CSS,
    NAV_LINKS_CSS,
    NAVIGATION_CSS,
    THEME_COLORS,
    navigation_html,
)

# ---- chunks ----
from ._sentiment_css import SENTIMENT_CSS
from ._sentiment_body import SENTIMENT_BODY
from ._sentiment_script_1 import SENTIMENT_SCRIPT_1
from ._sentiment_script_2 import SENTIMENT_SCRIPT_2



SENTIMENT_CSS = SENTIMENT_CSS


SENTIMENT_BODY = SENTIMENT_BODY


SENTIMENT_SCRIPT = SENTIMENT_SCRIPT_1 + SENTIMENT_SCRIPT_2


def build_sentiment_html() -> str:
    return (
        """<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>舆情</title>
    <style>"""
        + THEME_COLORS
        + BASE_CSS
        + NAVIGATION_CSS
        + NAV_LINKS_CSS
        + SENTIMENT_CSS
        + """</style>
</head>
<body>"""
        + navigation_html("sentiment")
        + SENTIMENT_BODY
        + SENTIMENT_SCRIPT
        + """</body>
</html>"""
    )
