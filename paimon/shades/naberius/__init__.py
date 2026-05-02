"""生执 · Naberius 子包入口 — 仅对外暴露 plan 函数。

主流程：plan() 在 plan.py。代码任务 pipeline 拆到 code_pipeline.py，
LLM 输出解析 helper 拆到 _parser.py。
"""
from __future__ import annotations

from .plan import plan

__all__ = ["plan"]
