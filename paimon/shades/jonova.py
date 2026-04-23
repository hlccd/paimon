"""死执 · Jonova — 安全审查

管线职责：
  - review(task): 入口请求审（管线第一步）
  - scan_plan(plan): DAG 敏感操作扫描（每轮编排后、dispatch 前）
  - review_skill_declaration(decl): 冰神热加载的新 skill 审查（外部调用）

docs/aimon.md §2.4 四影路径权限流：
  生执编排 DAG → 死执扫敏感操作 → 排除已永久放行 → 派蒙批量询问 → 其余剔除
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from loguru import logger

from paimon.core.authz.cache import AuthzCache
from paimon.core.authz.sensitive_tools import describe_tool_risk
from paimon.foundation.irminsul import Irminsul
from paimon.foundation.irminsul.task import TaskEdict
from paimon.llm.model import Model

from ._plan import Plan

if TYPE_CHECKING:
    from paimon.foundation.irminsul.skills import SkillDecl

_REVIEW_PROMPT = """\
你是安全审查官·若纳瓦。你的职责是判断用户请求是否安全。

审查标准：
1. 是否涉及删除系统文件、修改核心配置等破坏性操作
2. 是否试图获取未授权的权限
3. 是否包含恶意代码注入或攻击指令
4. 是否违反基本安全规范

正常的编程、分析、写作、查询等请求应该放行。

只输出 JSON，格式：{"safe": true/false, "reason": "简短原因"}
不要输出任何其他内容。"""


async def review(
    task: TaskEdict,
    model: Model,
    irminsul: Irminsul,
) -> tuple[bool, str]:
    messages = [
        {"role": "system", "content": _REVIEW_PROMPT},
        {"role": "user", "content": f"请审查以下请求:\n\n{task.title}\n{task.description}"},
    ]

    try:
        raw, usage = await model._stream_text(messages)
        await model._record_primogem(task.session_id, "死执", usage, purpose="安全审查")

        raw = raw.strip()
        if raw.startswith("```"):
            lines = raw.splitlines()
            raw = "\n".join(lines[1:-1]) if len(lines) > 2 else raw

        result = json.loads(raw)
        safe = result.get("safe", True)
        reason = result.get("reason", "")

        if safe:
            logger.info("[死执] 审查通过: {}", task.title[:60])
        else:
            logger.warning("[死执] 审查拒绝: {} — {}", task.title[:60], reason)

        await irminsul.flow_append(
            task_id=task.id,
            from_agent="派蒙",
            to_agent="死执",
            action="security_review",
            payload={"safe": safe, "reason": reason},
            actor="死执",
        )

        return safe, reason

    except Exception as e:
        logger.error("[死执] 审查异常，默认放行: {}", e)
        return True, ""


# ==================== 新 skill / plugin 声明审查 ====================

_SKILL_REVIEW_PROMPT = """\
你是安全审查官·若纳瓦。你现在不是审查用户请求，而是审查一个新 skill 声明是否应该上线加载。

输入：skill 名字 / description / allowed_tools（这个 skill 声明能调用的工具白名单）/ triggers（触发词）。

判断维度：
1. description 自述的用途与 allowed_tools 是否**匹配**（例如声明自己是"查天气"却申请 Bash/Write，明显不匹配）
2. description 里是否存在**恶意语义**（exfiltration 数据外泄、注入、破坏、假装他人身份、规避权限等）
3. allowed_tools 是否**最小权限**（能用 web_fetch 就别要 Bash；能用 Read 就别要 Write）
4. triggers 是否过于宽泛（如空或一个字母，会被随便触发）

只输出 JSON，格式：{"pass": true/false, "reason": "简短原因，中文"}
不要输出任何其他内容。"""


async def review_skill_declaration(
    decl: "SkillDecl",
    model: Model,
) -> tuple[bool, str]:
    """审查 skill 声明（冰神运行时加载前调）。

    返回 (passed, reason)。LLM 调用失败时保守拒绝（不加载）。
    """
    payload = {
        "name": decl.name,
        "description": decl.description,
        "allowed_tools": decl.allowed_tools or [],
        "sensitive_tools": decl.sensitive_tools or [],
        "triggers": decl.triggers,
        "source": decl.source,
    }

    messages = [
        {"role": "system", "content": _SKILL_REVIEW_PROMPT},
        {
            "role": "user",
            "content": "请审查以下 skill 声明:\n\n"
                       + json.dumps(payload, ensure_ascii=False, indent=2),
        },
    ]

    try:
        raw, usage = await model._stream_text(messages)
        await model._record_primogem("", "死执", usage, purpose="skill 声明审查")
    except Exception as e:
        logger.warning("[死执·skill 审查] LLM 调用失败，保守拒绝: {}", e)
        return False, f"审查 LLM 调用失败: {e}"

    raw = raw.strip()
    if raw.startswith("```"):
        lines = raw.splitlines()
        raw = "\n".join(lines[1:-1]) if len(lines) > 2 else raw

    try:
        result = json.loads(raw)
    except Exception as e:
        logger.warning("[死执·skill 审查] 解析 JSON 失败，保守拒绝: {} 原始={}", e, raw[:200])
        return False, "审查结果解析失败"

    passed = bool(result.get("pass", False))
    reason = str(result.get("reason", ""))

    if passed:
        logger.info("[死执·skill 审查] 通过 {}: {}", decl.name, reason[:80])
    else:
        logger.warning("[死执·skill 审查] 拒绝 {}: {}", decl.name, reason[:80])

    return passed, reason


# ==================== DAG 敏感操作扫描（四影路径批量授权）====================

@dataclass
class ScanItem:
    """扫描出的单个敏感操作条目（待派蒙询问用户）。"""
    subtask_id: str
    assignee: str
    description: str              # 子任务描述（展示给用户看）
    sensitive_ops: list[str]      # 本节点声明的敏感工具
    # 运行期标签
    blocked: bool = False         # 已被 permanent_deny 命中 → pipeline 应剔除节点
    pre_approved: bool = False    # 已被 permanent_allow 命中（内部用；不会返回给 pipeline）


@dataclass
class ScanResult:
    """死执扫描整个 plan 的结果。"""
    items_to_ask: list[ScanItem] = field(default_factory=list)  # 需要询问用户的
    blocked_ids: list[str] = field(default_factory=list)        # 永久禁止的节点
    pre_approved_ids: list[str] = field(default_factory=list)   # 永久放行的节点（免询问）

    @property
    def has_questions(self) -> bool:
        return len(self.items_to_ask) > 0


def scan_plan(
    plan: Plan,
    authz_cache: AuthzCache,
    *,
    user_id: str = "default",
    session_id: str = "",
) -> ScanResult:
    """扫 plan 中的敏感操作。

    规则：
      - subtask.sensitive_ops 为空 → 跳过
      - 查缓存：
          * permanent_deny → 加入 blocked_ids
          * permanent_allow → 加入 pre_approved_ids
          * session 已 allow → 视为 pre_approved
          * session 已 deny → 视为 blocked
          * 无记录 → 加入 items_to_ask
      - 若同节点有多个 sensitive_ops，整体作为一个条目问（粒度更友好）
    """
    result = ScanResult()

    for sub in plan.subtasks:
        ops = list(sub.sensitive_ops or [])
        if not ops:
            continue

        # skill 粒度：用 subject=skill/<assignee> 的键查（因为目前敏感度派生在 skill 维度；
        # 后续 todo.md 2.x 会支持工具粒度）
        # 这里先按"节点"整体决策，subject_id 用 assignee 作为粗粒度 key
        subject_type = "shades_node"
        subject_id = sub.assignee  # 用中文神名做键（与派蒙天使路径的 skill 名区分）

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

        # 需要询问
        result.items_to_ask.append(ScanItem(
            subtask_id=sub.id,
            assignee=sub.assignee,
            description=sub.description,
            sensitive_ops=ops,
        ))

    logger.info(
        "[死执·scan_plan] 共 {} 节点，{} 待询问 / {} 已放行 / {} 已禁止",
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
