from __future__ import annotations

import time
from typing import TYPE_CHECKING

from loguru import logger

from paimon.channels.base import ChannelReply

if TYPE_CHECKING:
    from paimon.channels.qq.channel import QQChannel

QQ_MAX_MESSAGE_LENGTH = 2000
PASSIVE_REPLY_TIMEOUT = 290

# notice kind 的处理策略。
# 见 docs/interaction.md §3.4 渠道 degrade 表。
_NOTICE_KINDS_DROP = {"tool", "thinking"}  # 直接丢弃
_NOTICE_KINDS_SEND = {"ack", "milestone", "done_recap"}


def _chunk_text(text: str, max_len: int = QQ_MAX_MESSAGE_LENGTH) -> list[str]:
    if len(text) <= max_len:
        return [text] if text.strip() else []
    chunks: list[str] = []
    for i in range(0, len(text), max_len):
        chunk = text[i : i + max_len]
        if chunk.strip():
            chunks.append(chunk)
    return chunks


class QQChannelReply(ChannelReply):
    # QQ 是批次渠道：send 累加 buffer，flush 才发；notice 是一条独立消息直发。
    streaming = False

    def __init__(
        self,
        channel: "QQChannel",
        chat_id: str,
        msg_id: str,
        msg_type: str,
    ):
        self._channel = channel
        self._chat_id = chat_id
        self._msg_id = msg_id
        self._msg_type = msg_type
        self._buffer = ""
        # ack 暂存：等 prepare 过死执后首条 milestone 触发时才真实送出。
        # prepare 直接失败（死执拒/异常）时 ack 永远不发，省一条 seq。
        self._pending_ack: str | None = None

    async def send(self, text: str) -> None:
        if not text:
            return
        self._buffer += text

    async def flush(self) -> None:
        text = self._buffer.strip()
        self._buffer = ""
        if not text:
            return
        # flush 正文前把可能暂存的 ack 一起冲出（按顺序先 ack 后正文）
        await self._flush_pending_ack()
        await self._send_chunks(text)

    async def notice(self, text: str, *, kind: str = "milestone") -> None:
        """按 kind + 窗口 + seq 预算决定是否真发。

        - tool / thinking：直接丢（seq 不值当，架构决策见 docs/interaction.md §3.4）
        - ack：暂存不立即发，等首条 milestone 触发时才带出
        - 其他：过窗口检查 + 剩余 seq 检查后直发
        """
        if not text:
            return
        if kind in _NOTICE_KINDS_DROP:
            return
        if not self._channel.seq_window_open(self._chat_id):
            return

        if kind == "ack":
            self._pending_ack = text
            return

        # milestone / done_recap：先冲掉 pending ack，再发自己
        if kind not in _NOTICE_KINDS_SEND:
            # 未知 kind 保守当 milestone
            pass

        await self._flush_pending_ack()
        await self._send_chunks(text)

    async def _flush_pending_ack(self) -> None:
        if self._pending_ack is None:
            return
        text = self._pending_ack
        self._pending_ack = None
        if self._channel.seq_window_open(self._chat_id):
            await self._send_chunks(text)

    async def _send_chunks(self, text: str) -> None:
        """真·发消息。从 channel 级 ctx 动态取 msg_id + seq。

        关键：msg_id 不用构造时绑定的 `self._msg_id`，而是每次发消息时读 ctx
        里的 `last_msg_id`。这样 ask_user 挂起→用户发答复→新 msg_id 进入 ctx
        的场景下，协程恢复后的消息会正确回复到"用户答复"那条，seq 计数也是
        新 msg_id 下的独立序列，不和旧消息冲突。
        """
        ctx = self._channel._chat_contexts.get(self._chat_id)
        current_msg_id = ctx.get("last_msg_id") if ctx else self._msg_id
        passive = self._channel.seq_window_open(self._chat_id)
        chunks = _chunk_text(text)
        for chunk in chunks:
            seq = self._channel.take_seq(self._chat_id)
            try:
                await self._channel._send_message(
                    chat_id=self._chat_id,
                    text=chunk,
                    msg_type=self._msg_type,
                    msg_id=current_msg_id if passive else None,
                    msg_seq=seq,
                )
            except Exception as e:
                logger.warning("[派蒙·QQ频道] 发送失败: {}", e)
