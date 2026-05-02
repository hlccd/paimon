"""三月调度服务核心：MarchService 类（poll / fire / 任务管理 / 响铃 delegator）。

事件响铃实现拆到 _ring.py（148 行），通用 helper 拆到 _helpers.py，避免单文件超 500。
"""
from __future__ import annotations

import asyncio
import time
from typing import TYPE_CHECKING, Any

from loguru import logger

from paimon.foundation.irminsul.schedule import ScheduledTask

from ._helpers import (
    MAX_FAILURES,
    MIN_INTERVAL,
    RING_EVENT_MAX_PER_WINDOW,
    RING_EVENT_WINDOW_SECONDS,
    _cron_next,
)

if TYPE_CHECKING:
    from paimon.foundation.irminsul import Irminsul
    from paimon.foundation.leyline import Leyline


class MarchService:
    """三月守护与定时调度服务：唯一响铃入口；不直接发消息（一律走地脉/push_archive）。"""

    def __init__(self, irminsul: "Irminsul", leyline: "Leyline"):
        self._irminsul = irminsul
        self._leyline = leyline
        self._running = False
        self._running_tasks: set[str] = set()
        # 事件响铃限流状态（内存滑动窗口；重启清零可接受）
        self._event_rate_limit: dict[tuple[str, str, str], list[float]] = {}
        # 时执生命周期清扫（docs/shades/istaroth.md §核心能力）
        # 首次启动延后一个周期再扫，避免刚起服就清旧数据
        self._last_lifecycle_sweep: float = time.time()
        self._lifecycle_sweep_running: bool = False

    async def _reconcile_cron_schedules(self) -> None:
        """启动时重算所有 enabled cron 任务的 next_run_at。

        历史 next_run_at 可能因 croniter 时区 bug（按 UTC 而非本地时区解析）
        而错位 8 小时。重启时按 _cron_next 重新算一次对齐到本地时区。
        副作用：每次重启 cron 任务都会"重新对齐到下次"，错过的执行不会补；
        这是 cron 语义的合理近似，避免重启风暴。
        """
        try:
            tasks = await self._irminsul.schedule_list(enabled_only=True)
        except Exception as e:
            logger.warning("[三月] 启动 cron 重对齐：拉任务失败 {}", e)
            return
        now = time.time()
        fixed = 0
        for task in tasks:
            if task.trigger_type != "cron":
                continue
            expr = task.trigger_value.get("expr", "") if task.trigger_value else ""
            if not expr:
                continue
            try:
                new_next = _cron_next(expr, now)
            except Exception as e:
                logger.warning("[三月] cron '{}' 重算失败 task={}: {}", expr, task.id, e)
                continue
            old_next = task.next_run_at
            # 只在差距大于 30 分钟时才覆盖（避免无意义的频繁更新）
            if abs(new_next - old_next) > 30 * 60:
                try:
                    await self._irminsul.schedule_update(
                        task.id, actor="三月·重对齐", next_run_at=new_next,
                    )
                    fixed += 1
                    logger.info(
                        "[三月] cron 重对齐 task={} expr='{}' "
                        "old_next={} new_next={} ({})",
                        task.id, expr,
                        time.strftime("%m-%d %H:%M", time.localtime(old_next)) if old_next else "-",
                        time.strftime("%m-%d %H:%M", time.localtime(new_next)),
                        "本地时间",
                    )
                except Exception as e:
                    logger.warning("[三月] cron 重对齐写库失败 task={}: {}", task.id, e)
        if fixed > 0:
            logger.info("[三月] 启动 cron 重对齐：修复 {} 条错位任务", fixed)

    async def start(self) -> None:
        """启动调度循环：先重对齐 cron，再对齐到下一个整分钟轮询。"""
        self._running = True

        # 启动时纠正 cron next_run_at（修历史时区错位 + 重启对齐）
        await self._reconcile_cron_schedules()

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
        """停止调度循环（设置 _running=False 让下个 sleep 后退出）。"""
        self._running = False

    async def _poll(self) -> None:
        """单次轮询：拉到期任务 → bg fire；并按周期触发生命周期清扫。"""
        from paimon.foundation.bg import bg
        now = time.time()
        due_tasks = await self._irminsul.schedule_list_due(now)
        for task in due_tasks:
            if task.id in self._running_tasks:
                continue
            bg(self._fire_task(task), label=f"march·{task.task_type}·{task.id[:8]}")

        # 时执生命周期清扫（独立 task 运行，不阻塞轮询）
        self._maybe_trigger_lifecycle_sweep(now)

    def _maybe_trigger_lifecycle_sweep(self, now: float) -> None:
        """按 config.lifecycle_sweep_interval_hours 节奏触发生命周期清扫。

        - 单例：同时只有一个 sweep 在跑
        - 开关：config.lifecycle_sweep_enabled
        - 间隔：clamp 到 [1h, 168h]
        """
        from paimon.config import config

        if not config.lifecycle_sweep_enabled:
            return
        if self._lifecycle_sweep_running:
            return
        interval_hours = max(1, min(int(config.lifecycle_sweep_interval_hours), 168))
        if now - self._last_lifecycle_sweep < interval_hours * 3600:
            return

        self._last_lifecycle_sweep = now
        from paimon.foundation.bg import bg
        bg(self._run_lifecycle_sweep(now), label="march·生命周期清扫")

    async def _run_lifecycle_sweep(self, now: float) -> None:
        """调时执 run_lifecycle_sweep；整条链路失败只记 log 不抛。"""
        from paimon.config import config
        from paimon.shades._lifecycle import run_lifecycle_sweep
        from paimon.state import state

        self._lifecycle_sweep_running = True
        try:
            logger.info("[三月] 触发时执·生命周期清扫")
            await run_lifecycle_sweep(
                self._irminsul, config,
                session_mgr=state.session_mgr,
                now=now,
            )
        except Exception as e:
            logger.error("[三月·生命周期] 清扫异常（已吞，下轮重试）: {}", e)
        finally:
            self._lifecycle_sweep_running = False

    async def _fire_task(self, task: ScheduledTask) -> None:
        """触发单条任务：发地脉 march.ring → 算下次时间 → 失败累计 + 退避。"""
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
        """记一次失败：累计 consecutive_failures；指数退避；3 次自动 disable。"""
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
        """完成一次后算下次时间：once → None；interval → +seconds；cron → next。"""
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
                    return _cron_next(expr, finished_at)
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
        *,
        task_type: str = "user",
        source_entity_id: str = "",
    ) -> str:
        """创建定时任务。

        task_type='user' 时 `prompt` 作自然语言喂给 LLM；非 user 类型（方案 D）
        prompt 仅用作 UI 回退显示文本，真正的路由靠 task_type + source_entity_id。
        """
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
            task_type=task_type,
            source_entity_id=source_entity_id,
        )
        task_id = await self._irminsul.schedule_create(task, actor="三月")
        logger.info(
            "[三月] 创建任务 {} type={} kind={} next={:.0f}",
            task_id, trigger_type, task_type, next_run,
        )
        return task_id

    async def delete_task(self, task_id: str) -> bool:
        """删任务（世界树持久化删除）。"""
        return await self._irminsul.schedule_delete(task_id, actor="三月")

    async def pause_task(self, task_id: str) -> bool:
        """暂停任务（仅置 enabled=False，保留记录便于面板观察）。"""
        return await self._irminsul.schedule_update(
            task_id, actor="三月", enabled=False,
        )

    async def resume_task(self, task_id: str) -> bool:
        """恢复任务：清零 failure / last_error，重算 next_run_at。"""
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
        """列全部任务（启用/未启用都返回，给 /tasks 面板）。"""
        return await self._irminsul.schedule_list()

    # ---- 事件响铃 ----

    async def ring_event(
        self,
        *,
        channel_name: str,
        chat_id: str,
        source: str,
        message: str = "",
        prompt: str = "",
        task_id: str = "",
        level: str = "silent",
        extra: dict | None = None,
        dedup_per_day: bool = False,
    ) -> bool:
        """事件响铃 delegator → _ring.ring_event_impl；行为见该文件 docstring。"""
        from ._ring import ring_event_impl
        return await ring_event_impl(
            self,
            channel_name=channel_name, chat_id=chat_id,
            source=source, message=message, prompt=prompt, task_id=task_id,
            level=level, extra=extra, dedup_per_day=dedup_per_day,
        )

    def _rate_limit_check(self, key: tuple) -> bool:
        """事件响铃滑动窗口限流。返回 True=允许通过；False=超限拒绝。"""
        now = time.time()
        window = self._event_rate_limit.setdefault(key, [])
        cutoff = now - RING_EVENT_WINDOW_SECONDS
        while window and window[0] < cutoff:
            window.pop(0)
        if len(window) >= RING_EVENT_MAX_PER_WINDOW:
            return False
        window.append(now)
        return True

    @staticmethod
    def _calc_initial_next_run(trigger_type: str, trigger_value: dict, now: float) -> float:
        """新建/恢复任务时初始下次运行时间：once 用 at；interval 用 +seconds；cron 用 next。"""
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
                    return _cron_next(expr, now)
                except Exception:
                    pass
            return now + 60

        return now + 60
