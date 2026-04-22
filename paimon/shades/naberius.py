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
- 雷神: 写代码（含自检），代码生成、重构
- 水神: 评审挑刺（方案/代码/文档/架构），质量终审
- 火神: Shell/代码执行、部署，仅在用户明确要求执行时使用
- 风神: 新闻采集、舆情分析、信息整理
- 岩神: 理财分析、红利股、资产管理
- 冰神: Skill 生态管理、扫描评估

分解规则：
1. 每个子任务必须指定一个执行者（assignee），填中文名如"草神"、"雷神"
2. 子任务描述要具体、可执行
3. 根据任务性质选择合适的执行者，不要全部给草神
4. 简单任务可以只有 1 个子任务，复杂任务拆分为 2-5 个
5. 写代码再评审的流程：先分给雷神写，再分给水神审

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
