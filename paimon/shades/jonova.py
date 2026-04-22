"""死执 · Jonova — 安全审查

管线第一步。审查用户请求的安全性，拒绝危险操作。
"""
from __future__ import annotations

import json

from loguru import logger

from paimon.foundation.irminsul import Irminsul
from paimon.foundation.irminsul.task import TaskEdict
from paimon.llm.model import Model

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
