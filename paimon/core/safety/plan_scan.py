"""派蒙·plan_scan — DAG 敏感操作扫描（v7 起从死执上提派蒙）。

四影管线在生执编排出 DAG 后、空执 dispatch 前，由派蒙扫一遍敏感操作：
  - permanent_deny → 加入 blocked_ids（pipeline 剔除）
  - permanent_allow → pre_approved_ids（免询问）
  - 无记录 → items_to_ask（派蒙批量问用户）
  - session 已 allow/deny → 视为 pre_approved/blocked

subject 维度 = stage（assignee 字段值即 stage 名）。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from loguru import logger

from paimon.core.authz.cache import AuthzCache
from paimon.core.authz.sensitive_tools import describe_tool_risk

if TYPE_CHECKING:
    from paimon.shades._plan import Plan


@dataclass
class ScanItem:
    """扫描出的单个敏感操作条目（待派蒙询问用户）。"""
    subtask_id: str
    assignee: str                 # stage 名
    description: str              # 子任务描述（展示给用户看）
    sensitive_ops: list[str]      # 本节点声明的敏感工具
    blocked: bool = False
    pre_approved: bool = False


@dataclass
class ScanResult:
    """扫描整个 plan 的结果。"""
    items_to_ask: list[ScanItem] = field(default_factory=list)
    blocked_ids: list[str] = field(default_factory=list)
    pre_approved_ids: list[str] = field(default_factory=list)

    @property
    def has_questions(self) -> bool:
        return len(self.items_to_ask) > 0


def scan_plan(
    plan: "Plan",
    authz_cache: AuthzCache,
    *,
    user_id: str = "default",
    session_id: str = "",
) -> ScanResult:
    """扫 plan 中的敏感操作。"""
    result = ScanResult()

    for sub in plan.subtasks:
        ops = list(sub.sensitive_ops or [])
        if not ops:
            continue

        # subject 用 stage 维度（assignee 字段值即 stage 名）
        subject_type = "stage"
        subject_id = sub.assignee

        cached = authz_cache.get(subject_type, subject_id)
        if cached == "permanent_deny":
            result.blocked_ids.append(sub.id)
            continue
        if cached == "permanent_allow":
            result.pre_approved_ids.append(sub.id)
            continue

        # 会话级
        if session_id:
            scope = authz_cache.get_session_scope(session_id, subject_type, subject_id)
            if scope == "deny":
                result.blocked_ids.append(sub.id)
                continue
            if scope == "allow":
                result.pre_approved_ids.append(sub.id)
                continue

        result.items_to_ask.append(ScanItem(
            subtask_id=sub.id,
            assignee=sub.assignee,
            description=sub.description,
            sensitive_ops=ops,
        ))

    logger.info(
        "[派蒙·安全审·scan_plan] 共 {} 节点，{} 待询问 / {} 已放行 / {} 已禁止",
        len(plan.subtasks), len(result.items_to_ask),
        len(result.pre_approved_ids), len(result.blocked_ids),
    )
    return result


def format_scan_prompt(items: list[ScanItem]) -> str:
    """把扫描条目拼成给用户的询问文本。"""
    if not items:
        return ""
    lines = [
        f"本次任务涉及 **{len(items)}** 项敏感操作，请确认："
    ]
    for i, item in enumerate(items, 1):
        tool_hits = []
        for op in item.sensitive_ops:
            risk = describe_tool_risk(op)
            tool_hits.append(f"{op}" + (f"（{risk}）" if risk else ""))
        tools_str = " / ".join(tool_hits) if tool_hits else "敏感工具"
        desc = item.description.strip().replace("\n", " ")[:80]
        lines.append(f"[{i}] {item.assignee} · {desc}\n      需要: {tools_str}")
    lines.append("")
    lines.append(
        "答复方式：\n"
        "  • 全部放行 / 全部拒绝\n"
        "  • \"1,3\" 仅放行 1 和 3（其余默认拒绝）\n"
        "  • 永久放行 / 永久拒绝（加上永久二字会写入世界树长期生效）\n"
        "  • 30 秒无答复保守拒绝"
    )
    return "\n".join(lines)
