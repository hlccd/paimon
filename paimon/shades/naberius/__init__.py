"""生执 · Naberius — 生

职能：
- **propose_skill**：从 task / 历史归档凝练 skill 草案落 skill_proposals 域
- **revise_proposal**：根据用户在面板上提的反馈重写已有草案（in-place）
"""
from __future__ import annotations

from .propose import propose_skill
from .revise import revise_proposal, run_revise_and_review_chain

__all__ = ["propose_skill", "revise_proposal", "run_revise_and_review_chain"]
