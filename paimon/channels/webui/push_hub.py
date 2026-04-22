"""WebUI 推送扇出中心 —— 服务层（无持久化，进程内）。

按 docs/aimon.md §2.6：三月 → 派蒙 → channel.send_text → PushHub → SSE → 前端
- 同一 chat_id 支持多标签页（fan-out 到每个 queue）
- 无监听者时 publish 返回 0，调用方决定是否降级为日志
- 派蒙挂掉时的积压由三月承担（本 Hub 不负责离线重放）
"""
from __future__ import annotations

import asyncio

from loguru import logger


class PushHub:
    def __init__(self) -> None:
        self._queues: dict[str, list[asyncio.Queue]] = {}

    async def register(self, chat_id: str) -> asyncio.Queue:
        """新 SSE 客户端接入时调用，返回独占队列。"""
        q: asyncio.Queue = asyncio.Queue(maxsize=256)
        self._queues.setdefault(chat_id, []).append(q)
        logger.debug(
            "[派蒙·推送] 监听者接入 chat_id={} 当前数={}",
            chat_id, len(self._queues[chat_id]),
        )
        return q

    async def unregister(self, chat_id: str, queue: asyncio.Queue) -> None:
        """SSE 客户端断开时调用；空列表自动清理。"""
        queues = self._queues.get(chat_id, [])
        if queue in queues:
            queues.remove(queue)
        if not queues and chat_id in self._queues:
            del self._queues[chat_id]
        logger.debug(
            "[派蒙·推送] 监听者断开 chat_id={} 余={}",
            chat_id, self.listener_count(chat_id),
        )

    async def publish(self, chat_id: str, payload: dict) -> int:
        """投递到所有监听 chat_id 的 queue，返回投递数；0 表示无监听者。

        队列满时丢最早一条（保证后到的重要消息不卡死）。
        """
        queues = list(self._queues.get(chat_id, []))
        if not queues:
            return 0

        delivered = 0
        for q in queues:
            if q.full():
                try:
                    q.get_nowait()  # 丢最早
                except asyncio.QueueEmpty:
                    pass
            try:
                q.put_nowait(payload)
                delivered += 1
            except Exception as e:
                logger.warning("[派蒙·推送] 队列投递异常: {}", e)
        return delivered

    def listener_count(self, chat_id: str) -> int:
        return len(self._queues.get(chat_id, []))
