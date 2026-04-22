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
    def __init__(self):
        self._queue: asyncio.Queue[Event] = asyncio.Queue()
        self._handlers: dict[str, list[Handler]] = defaultdict(list)
        self._running = False

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
        self._queue.put_nowait(event)

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
                        await handler(event)
                    except Exception as e:
                        logger.error(
                            "[地脉] handler 异常 topic={} handler={}: {}",
                            event.topic, _handler_name(handler), e,
                        )
                        if event.topic != "error.log":
                            await self.publish(
                                "error.log",
                                {
                                    "origin_topic": event.topic,
                                    "handler": _handler_name(handler),
                                    "error": str(e),
                                },
                                source="地脉",
                            )
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
