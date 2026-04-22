"""空执 · Asmoday — 动态路由

管线第三步。将子任务路由到对应七神执行。
"""
from __future__ import annotations

from loguru import logger

from paimon.archons.base import Archon
from paimon.archons.nahida import NahidaArchon
from paimon.foundation.irminsul import Irminsul
from paimon.foundation.irminsul.task import Subtask, TaskEdict
from paimon.llm.model import Model

_ARCHON_REGISTRY: dict[str, Archon] = {
    "草神": NahidaArchon(),
}


async def dispatch(
    task: TaskEdict,
    subtasks: list[Subtask],
    model: Model,
    irminsul: Irminsul,
) -> str:
    results = []

    for i, sub in enumerate(subtasks):
        archon = _ARCHON_REGISTRY.get(sub.assignee)
        if not archon:
            logger.warning("[空执] 未知执行者 '{}', 回退到草神", sub.assignee)
            archon = _ARCHON_REGISTRY["草神"]

        await irminsul.flow_append(
            task_id=task.id,
            from_agent="空执",
            to_agent=sub.assignee,
            action="dispatch",
            payload={"subtask_id": sub.id},
            actor="空执",
        )

        await irminsul.subtask_update_status(sub.id, status="running", actor="空执")
        logger.info("[空执] 路由子任务 {}/{} {} → {}", i + 1, len(subtasks), sub.id, sub.assignee)

        try:
            result = await archon.execute(
                task, sub, model, irminsul,
                prior_results=results if results else None,
            )
            await irminsul.subtask_update_status(
                sub.id, status="completed", result=result[:2000], actor=sub.assignee,
            )
            results.append(result)
        except Exception as e:
            error_msg = f"执行失败: {e}"
            await irminsul.subtask_update_status(
                sub.id, status="failed", result=error_msg, actor=sub.assignee,
            )
            results.append(error_msg)
            logger.error("[空执] 子任务 {} 执行失败: {}", sub.id, e)

    return "\n\n---\n\n".join(results)
