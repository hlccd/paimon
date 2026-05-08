"""生执 · Naberius — 生（生成 + 落地产物）

两段职能（公开 API）：

1. **编排**（plan）：LLM 把任务拆 DAG，节点带 stage 标签
   - plan() 入口在 plan.py
   - 代码任务硬编码模板在 code_pipeline.py
   - LLM 输出解析 helper 在 _parser.py

2. **产出**（produce）：实现 6 个产物 stage
   - produce_spec / produce_design / produce_code（调对应 skill）
   - simple_run（simple_code / exec / chat 共用 LLM tool-loop）
"""
from __future__ import annotations

from .plan import plan
from .produce import produce_code, produce_design, produce_spec
from ._simple import simple_run

__all__ = [
    "plan",
    "produce_spec",
    "produce_design",
    "produce_code",
    "simple_run",
]
