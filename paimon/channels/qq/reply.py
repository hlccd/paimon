from __future__ import annotations

import time
from typing import TYPE_CHECKING

from loguru import logger

from paimon.channels.base import ChannelReply

if TYPE_CHECKING:
    from paimon.channels.qq.channel import QQChannel

QQ_MAX_MESSAGE_LENGTH = 2000
PASSIVE_REPLY_TIMEOUT = 290


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
    def __init__(
        self,
        channel: QQChannel,
        chat_id: str,
        msg_id: str,
        msg_type: str,
    ):
        self._channel = channel
        self._chat_id = chat_id
        self._msg_id = msg_id
        self._msg_type = msg_type
        self._msg_seq = 1
        self._created_at = time.time()
        self._buffer = ""

    async def send(self, text: str) -> None:
        if not text:
            return
        self._buffer += text

    async def flush(self) -> None:
        text = self._buffer.strip()
        self._buffer = ""
        if not text:
            return
        passive = (time.time() - self._created_at) < PASSIVE_REPLY_TIMEOUT
        chunks = _chunk_text(text)
        for chunk in chunks:
            try:
                await self._channel._send_message(
                    chat_id=self._chat_id,
                    text=chunk,
                    msg_type=self._msg_type,
                    msg_id=self._msg_id if passive else None,
                    msg_seq=self._msg_seq,
                )
            except Exception as e:
                logger.warning("[派蒙·QQ频道] 回复发送失败: {}", e)
            self._msg_seq += 1
