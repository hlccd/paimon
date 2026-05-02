"""风神 L1 · 事件级舆情监测核心 (EventClusterer)

docs/archons/venti.md §L1 事件级舆情监测

把单批次新条目升级为事件级情报：
1. 聚类 LLM（_llm_cluster）  —— 阶段 A 暂跳过、强制 new；B 阶段启用
2. 分析 LLM（_llm_analyze）  —— 给每个事件出"标题/摘要/实体/时间线/严重度/情感"
3. UPSERT 到 feed_events + 关联 feed_items.event_id

设计要点：
- LLM 用浅池（mimo-v2-omni）；token 记原石 component="风神" purpose="事件聚类/分析"
- 严格 JSON 输出 + 多道兜底，失败降级为模板事件，绝不阻塞批次
- 严重度由 LLM 直接判定（p0-p3），不在此处做规则修正
- 事件 upsert 完全幂等：merge 时 item_count_inc + last_seen_at 滚动
"""
from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any
from urllib.parse import urlparse

from loguru import logger

if TYPE_CHECKING:
    from paimon.foundation.irminsul import Irminsul
    from paimon.foundation.irminsul.feed_event import FeedEvent
    from paimon.foundation.irminsul.subscription import Subscription
    from paimon.llm.model import Model


# 同一订阅 7 天回看；超出按 last_seen_at 截
LOOKBACK_SECONDS = 7 * 24 * 3600
# 单批送聚类 LLM 的"近期事件候选"上限
MAX_RECENT_CANDIDATES = 20
# 单事件最多关联条目数（防 LLM 错把 wholly irrelevant 条目都塞过来）
MAX_ITEMS_PER_EVENT = 30
# 新事件分析时 description 截断长度
MAX_DESC_LEN = 400
# title 最长字数（超过 LLM 输出截断）
MAX_TITLE_LEN = 80
# summary 最长字数
MAX_SUMMARY_LEN = 200
# severity / sentiment_label 的合法集合
_VALID_SEVERITY = {"p0", "p1", "p2", "p3"}
_VALID_SENTIMENT_LABEL = {"positive", "neutral", "negative", "mixed"}


@dataclass
class ProcessedEvent:
    """聚类 + 分析后的单个事件，给 collect_subscription 做后续推送决策。"""
    event_id: str
    severity: str                    # 当前 severity (p0-p3)
    base_severity: str               # merge 前的旧 severity（new 时为 ""）
    is_new: bool                     # 是新建事件还是 merge 已有
    severity_changed: bool           # 跟旧 severity 不同（升级 / 降级 / 平级）
    title: str
    summary: str
    first_url: str                   # 第一个 url（推送时点开用）
    item_count: int                  # 本批次为此事件贡献的条目数
    sentiment_label: str
    sentiment_score: float
    last_seen_at: float = 0.0        # 事件最近一次更新时间 (unix)，digest 时效过滤用
    timeline: list = None            # [{"ts": int, "point": str}, ...]，digest 判定起源/动态用


# ---------- 公共工具 ----------

_CODE_FENCE = re.compile(r"^```(?:json)?\s*\n?", re.MULTILINE)
_TRAILING_FENCE = re.compile(r"\n?```\s*$", re.MULTILINE)


def _strip_code_fence(text: str) -> str:
    """LLM 偶尔包 ```json\n...\n```；剥掉再 json.loads。"""
    text = text.strip()
    text = _CODE_FENCE.sub("", text, count=1)
    text = _TRAILING_FENCE.sub("", text, count=1)
    return text.strip()


def _extract_domain(url: str) -> str:
    """从 url 抽 host（无协议返空字符串）。"""
    try:
        host = urlparse(url).netloc.lower().strip()
        # 去 www.
        if host.startswith("www."):
            host = host[4:]
        return host
    except Exception:
        return ""


def _truncate(text: str, n: int) -> str:
    text = (text or "").strip()
    return text[:n] if len(text) > n else text


# ---------- 风神领域 DigestSpec（注入通用 prompt 模板）----------

from paimon.foundation.digest import (
    DigestSpec,
    render_analyze_prompt,
    render_cluster_prompt,
)

VENTI_DIGEST_SPEC = DigestSpec(
    actor="风神·巴巴托斯",
    domain="舆情新闻",
    item_kind="新闻条目",
    entity_kinds="人物 / 公司 / 产品 / 地点",
    cluster_examples=(
        '  * "OpenAI 发布 GPT-5"、"GPT-5 上线" → 合并\n'
        '  * "苹果 WWDC 公布 X"、"WWDC 大会回顾"、"X 在 WWDC 亮相" → 合并\n'
        '  * "DeepSeek V4 发布"、"DeepSeek 新模型开源" → 合并\n'
        '  * "苹果发布会" vs "苹果裁员" → 分开（不同动作）\n'
        '  * "OpenAI 起诉" vs "Anthropic 融资" → 分开（不同主体）'
    ),
    digest_focus="事件影响 + 整体情感倾向",
    regular_examples="产品迭代 / 例行公告",
    advice_examples="具体下一步看什么 / 何时再来扫（可选）",
)

# 风神聚类 + 分析 system prompt 由通用模板渲染（一次性 .format）
# 日报 prompt 走 venti.py 的 _compose_event_digest（保留 {query}/{n} 占位待 format）
_CLUSTER_SYSTEM = render_cluster_prompt(VENTI_DIGEST_SPEC)
_ANALYZE_SYSTEM = render_analyze_prompt(VENTI_DIGEST_SPEC)

