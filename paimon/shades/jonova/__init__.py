"""死执 · Jonova — 审（评审 + 自检）

v7：安全审职能（task_review / scan_plan / review_skill_declaration）已上提到
派蒙 `paimon/core/safety/`，本子包专注质量审：

1. **review**（评审循环）：在四影管线里给生执的产物打 verdict
   - review(stage, task, subtask, model, irminsul, prior_results) → 文本（含 verdict JSON）
   - stage ∈ {review_spec, review_design, review_code}
   - 实现在 review.py（轻量 LLM JSON / 重型 check skill 双路径）

2. **self_check**（静态质量门）：py_compile + ruff + pytest
   - run_self_check(workspace) → {ok, log, details}
   - 实现在 self_check.py
   - 调用方：生执 produce_code / simple_run(simple_code) 跑完后即时调；
     review_code heavy 路径里也间接通过 check skill 调
"""
from __future__ import annotations

from .review import review, run_review_code, run_review_design, run_review_spec
from .self_check import run_self_check

__all__ = [
    "review",
    "run_review_spec",
    "run_review_design",
    "run_review_code",
    "run_self_check",
]
