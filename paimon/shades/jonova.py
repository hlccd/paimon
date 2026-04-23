"""死执 · Jonova — 安全审查

管线第一步。审查用户请求的安全性，拒绝危险操作。
同时对接魔女会 & 冰神的新 skill / plugin 声明审查（见 review_skill_declaration）。
"""
from __future__ import annotations

import json
from typing import TYPE_CHECKING

from loguru import logger

from paimon.foundation.irminsul import Irminsul
from paimon.foundation.irminsul.task import TaskEdict
from paimon.llm.model import Model

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
