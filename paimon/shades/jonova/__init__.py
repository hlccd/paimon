"""死执 · Jonova — 审（评审）

安全审职能（task_review / scan_plan / review_skill_declaration）在
派蒙 `paimon/core/safety/`，本子包专注**自进化提案的质量审**：

- **review_proposal**：评审 skill 自进化提案
  - 输入 prop_id（从 prior_results 解析；生执 propose 节点输出）
  - LLM 审：草案完整度 / 跟现有 skill 重叠 / tool 越权 / 边界清晰
  - 输出 ReviewVerdict 协议 JSON + 同步写 skill_proposals.review_verdict
"""
from __future__ import annotations

from .review_proposal import review_proposal

__all__ = ["review_proposal"]
