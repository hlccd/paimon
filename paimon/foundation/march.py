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

# 事件响铃限流（内存滑动窗口）：每个 (source, channel, chat_id) 60s 最多 10 条
# docs/foundation/march.md §推送响铃
RING_EVENT_WINDOW_SECONDS = 60
RING_EVENT_MAX_PER_WINDOW = 10


def today_local_bounds(now: float | None = None) -> tuple[float, float]:
    """返回当地时区今天 [00:00, 次日 00:00) 的 unix 秒区间。

    用于 ring_event(dedup_per_day=True) 计算日级幂等键。与前端的
    `new Date(Y, M-1, D, 0,0,0).getTime()/1000` 保持一致（同机器时区）。
    """
    t = time.time() if now is None else now
    lt = time.localtime(t)
    midnight = time.mktime(
        (lt.tm_year, lt.tm_mon, lt.tm_mday, 0, 0, 0, 0, 0, lt.tm_isdst)
    )
    return midnight, midnight + 86400


def _cron_next(expr: str, base_ts: float) -> float:
    """计算 cron 表达式相对 base_ts 的下次触发 unix 时间戳。

    必须显式用 timezone-aware datetime 喂给 croniter——否则 croniter 把 cron
    解析为 UTC 而非系统本地时区（即使系统 timezone 已正确配置）。
    举例：cron '0 12 * * *' 在中国大陆 (UTC+8) 应返回北京时间 12:00 unix，
    但如果传 unix timestamp 或 naive datetime，会返回 UTC 12:00 (= 北京 20:00)。
    """
    from datetime import datetime
    from croniter import croniter

    # astimezone() 无参数 = 用系统本地时区，结果是 timezone-aware datetime
    base_dt = datetime.fromtimestamp(base_ts).astimezone()
    nxt_dt = croniter(expr, base_dt).get_next(datetime)
    return nxt_dt.timestamp()


class MarchService:
    def __init__(self, irminsul: Irminsul, leyline: Leyline):
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
        self._running = False

    async def _poll(self) -> None:
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
        """事件响铃入口（2026-04-25 改造为静默归档）。

        历史：原本经地脉 `march.ring` 投递到聊天会话，污染对话流。
        现在：所有 ring_event 调用静默落地到世界树 `push_archive` 域，
        WebUI 导航栏全局红点 + 抽屉消费；聊天会话只承载用户对话 + /schedule
        定时任务（_fire_task 路径不变）。

        参数：
          channel_name: 推送目标频道（webui / telegram / qq），仅供归档元信息
          chat_id:      推送目标会话 id（同上，归档用）
          source:       调用方（"风神·舆情日报" / "风神·舆情预警" / "岩神·..."）
          message:      整理好的 markdown 文案（必填；prompt 字段已废弃）
          prompt:       已废弃，传入会被并入 message 末尾（保兼容）
          task_id:      可选，关联的定时任务 id（写入 extra_json）
          level:        'silent'（默认，不打断）| 'loud'（预留，当前实现仍是静默）
          dedup_per_day: 日级幂等模式（默认 False）。True 时按 (actor, source,
                        当地日期) 去重：当日首次响铃新建一条；同日再次响铃且
                        message 未变 → no-op；message 变了 → 原地更新并 reset
                        未读。适用于「每日订阅日报」/「红利股变化」这类 cron
                        + 手动刷新会重复推送的场景。事件驱动型（P0 预警）应
                        保持 False。dedup 路径跳过滑窗限流（upsert 本身幂等）。

        返回：
          True  — 已归档（含 created / updated / unchanged）
          False — 被限流拒绝（仅非 dedup 路径）

        抛出：
          ValueError — message 为空 / source / channel_name / chat_id 缺失
        """
        # prompt 字段早期设计为 LLM 人格化提示，现已废弃；如调用方还传，并入 message
        if prompt and not message:
            message = prompt
        elif prompt and message:
            message = f"{message}\n\n{prompt}"
        if not message:
            raise ValueError("ring_event: message 非空（prompt 已废弃，请用 message）")
        # strip 校验
        source = (source or "").strip()
        channel_name = (channel_name or "").strip()
        chat_id = (chat_id or "").strip()
        if not source or not channel_name or not chat_id:
            raise ValueError("ring_event: source / channel_name / chat_id 均必填")
        if any(c in source for c in "\n\r\t"):
            raise ValueError("ring_event: source 不能含换行/制表符")

        # 非 dedup 路径才走滑窗限流；dedup 是幂等 upsert，重复调用本身无副作用
        if not dedup_per_day:
            key = (source, channel_name, chat_id)
            if not self._rate_limit_check(key):
                logger.warning(
                    "[三月·事件响铃] 限流拒绝 source={} channel={}/{} "
                    "({}s 内已 ≥{} 次)",
                    source, channel_name, chat_id[:20],
                    RING_EVENT_WINDOW_SECONDS, RING_EVENT_MAX_PER_WINDOW,
                )
                return False

        # 从 source 推出 actor（"风神·舆情日报" → "风神"）；用于面板按神分组
        actor = source.split("·", 1)[0] if "·" in source else source

        # 落地到 push_archive（静默归档）
        # extra: 调用方扩展字段（如 sub_id / event_id / change_id）+ task_id（如有）
        merged_extra: dict = dict(extra) if extra else {}
        if task_id and "task_id" not in merged_extra:
            merged_extra["task_id"] = task_id
        rec_id = ""
        upsert_status = ""  # created / updated / unchanged（仅 dedup 路径有值）
        try:
            if dedup_per_day:
                day_start, day_end = today_local_bounds()
                upsert_status, rec_id = await self._irminsul.push_archive_upsert_daily(
                    source=source, actor=actor,
                    message_md=message,
                    day_start=day_start, day_end=day_end,
                    channel_name=channel_name, chat_id=chat_id,
                    level=level,
                    extra=merged_extra,
                )
            else:
                rec_id = await self._irminsul.push_archive_create(
                    source=source, actor=actor,
                    message_md=message,
                    channel_name=channel_name, chat_id=chat_id,
                    level=level,
                    extra=merged_extra,
                )
        except Exception as e:
            logger.error("[三月·事件响铃] 归档失败 source={}: {}", source, e)
            return False

        # 通知 WebUI 红点更新（前端 SSE 可订阅；当前用前端 30s 轮询，
        # 这条 publish 是预留扩展点）
        # dedup 路径下 unchanged 状态不再触发红点（用户既然已读、内容也没变）
        publish_event = not (dedup_per_day and upsert_status == "unchanged")
        if publish_event:
            try:
                await self._leyline.publish(
                    "push.archived",
                    {"id": rec_id, "actor": actor, "source": source, "level": level},
                    source=f"三月·事件响铃@{actor}",
                )
            except Exception as e:
                logger.debug("[三月·事件响铃] leyline publish 失败（不影响归档）: {}", e)

        if dedup_per_day:
            logger.info(
                "[三月·事件响铃] source={} → push_archive {} (actor={} len={} daily={})",
                source, rec_id, actor, len(message), upsert_status,
            )
        else:
            logger.info(
                "[三月·事件响铃] source={} → push_archive {} (actor={} len={})",
                source, rec_id, actor, len(message),
            )

        # audit 落盘（失败不影响推送链路）
        try:
            await self._irminsul.audit_append(
                event_type="march_ring_event",
                payload={
                    "source": source,
                    "actor": actor,
                    "archive_id": rec_id,
                    "channel_name": channel_name,
                    "chat_id": chat_id,
                    "level": level,
                    "message_prefix": message[:200],
                    "task_id": task_id,
                },
                actor=f"三月·{source}",
            )
        except Exception as e:
            logger.debug("[三月·事件响铃] audit 写入失败（不影响推送）: {}", e)

        return True

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
