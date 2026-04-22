"""生执 · Naberius — 任务编排

管线第二步。将复杂任务分解为子任务 DAG。
"""
from __future__ import annotations

import json
from uuid import uuid4

from loguru import logger

from paimon.foundation.irminsul import Irminsul
from paimon.foundation.irminsul.task import Subtask, TaskEdict
from paimon.llm.model import Model

_DECOMPOSE_PROMPT = """\
你是任务编排官·纳贝里士。你的职责是将复杂任务分解为可执行的子任务。

当前可用的执行者（七神）：
- 草神: 推理、知识整合、文书起草、方案分析

分解规则：
1. 每个子任务必须指定一个执行者（assignee）
2. 子任务描述要具体、可执行
3. 当前只有草神可用，所有子任务 assignee 填"草神"
4. 简单任务可以只有 1 个子任务，复杂任务拆分为 2-5 个

只输出 JSON 数组，格式：
[{"assignee": "草神", "description": "具体任务描述"}]
不要输出任何其他内容。"""


async def decompose(
    task: TaskEdict,
    model: Model,
    irminsul: Irminsul,
) -> list[Subtask]:
    messages = [
        {"role": "system", "content": _DECOMPOSE_PROMPT},
        {"role": "user", "content": f"请分解以下任务:\n\n{task.title}\n{task.description}"},
    ]

    try:
        raw, usage = await model._stream_text(messages)
        await model._record_primogem(task.session_id, "生执", usage, purpose="任务编排")

        raw = raw.strip()
        if raw.startswith("```"):
            lines = raw.splitlines()
            raw = "\n".join(lines[1:-1]) if len(lines) > 2 else raw

        items = json.loads(raw)
        if not isinstance(items, list) or not items:
            items = [{"assignee": "草神", "description": task.description}]

    except Exception as e:
        logger.warning("[生执] 分解异常，整体交给草神: {}", e)
        items = [{"assignee": "草神", "description": task.description}]

    subtasks = []
    for item in items:
        sub = Subtask(
            id=uuid4().hex[:12],
            task_id=task.id,
            parent_id=None,
            assignee=item.get("assignee", "草神"),
            description=item.get("description", ""),
            status="pending",
        )
        await irminsul.subtask_create(sub, actor="生执")
        subtasks.append(sub)

    await irminsul.flow_append(
        task_id=task.id,
        from_agent="死执",
        to_agent="生执",
        action="decompose",
        payload={"subtask_count": len(subtasks)},
        actor="生执",
    )

    logger.info("[生执] 分解为 {} 个子任务", len(subtasks))
    return subtasks
