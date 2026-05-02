"""风神 L1 · 事件级舆情监测核心 (EventClusterer) 子包

docs/archons/venti.md §L1 事件级舆情监测

子模块：
- _models.py   —— ProcessedEvent + 各类常量 + helpers + VENTI_DIGEST_SPEC + system prompts
- _process.py  —— _ProcessMixin: process 主流程（聚类→分析→upsert）
- _llm.py      —— _LLMMixin: _llm_cluster / _llm_analyze / _fallback_analysis
- service.py   —— EventClusterer 主类（__init__ + mixin 组合）
"""
from __future__ import annotations

from ._models import (
    LOOKBACK_SECONDS,
    MAX_DESC_LEN,
    MAX_ITEMS_PER_EVENT,
    MAX_RECENT_CANDIDATES,
    MAX_SUMMARY_LEN,
    MAX_TITLE_LEN,
    VENTI_DIGEST_SPEC,
    ProcessedEvent,
)
from .service import EventClusterer

__all__ = [
    "LOOKBACK_SECONDS",
    "MAX_DESC_LEN",
    "MAX_ITEMS_PER_EVENT",
    "MAX_RECENT_CANDIDATES",
    "MAX_SUMMARY_LEN",
    "MAX_TITLE_LEN",
    "VENTI_DIGEST_SPEC",
    "EventClusterer",
    "ProcessedEvent",
]
