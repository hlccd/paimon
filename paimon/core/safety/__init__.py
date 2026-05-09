"""派蒙·安全闸。

派蒙作为系统出入口的同时担任全程安全闸 — 入口 / 装载 / 写入三个时点都可调用：

- **task_review**：入口任务级审（用户主动触发的 task 入口审）
- **review_skill_declaration**：skill 热加载审（skill_loader 加载 plugin / AI 自进化生成 skill 时调）
- **detect_sensitive**：敏感串过滤（memory 写入 / 知识库写入路径用，跟 LLM 审查无关）
"""
from __future__ import annotations

from .sensitive_filter import SENSITIVE_PATTERNS, detect_sensitive
from .skill_review import review_skill_declaration
from .task_review import task_review

__all__ = [
    # 任务级安全审
    "task_review",
    # skill 声明审
    "review_skill_declaration",
    # 敏感串过滤
    "detect_sensitive",
    "SENSITIVE_PATTERNS",
]
