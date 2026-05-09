"""派蒙对话 chat 子包入口 — re-export 全部对外 API 保持原 import 路径不变。

子模块切分：
- _runtime.py     —— 状态守卫 + 压缩阈值常量（只被 chat 子包内部用）
- _persist.py     —— 一回合落盘 + 去重逻辑
- _prompt.py      —— system prompt 构造 + L1 记忆注入
- _handler.py     —— handle_chat 主对话循环（天使工具超时升级 / 压缩 / 标题）
- session.py      —— run_session_chat / stop_session_task 会话级任务调度
- entry.py        —— on_channel_message 渠道总入口（chat / skill 二选一分流）
"""
from __future__ import annotations

from .entry import on_channel_message
from .session import run_session_chat, stop_session_task

__all__ = [
    "on_channel_message",
    "run_session_chat",
    "stop_session_task",
]
