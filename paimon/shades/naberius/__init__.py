"""生执 · Naberius — 生（编排 + 产出）

两段职能（公开 API）：

1. **编排**（plan）：LLM 把任务拆 DAG，节点带 stage 标签
   - plan() 入口在 plan.py
   - LLM 输出解析 helper 在 _parser.py

2. **产出**：
   - **propose_skill**：从 task / 历史归档凝练 skill 草案落 skill_proposals 域
   - **exec / chat**：兜底 LLM tool-loop（exec=shell+saga 补偿；chat=通用兜底）
"""
from __future__ import annotations

from .plan import plan
from .propose import propose_skill
from ._simple import simple_run

__all__ = [
    "plan",
    "propose_skill",
    "simple_run",
]
