from __future__ import annotations

from typing import TYPE_CHECKING

import telegramify_markdown
from aiogram.types import MessageEntity
from loguru import logger

from paimon.channels.base import ChannelReply

if TYPE_CHECKING:
    from paimon.channels.telegram.channel import TelegramChannel


TELEGRAM_MAX_MESSAGE_UTF16 = 4096


def _to_aiogram_entities(
    entities: list[telegramify_markdown.MessageEntity],
) -> list[MessageEntity]:
    return [MessageEntity(**entity.to_dict()) for entity in entities]


def to_tg_chunks(text: str) -> list[tuple[str, list[MessageEntity]]]:
    plain_text, entities = telegramify_markdown.convert(text)
    chunks = telegramify_markdown.split_entities(
        plain_text,
        entities,
        TELEGRAM_MAX_MESSAGE_UTF16,
    )

    results: list[tuple[str, list[MessageEntity]]] = []
    for chunk_text, chunk_entities in chunks:
        if chunk_text and chunk_text.strip():
            results.append((chunk_text, _to_aiogram_entities(chunk_entities)))
    return results


class TelegramChannelReply(ChannelReply):
    def __init__(self, channel: TelegramChannel, chat_id: str):
        self._channel = channel
        self._chat_id = chat_id

    async def send(self, text: str) -> None:
        if not text or not text.strip():
            return
        try:
            chunks = to_tg_chunks(text)
            for chunk_text, chunk_entities in chunks:
                await self._channel.send_text_entities(
                    self._chat_id,
                    chunk_text,
                    chunk_entities,
                )
            return
        except Exception as e:
            logger.warning("[派蒙·TG频道] 回复发送失败: {}", e)

        try:
            if text and text.strip():
                await self._channel.send_text(self._chat_id, text)
        except Exception as e:
            logger.warning("[派蒙·TG频道] 回复降级发送也失败: {}", e)
