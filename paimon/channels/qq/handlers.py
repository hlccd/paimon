from __future__ import annotations

from typing import TYPE_CHECKING

import botpy
from loguru import logger

from paimon.channels.base import IncomingMessage
from paimon.channels.qq.middleware import is_authorized

if TYPE_CHECKING:
    from paimon.channels.qq.channel import QQChannel


def _clean_content(content: str | None) -> str:
    if not content:
        return ""
    return content.strip()


def _build_wrap(
    channel: QQChannel,
    message,
    chat_id: str,
    msg_type: str,
) -> IncomingMessage:
    text = _clean_content(message.content)
    msg_id = str(message.id)

    channel.register_chat_context(chat_id, msg_type, msg_id)

    async def _reply(reply_text: str) -> None:
        from paimon.channels.qq.reply import QQChannelReply

        r = QQChannelReply(channel, chat_id, msg_id, msg_type)
        await r.send(reply_text)
        await r.flush()

    return IncomingMessage(
        channel_name=channel.name,
        chat_id=chat_id,
        text=text,
        raw=message,
        _reply=_reply,
    )


class PaimonQQClient(botpy.Client):
    def __init__(self, channel: QQChannel, **kwargs):
        super().__init__(**kwargs)
        self._channel = channel

    async def on_group_at_message_create(self, message):
        chat_id = str(message.group_openid)
        await self._handle_message(message, chat_id, "group")

    async def on_c2c_message_create(self, message):
        author = getattr(message, "author", None)
        chat_id = str(getattr(author, "user_openid", "")) if author else ""
        if not chat_id:
            return
        await self._handle_message(message, chat_id, "c2c")

    async def _handle_message(self, message, chat_id: str, msg_type: str):
        if not is_authorized(message):
            return

        msg = _build_wrap(self._channel, message, chat_id, msg_type)
        text = msg.text
        if not text:
            return

        logger.info("[派蒙·QQ频道] 收到{}消息 chat_id={}", msg_type, chat_id[:8])

        try:
            from paimon.core.chat import on_channel_message
            await on_channel_message(msg, self._channel)
        except Exception as e:
            logger.error("[派蒙·QQ频道] 消息处理失败: {}", e)
