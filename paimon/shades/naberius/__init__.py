"""生执 · Naberius — 生（编排 + 产出）

两段职能（公开 API）：

1. **编排**（plan）：LLM 把任务拆 DAG，节点带 stage 标签
   - plan() 入口在 plan.py
   - LLM 输出解析 helper 在 _parser.py

2. **产出**：
   - **propose_skill**（待批 2 实装）：凝练 skill 草案落世界树 skill_proposals 域
   - **exec**：shell / 重型工具（saga 补偿用）— simple_run 共用
   - **chat**：通用 LLM 推理 / 兜底 — simple_run 共用
"""
from __future__ import annotations

from .plan import plan
from ._simple import simple_run

__all__ = [
    "plan",
    "simple_run",
]
