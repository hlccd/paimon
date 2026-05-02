"""风神 · 巴巴托斯 archon 子包

舆情采集 + 日报组装 + P0 预警；docs/archons/venti.md。

子模块：
- _models.py     —— 模块级常量 + system prompts + 兜底 digest 生成
- _collect.py    —— _CollectMixin: collect_subscription / 采集 impl / 空跑占位 / web_search
- _digest.py     —— _DigestMixin: 传统 _compose_digest + 事件级 _compose_event_digest
- _alert.py      —— _AlertMixin: P0 即时预警投送
- service.py     —— VentiArchon 主类（4 mixin 组合）
- _register.py   —— register_task_types / register_subscription_types / run_web_search_collect
"""
from __future__ import annotations

from ._register import (
    register_subscription_types,
    register_task_types,
    run_web_search_collect,
)
from .service import VentiArchon

__all__ = [
    "VentiArchon",
    "register_subscription_types",
    "register_task_types",
    "run_web_search_collect",
]
