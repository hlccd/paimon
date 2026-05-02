"""派蒙对话 chat 子包入口 — re-export 全部对外 API 保持原 import 路径不变。

子模块切分：
- _runtime.py     —— 状态守卫 + 压缩阈值常量（只被 chat 子包内部用）
- _persist.py     —— 一回合落盘 + 四影补录（去重逻辑共用）
- _prompt.py      —— system prompt 构造 + L1 记忆注入
- _handler.py     —— handle_chat 主对话循环（天使工具超时升级 / 压缩 / 标题）
- session.py      —— run_session_chat / stop_session_task 会话级任务调度
- shades_bridge.py —— run_shades_pipeline 同步等四影 pipeline
- entry.py        —— on_channel_message 渠道总入口 + enter_shades_pipeline_background 流式/批次分流
"""
from __future__ import annotations

from .entry import enter_shades_pipeline_background, on_channel_message
from .session import run_session_chat, stop_session_task
from .shades_bridge import run_shades_pipeline

__all__ = [
    "enter_shades_pipeline_background",
    "on_channel_message",
    "run_session_chat",
    "run_shades_pipeline",
    "stop_session_task",
]
