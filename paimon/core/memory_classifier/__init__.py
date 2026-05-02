"""草神记忆/知识分类器子包入口 — re-export 全部对外 API 保持原 import 路径不变。

子模块切分：
- _common.py      —— LLM JSON 解析 / 修复 / Hygiene 通用 dataclass（被四个业务模块共用）
- memory.py       —— /remember 流程：分类 + reconcile + 落库（user/feedback/project/reference 域）
- memory_hygiene.py —— memory 域批量整理（cron + 面板手动）
- kb.py           —— 知识库录入：分类 (category/topic) + reconcile + 写盘
- kb_hygiene.py   —— knowledge 域按 category 批量整理
- _register.py    —— 启动期注册 memory_hygiene / kb_hygiene 两个 task_type
"""
from __future__ import annotations

from ._common import HygieneReport, HygieneStats
from ._register import register_task_types
from .kb import (
    KbReconcileDecision,
    KbRememberOutcome,
    classify_knowledge,
    reconcile_knowledge,
    remember_knowledge_with_reconcile,
    sanitize_kb_segment,
)
from .kb_hygiene import is_kb_hygiene_running, run_kb_hygiene
from .memory import (
    MAX_REMEMBER_CHARS,
    RECONCILE_CANDIDATE_LIMIT,
    ReconcileDecision,
    RememberOutcome,
    classify_memory,
    default_title,
    reconcile_memory,
    remember_with_reconcile,
    sanitize_subject,
)
from .memory_hygiene import is_hygiene_running, run_hygiene

__all__ = [
    "MAX_REMEMBER_CHARS",
    "RECONCILE_CANDIDATE_LIMIT",
    "HygieneReport",
    "HygieneStats",
    "KbReconcileDecision",
    "KbRememberOutcome",
    "ReconcileDecision",
    "RememberOutcome",
    "classify_knowledge",
    "classify_memory",
    "default_title",
    "is_hygiene_running",
    "is_kb_hygiene_running",
    "reconcile_knowledge",
    "reconcile_memory",
    "register_task_types",
    "remember_knowledge_with_reconcile",
    "remember_with_reconcile",
    "run_hygiene",
    "run_kb_hygiene",
    "sanitize_kb_segment",
    "sanitize_subject",
]
