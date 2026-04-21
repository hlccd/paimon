from __future__ import annotations

from typing import TYPE_CHECKING

from aiogram import Router
from aiogram.types import Message, ReactionTypeEmoji
from loguru import logger

from paimon.channels.base import IncomingMessage
from paimon.channels.telegram.middleware import AuthMiddleware
from paimon.channels.telegram.reply import to_tg_chunks

if TYPE_CHECKING:
    from paimon.channels.telegram.channel import TelegramChannel


def build_router(channel: TelegramChannel) -> Router:
    router = Router()
    router.message.middleware(AuthMiddleware())

    def _wrap(message: Message) -> IncomingMessage:
        async def _reply(text: str) -> None:
            try:
                chunks = to_tg_chunks(text)
                for chunk_text, chunk_entities in chunks:
                    await message.answer(chunk_text, entities=chunk_entities)
                return
            except Exception as e:
                logger.warning("[派蒙·TG频道] 格式化回复失败: {}", e)

            try:
                if text and text.strip():
                    await message.answer(text)
            except Exception as e:
                logger.warning("[派蒙·TG频道] 回复失败: {}", e)

        return IncomingMessage(
            channel_name=channel.name,
            chat_id=str(message.chat.id),
            text=message.text or "",
            raw=message,
            _reply=_reply,
        )

    @router.message()
    async def on_message(message: Message):
        if not message.text:
            return
        msg = _wrap(message)
        logger.info("[派蒙·TG频道] 收到消息 chat_id={}", msg.chat_id)

        try:
            await message.react(reaction=[ReactionTypeEmoji(emoji="❤️")])
        except Exception:
            pass
        try:
            from paimon.core.chat import on_channel_message
            await on_channel_message(msg, channel)
        except Exception as e:
            logger.error("[派蒙·TG频道] 消息处理失败: {}", e)
        finally:
            try:
                await message.react(reaction=[])
            except Exception:
                pass

    return router
