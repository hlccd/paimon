"""三月 (March) — 守护与定时调度服务

核心约束（来自架构文档）：
- 三月不直接对用户发消息，一切通过派蒙（走地脉 march.ring）
- 三月不自己运行 LLM，需要 LLM 时转发给派蒙处理
- 三月是唯一响铃入口

子模块：
- _helpers.py  —— today_local_bounds / _cron_next / 模块常量
- _ring.py     —— ring_event_impl 实现（148 行，service.py 的方法 delegate 到这里）
- service.py   —— MarchService 主类
"""
from __future__ import annotations

from ._helpers import (
    MAX_FAILURES,
    MIN_INTERVAL,
    POLL_INTERVAL,
    RING_EVENT_MAX_PER_WINDOW,
    RING_EVENT_WINDOW_SECONDS,
    _cron_next,
    today_local_bounds,
)
from .service import MarchService

__all__ = [
    "MAX_FAILURES",
    "MIN_INTERVAL",
    "MarchService",
    "POLL_INTERVAL",
    "RING_EVENT_MAX_PER_WINDOW",
    "RING_EVENT_WINDOW_SECONDS",
    "_cron_next",
    "today_local_bounds",
]
