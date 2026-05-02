"""WebUI SSE reply 包装 — 主 channel.py 抽离的独立 module。"""
from __future__ import annotations

from loguru import logger

from paimon.channels.base import ChannelReply


class WebUIChannelReply(ChannelReply):
    streaming = True

    def __init__(self, reply_callback):
        self._reply = reply_callback

    async def send(self, text: str) -> None:
        if self._reply:
            await self._reply(text)

    async def notice(self, text: str, *, kind: str = "milestone") -> None:
        """推一条中间状态 SSE 事件（前端渲染为浅灰小字）。

        连接已关（SSE 断 / bg 任务晚于 SSE 生命周期）时静默丢弃——
        这正是 docs/interaction.md §1.1 说的 "送不了就丢" 的 degrade 语义。
        """
        if not self._reply or not text:
            return
        try:
            await self._reply(text, msg_type="notice", kind=kind)
        except (ConnectionResetError, ConnectionError):
            # SSE 已关（常见于 execute 后台阶段），按设计静默
            pass
        except TypeError:
            # reply 闭包不支持 kind（旧测试/mock 兜底），忽略
            pass
        except Exception as e:
            logger.debug("[派蒙·WebUI·notice] 发送失败 kind={}: {}", kind, e)
