"""
三月 (March) — 守护与定时调度服务

核心约束（来自架构文档）：
- 三月不直接对用户发消息，一切通过派蒙（走地脉 march.ring）
- 三月不自己运行 LLM，需要 LLM 时转发给派蒙处理
- 三月是唯一响铃入口
"""
from __future__ import annotations

import asyncio
import json
import time
from typing import TYPE_CHECKING, Any

from loguru import logger

if TYPE_CHECKING:
    from paimon.foundation.irminsul import Irminsul
    from paimon.foundation.leyline import Leyline

from paimon.foundation.irminsul.schedule import ScheduledTask

POLL_INTERVAL = 30
MAX_FAILURES = 3


class MarchService:
    def __init__(self, irminsul: Irminsul, leyline: Leyline):
        self._irminsul = irminsul
        self._leyline = leyline
        self._running = False
        self._running_tasks: set[str] = set()

    async def start(self) -> None:
        self._running = True
        logger.info("[三月] 调度服务已启动 (轮询间隔={}s)", POLL_INTERVAL)
        try:
            while self._running:
                try:
                    await self._poll()
                except Exception as e:
                    logger.error("[三月] 轮询异常: {}", e)
                await asyncio.sleep(POLL_INTERVAL)
        except asyncio.CancelledError:
            pass
        finally:
            self._running = False
            logger.info("[三月] 调度服务已停止")

    async def stop(self) -> None:
        self._running = False

    async def _poll(self) -> None:
        now = time.time()
        due_tasks = await self._irminsul.schedule_list_due(now)
        for task in due_tasks:
            if task.id in self._running_tasks:
                continue
            asyncio.create_task(self._fire_task(task))

    async def _fire_task(self, task: ScheduledTask) -> None:
        self._running_tasks.add(task.id)
        try:
            logger.info("[三月] 响铃 task={} prompt={}", task.id, task.task_prompt[:60])

            await self._leyline.publish(
                "march.ring",
                {
                    "task_id": task.id,
                    "chat_id": task.chat_id,
                    "channel_name": task.channel_name,
                    "prompt": task.task_prompt,
                },
                source="三月",
            )

            now = time.time()
            next_run = self._calc_next_run(task, now)
            update_fields: dict[str, Any] = {
                "last_run_at": now,
                "last_error": "",
                "consecutive_failures": 0,
            }

            if next_run is None:
                update_fields["enabled"] = False
                update_fields["next_run_at"] = 0
            else:
                update_fields["next_run_at"] = next_run

            await self._irminsul.schedule_update(task.id, actor="三月", **update_fields)

        except Exception as e:
            logger.error("[三月] 任务 {} 执行失败: {}", task.id, e)
            await self._mark_failure(task, str(e))
        finally:
            self._running_tasks.discard(task.id)

    async def _mark_failure(self, task: ScheduledTask, error: str) -> None:
        failures = task.consecutive_failures + 1
        update_fields: dict[str, Any] = {
            "last_error": error[:500],
            "consecutive_failures": failures,
            "last_run_at": time.time(),
        }

        if failures >= MAX_FAILURES:
            update_fields["enabled"] = False
            update_fields["next_run_at"] = 0
            logger.warning("[三月] 任务 {} 连续失败 {} 次，已自动禁用", task.id, failures)
        else:
            backoff = min(60 * (2 ** (failures - 1)), 3600)
            update_fields["next_run_at"] = time.time() + backoff
            logger.warning("[三月] 任务 {} 失败 ({}/{}), 退避 {}s", task.id, failures, MAX_FAILURES, backoff)

        await self._irminsul.schedule_update(task.id, actor="三月", **update_fields)

    @staticmethod
    def _calc_next_run(task: ScheduledTask, finished_at: float) -> float | None:
        if task.trigger_type == "once":
            return None

        if task.trigger_type == "interval":
            seconds = task.trigger_value.get("seconds", 0)
            if seconds > 0:
                return finished_at + seconds
            return None

        if task.trigger_type == "cron":
            expr = task.trigger_value.get("expr", "")
            if expr:
                try:
                    from croniter import croniter
                    cron = croniter(expr, finished_at)
                    return cron.get_next(float)
                except Exception as e:
                    logger.error("[三月] cron 表达式解析失败 '{}': {}", expr, e)
            return None

        return None

    # ---- 任务管理 API ----

    async def create_task(
        self,
        chat_id: str,
        channel_name: str,
        prompt: str,
        trigger_type: str,
        trigger_value: dict,
    ) -> str:
        now = time.time()
        next_run = self._calc_initial_next_run(trigger_type, trigger_value, now)

        task = ScheduledTask(
            chat_id=chat_id,
            channel_name=channel_name,
            task_prompt=prompt,
            trigger_type=trigger_type,
            trigger_value=trigger_value,
            next_run_at=next_run,
            created_at=now,
        )
        task_id = await self._irminsul.schedule_create(task, actor="三月")
        logger.info("[三月] 创建任务 {} type={} next={:.0f}", task_id, trigger_type, next_run)
        return task_id

    async def delete_task(self, task_id: str) -> bool:
        return await self._irminsul.schedule_delete(task_id, actor="三月")

    async def pause_task(self, task_id: str) -> bool:
        return await self._irminsul.schedule_update(
            task_id, actor="三月", enabled=False,
        )

    async def resume_task(self, task_id: str) -> bool:
        task = await self._irminsul.schedule_get(task_id)
        if not task:
            return False
        now = time.time()
        next_run = self._calc_initial_next_run(task.trigger_type, task.trigger_value, now)
        return await self._irminsul.schedule_update(
            task_id, actor="三月",
            enabled=True, consecutive_failures=0, last_error="",
            next_run_at=next_run,
        )

    async def list_tasks(self) -> list[ScheduledTask]:
        return await self._irminsul.schedule_list()

    @staticmethod
    def _calc_initial_next_run(trigger_type: str, trigger_value: dict, now: float) -> float:
        if trigger_type == "once":
            return trigger_value.get("at", now + 60)

        if trigger_type == "interval":
            seconds = trigger_value.get("seconds", 60)
            return now + seconds

        if trigger_type == "cron":
            expr = trigger_value.get("expr", "")
            if expr:
                try:
                    from croniter import croniter
                    return croniter(expr, now).get_next(float)
                except Exception:
                    pass
            return now + 60

        return now + 60
