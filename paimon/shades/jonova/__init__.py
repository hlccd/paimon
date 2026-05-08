"""死执 · Jonova — 审（评审）

安全审职能（task_review / scan_plan / review_skill_declaration）在
派蒙 `paimon/core/safety/`，本子包专注**自进化提案的质量审**：

- **review_proposal**（待批 2 实装）：评审 skill 自进化提案
  - 输入 prop_id（从世界树 skill_proposals 域读 pending 提案）
  - LLM 审：草案完整度 / 跟现有 skill 重叠 / tool 越权 / 边界清晰
  - 输出 verdict ∈ {pass, needs_revise, reject} + notes 写回 skill_proposals
"""
