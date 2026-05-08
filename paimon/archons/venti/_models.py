"""风神 · Venti — 自由·歌咏

新闻采集、舆情分析与追踪、推送整理。

⚠️ v6 解耦后单一入口：
- `collect_subscription()` —— 话题订阅后台采集入口（subprocess 直调 web-search skill，
  批量 LLM 早报，交三月响铃推送）
- `execute()` 已废除（v6 解耦后 asmoday 不再调本节点；通用执行职能由四影自己承担）
"""
from __future__ import annotations

import asyncio
import json
import sys
import time
from pathlib import Path
from typing import TYPE_CHECKING
from uuid import uuid4

from loguru import logger

from paimon.archons.base import Archon
from paimon.foundation.irminsul import Irminsul
from paimon.foundation.irminsul.task import Subtask, TaskEdict
from paimon.foundation.march import today_local_bounds
from paimon.llm.model import Model
from paimon.session import Session

if TYPE_CHECKING:
    from paimon.foundation.irminsul.feed_event import FeedEvent
    from paimon.foundation.march import MarchService

# web-search skill 脚本路径（文件存在则订阅能力可用；不存在仅告警不阻塞启动）
# 路径：paimon/archons/venti/_models.py → 上 4 级到项目根 → skills/web-search/search.py
_SKILL_SEARCH_PY = (
    Path(__file__).resolve().parent.parent.parent.parent / "skills" / "web-search" / "search.py"
)

# subprocess 超时：双引擎并发 + 反爬偶发慢，默认 60s
_WEB_SEARCH_TIMEOUT = 60.0

# 去重窗口：过去 30 天的 url 视为已见
_DEDUP_WINDOW_SECONDS = 30 * 24 * 3600

# 事件型日报 LLM 重试退避：第 1 次失败等 60s，第 2 次失败等 180s，第 3 次失败
# 不再重试，转走 P0+P1 兜底模板。`len(...)+1 = 总尝试次数`。
# 选 60s/180s 而非更短：失败模式以「上游 edge transient hiccup」为主，
# 拉长窗口能错过最常见的 30~60s 限流恢复期，再短反而连续撞同一波故障。
_DIGEST_RETRY_DELAYS = (60.0, 180.0)


_SYSTEM_PROMPT = """\
你是风神·巴巴托斯，掌管自由与歌咏。你的职责是信息采集与分析。

能力：
1. 用 web_fetch 工具抓取网页内容（新闻、文章、搜索结果）
2. 用 exec 工具执行 curl 等命令做补充抓取
3. 新闻摘要和舆情分析

规则：
1. 优先用 web_fetch 工具，它更安全且输出更干净
2. 输出结构化结果：标题、来源、摘要
3. 舆情分析时标注情感倾向（正面/中性/负面）
4. 调用工具时不要输出过程描述，只输出最终结果
"""


_DIGEST_PROMPT = """\
你是风神·巴巴托斯，负责给用户整理关注话题的日报。

用户订阅主题：「{query}」
下面是刚采集到的 {n} 条新条目（JSON），请整理成一段中文日报，体裁要求：

1. 开头一句 40 字内的总体概述（当前这些新内容的主要看点）
2. 之后用 1-3 级 bullet 列出条目，每条「标题 + 1 句话要点 + 来源 URL」
3. 末尾一句话点出情感倾向（正面 / 中性 / 负面 / 混合）和建议（要不要深读）
4. 全篇控制在 500 字内
5. 保留 URL 的 markdown 链接格式: [标题](URL)
6. 只输出最终日报文本，不要任何前置说明
"""


# 阶段 C · 事件型日报（按事件而非条目组织）
# 风神日报 system prompt 由通用 composer 渲染（保留 {query}/{n} 占位待调用方 .format）
from paimon.archons.venti_event import VENTI_DIGEST_SPEC
from paimon.foundation.digest import render_digest_prompt
_EVENT_DIGEST_PROMPT = render_digest_prompt(VENTI_DIGEST_SPEC)


def _build_fallback_digest(query: str, items: list[dict]) -> str:
    """LLM 失败时的降级模板：直接列条目。"""
    lines = [f"【订阅·{query}】刚刚采集到 {len(items)} 条新内容："]
    for it in items:
        title = (it.get("title") or "").strip() or "(无标题)"
        url = (it.get("url") or "").strip()
        if url:
            lines.append(f"- [{title}]({url})")
        else:
            lines.append(f"- {title}")
    return "\n".join(lines)


def _build_event_fallback_digest(query: str, processed_events: list) -> str:
    """事件型日报 LLM 重试用尽后的精简降级模板：仅展示 P0 / P1。

    设计取舍：P2/P3 多是日常资讯噪音，LLM 挂了的时候硬塞进公告反而难读；
    省略后让用户聚焦真正紧急的内容。当天没有 P0/P1 时只发简短提示。
    """
    if not processed_events:
        return f"**风神·订阅日报【{query}】** 本次无新事件。"

    critical = [e for e in processed_events if e.severity in ("p0", "p1")]
    skipped = len(processed_events) - len(critical)

    if not critical:
        return (
            f"**风神·订阅日报【{query}】**\n"
            f"（LLM 合成失败 / 重试用尽 · 当日无 P0/P1 事件，"
            f"P2 及以下 {skipped} 个事件已省略）"
        )

    rank = {"p0": 0, "p1": 1}
    sorted_events = sorted(critical, key=lambda e: rank.get(e.severity, 4))

    skipped_tag = f"，P2 及以下 {skipped} 个已省略" if skipped else ""
    lines = [
        f"**风神·订阅日报【{query}】**",
        f"（LLM 合成失败 · 仅展示 P0+P1 共 {len(critical)} 个{skipped_tag}）",
        "",
    ]
    for ev in sorted_events:
        title = (ev.title or "(无标题)").strip()
        sev_icon = {"p0": "🔴", "p1": "🟠"}.get(ev.severity, "⚠")
        link = f"[{title}]({ev.first_url})" if ev.first_url else title
        upgrade = (
            "·升级" if (not ev.is_new and ev.severity_changed) else ""
        )
        sentiment_tag = (
            f"·{ev.sentiment_label}"
            if ev.sentiment_label and ev.sentiment_label != "neutral"
            else ""
        )
        lines.append(
            f"- {sev_icon} **[{ev.severity.upper()}{upgrade}{sentiment_tag}]** {link}"
        )
        if ev.summary:
            lines.append(f"  {ev.summary[:120]}")
    return "\n".join(lines)
