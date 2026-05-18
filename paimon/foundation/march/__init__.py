"""三月 (March) — 守护与定时调度服务

核心约束（来自架构文档）：
- 三月不直接对用户发消息（事件归档走 push_archive 表，面板拉历史展示）
- 三月不自己运行 LLM，需要 LLM 时转发给派蒙处理

子模块：
- _helpers.py  —— today_local_bounds / _cron_next / 模块常量
- service.py   —— MarchService 主类
"""
from __future__ import annotations

from ._helpers import (
    MAX_FAILURES,
    MIN_INTERVAL,
    POLL_INTERVAL,
    _cron_next,
    today_local_bounds,
)
from .service import MarchService

__all__ = [
    "MAX_FAILURES",
    "MIN_INTERVAL",
    "MarchService",
    "POLL_INTERVAL",
    "_cron_next",
    "today_local_bounds",
]
