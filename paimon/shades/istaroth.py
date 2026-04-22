"""时执 · Istaroth — 生命周期管理

管线最后一步。归档任务、写审计记录。
"""
from __future__ import annotations

import time

from loguru import logger

from paimon.foundation.irminsul import Irminsul
from paimon.foundation.irminsul.task import TaskEdict


async def archive(task: TaskEdict, irminsul: Irminsul) -> None:
    await irminsul.task_update_status(task.id, status="completed", actor="时执")

    subtasks = await irminsul.subtask_list(task.id)
    summary = {
        "total_subtasks": len(subtasks),
        "completed": sum(1 for s in subtasks if s.status == "completed"),
        "failed": sum(1 for s in subtasks if s.status == "failed"),
    }

    await irminsul.audit_append(
        event_type="task_completed",
        payload=summary,
        task_id=task.id,
        session_id=task.session_id,
        actor="时执",
    )

    await irminsul.task_update_lifecycle(task.id, stage="cold", actor="时执")

    logger.info(
        "[时执] 归档完成 task={} (子任务: {}完成/{}失败)",
        task.id, summary["completed"], summary["failed"],
    )
