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

# 轮询粒度：每分钟的 :00 对齐
# 设计取舍：多数定时场景（新闻、股价、提醒）精度到分钟已经足够；
# 对齐 :00 之后，`cron * * * * *` / `interval=60` 都会在整分钟触发，日志时间戳整齐好读。
POLL_INTERVAL = 60
MAX_FAILURES = 3
# interval 下限：小于 60s 的设置会被提升到 60s，避免虚假的高精度预期
MIN_INTERVAL = 60


class MarchService:
    def __init__(self, irminsul: Irminsul, leyline: Leyline):
        self._irminsul = irminsul
        self._leyline = leyline
        self._running = False
        self._running_tasks: set[str] = set()

    async def start(self) -> None:
        self._running = True

        # 启动对齐：算到下一个整分钟（:00）还有多久，先睡到那里再开始轮询
        # 之后每轮都按"当前时间到下一个 :00"精确睡眠，避免长期漂移
        now = time.time()
        initial_delay = 60 - (now % 60)
        if initial_delay < 0.5:
            initial_delay += 60  # 极少见的恰好在 :00 启动，再等一分钟
        logger.info(
            "[三月] 调度服务已启动 (轮询=每分钟 :00；首次对齐延迟 {:.1f}s)",
            initial_delay,
        )

        try:
            await asyncio.sleep(initial_delay)

            while self._running:
                try:
                    await self._poll()
                except Exception as e:
                    logger.error("[三月] 轮询异常: {}", e)

                # 每次睡到下一个 :00，而不是 sleep(60)——后者会累积漂移
                now = time.time()
                next_delay = 60 - (now % 60)
                if next_delay < 0.5:
                    next_delay += 60
                await asyncio.sleep(next_delay)
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
                # 最小间隔保护：避免 LLM 参数解析偏差或用户笔误产生过短周期
                seconds = max(seconds, MIN_INTERVAL)
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
            seconds = max(seconds, MIN_INTERVAL)  # 最小 interval 保护
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
