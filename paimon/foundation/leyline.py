"""
地脉 (Leyline) — 全局事件总线

基于 asyncio.Queue 的进程内发布/订阅事件系统。
所有模块间的事件交互走地脉，保证消息有序、handler 异常隔离。

预定义 Topic 命名约定：
  march.ring          三月推送响铃 → 派蒙投递
  march.task_due      定时任务到期
  shade.authz_update  权限变更 → 派蒙更新本地缓存
  skill.loaded        新 skill 上线 → 派蒙刷新
  error.log           异常广播 → 日志设施
"""
from __future__ import annotations

import asyncio
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Callable, Coroutine

from loguru import logger

Handler = Callable[["Event"], Coroutine[Any, Any, None]]

_SENTINEL_TOPIC = "_leyline_stop"


@dataclass
class Event:
    topic: str
    payload: dict
    source: str = ""
    timestamp: float = field(default_factory=time.time)


def _handler_name(handler: Handler) -> str:
    return getattr(handler, "__qualname__", None) or repr(handler)


class Leyline:
    # REL-008 防内存爆炸：Queue 加 maxsize；满时丢最旧并 warning
    # 10000 在事件吞吐 50/s 时可缓冲 200s，handler 异常导致积压时给运维反应时间
    _MAX_QUEUE = 10000
    # handler 单次处理超时；超过即 cancel 防止阻塞主循环
    _HANDLER_TIMEOUT = 30.0

    def __init__(self):
        self._queue: asyncio.Queue[Event] = asyncio.Queue(maxsize=self._MAX_QUEUE)
        self._handlers: dict[str, list[Handler]] = defaultdict(list)
        self._running = False
        # 队列满 warning 节流：避免 handler 卡死时疯狂打日志
        self._last_overflow_warn_ts: float = 0.0

    def subscribe(self, topic: str, handler: Handler) -> None:
        if handler not in self._handlers[topic]:
            self._handlers[topic].append(handler)
            logger.debug("[地脉] 订阅 {} -> {}", topic, _handler_name(handler))

    def unsubscribe(self, topic: str, handler: Handler) -> None:
        handlers = self._handlers.get(topic)
        if handlers and handler in handlers:
            handlers.remove(handler)

    async def publish(self, topic: str, payload: dict, source: str = "") -> None:
        event = Event(topic=topic, payload=payload, source=source)
        try:
            self._queue.put_nowait(event)
        except asyncio.QueueFull:
            # REL-008 队列满：丢最旧 + warning（带节流，最多 10s 一次）
            try:
                dropped = self._queue.get_nowait()
                self._queue.task_done()
                self._queue.put_nowait(event)
            except (asyncio.QueueEmpty, asyncio.QueueFull):
                return  # 极端罕见，放弃本事件
            now = time.time()
            if now - self._last_overflow_warn_ts > 10:
                self._last_overflow_warn_ts = now
                logger.warning(
                    "[地脉] 队列满（maxsize={}），丢弃最旧事件 dropped_topic={} "
                    "new_topic={} source={}（handler 可能卡死，请排查）",
                    self._MAX_QUEUE, dropped.topic, topic, source,
                )

    async def start(self) -> None:
        self._running = True
        logger.info("[地脉] 事件总线已启动")
        try:
            while self._running:
                event = await self._queue.get()

                if event.topic == _SENTINEL_TOPIC:
                    break

                handlers = self._handlers.get(event.topic, [])
                if not handlers:
                    logger.trace("[地脉] 无订阅者: {}", event.topic)
                    continue

                for handler in list(handlers):
                    try:
                        # REL-005 handler 超时保护：阻塞型 handler 不会卡死整个总线
                        await asyncio.wait_for(handler(event), timeout=self._HANDLER_TIMEOUT)
                    except asyncio.TimeoutError:
                        logger.error(
                            "[地脉] handler 超时 ({}s) topic={} handler={}",
                            self._HANDLER_TIMEOUT, event.topic, _handler_name(handler),
                        )
                        if event.topic != "error.log":
                            try:
                                self._queue.put_nowait(Event(
                                    topic="error.log",
                                    payload={
                                        "origin_topic": event.topic,
                                        "handler": _handler_name(handler),
                                        "error": f"timeout >{self._HANDLER_TIMEOUT}s",
                                    },
                                    source="地脉",
                                ))
                            except asyncio.QueueFull:
                                pass
                    except Exception as e:
                        logger.error(
                            "[地脉] handler 异常 topic={} handler={}: {}",
                            event.topic, _handler_name(handler), e,
                        )
                        if event.topic != "error.log":
                            # 直接 put_nowait（不 await self.publish）避免再次进入
                            # 满队列丢最旧的逻辑造成日志风暴
                            try:
                                self._queue.put_nowait(Event(
                                    topic="error.log",
                                    payload={
                                        "origin_topic": event.topic,
                                        "handler": _handler_name(handler),
                                        "error": str(e),
                                    },
                                    source="地脉",
                                ))
                            except asyncio.QueueFull:
                                pass
        except asyncio.CancelledError:
            pass
        finally:
            self._running = False
            logger.info("[地脉] 事件总线已停止")

    async def stop(self) -> None:
        if not self._running:
            return
        self._running = False
        self._queue.put_nowait(Event(topic=_SENTINEL_TOPIC, payload={}))
