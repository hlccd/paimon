"""四影管线 — 固定调用链：死执 → 生执 → 空执 → 七神 → 时执"""
from __future__ import annotations

import time
from uuid import uuid4

from loguru import logger

from paimon.foundation.irminsul import Irminsul
from paimon.foundation.irminsul.task import TaskEdict
from paimon.llm.model import Model
from paimon.shades import jonova, naberius, asmoday, istaroth


class ShadesPipeline:

    def __init__(self, model: Model, irminsul: Irminsul):
        self._model = model
        self._irminsul = irminsul

    async def run(
        self,
        user_input: str,
        session_id: str = "",
        escalation_reason: str | None = None,
    ) -> str:
        task = await self._create_task(user_input, session_id, escalation_reason)
        if escalation_reason:
            logger.info(
                "[四影] 魔女会转入 task={} reason={}",
                task.id, escalation_reason,
            )
        logger.info("[四影] 管线启动 task={} title={}", task.id, task.title[:60])

        try:
            safe, reason = await jonova.review(task, self._model, self._irminsul)
            if not safe:
                await self._irminsul.task_update_status(task.id, status="rejected", actor="死执")
                return f"请求未通过安全审查: {reason}"

            subtasks = await naberius.decompose(task, self._model, self._irminsul)

            await self._irminsul.task_update_status(task.id, status="running", actor="空执")
            results = await asmoday.dispatch(task, subtasks, self._model, self._irminsul)

            await istaroth.archive(task, self._irminsul)

            logger.info("[四影] 管线完成 task={}", task.id)
            return results

        except Exception as e:
            logger.error("[四影] 管线异常 task={}: {}", task.id, e)
            await self._irminsul.task_update_status(task.id, status="failed", actor="四影")
            return f"任务执行失败: {e}"

    async def _create_task(
        self,
        user_input: str,
        session_id: str,
        escalation_reason: str | None = None,
    ) -> TaskEdict:
        title = user_input[:100].strip()
        if escalation_reason:
            description = (
                f"{user_input}\n"
                f"---\n"
                f"[魔女会转交] 天使路径失败原因：{escalation_reason}"
            )
            creator = "派蒙·魔女会"
        else:
            description = user_input
            creator = "派蒙"
        task = TaskEdict(
            id=uuid4().hex[:12],
            title=title,
            description=description,
            creator=creator,
            status="pending",
            session_id=session_id,
            created_at=time.time(),
            updated_at=time.time(),
        )
        await self._irminsul.task_create(task, actor=creator)
        return task
