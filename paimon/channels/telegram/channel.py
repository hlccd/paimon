from __future__ import annotations

from pathlib import Path

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.types import BotCommand, MessageEntity
from loguru import logger

from paimon.channels.base import Channel, ChannelReply, IncomingMessage
from paimon.channels.telegram.reply import (
    TELEGRAM_MAX_MESSAGE_UTF16,
    TelegramChannelReply,
    to_tg_chunks,
)


class TelegramChannel(Channel):
    name = "telegram"

    def __init__(self, token: str, owner_id: int):
        self._token = token
        self._owner_id = owner_id
        self._bot: Bot | None = None
        self._dp: Dispatcher | None = None

    async def send_text(self, chat_id: str, text: str) -> None:
        if not self._bot:
            return
        if not text or not text.strip():
            return
        try:
            chunks = to_tg_chunks(text)
            if chunks:
                for chunk_text, chunk_entities in chunks:
                    await self.send_text_entities(chat_id, chunk_text, chunk_entities)
                return
        except Exception as e:
            logger.warning("[派蒙·TG频道] 格式化发送失败: {}", e)

        try:
            for i in range(0, len(text), TELEGRAM_MAX_MESSAGE_UTF16):
                chunk_text = text[i : i + TELEGRAM_MAX_MESSAGE_UTF16]
                if chunk_text.strip():
                    await self._bot.send_message(chat_id=int(chat_id), text=chunk_text)
        except Exception as e:
            logger.warning("[派蒙·TG频道] 发送文本失败: {}", e)

    async def send_text_entities(
        self,
        chat_id: str,
        text: str,
        entities: list[MessageEntity] | None = None,
    ) -> None:
        if not self._bot:
            return
        try:
            await self._bot.send_message(chat_id=int(chat_id), text=text, entities=entities)
        except Exception as e:
            logger.warning("[派蒙·TG频道] 发送entities消息失败: {}", e)

    async def send_file(self, chat_id: str, path: Path, caption: str = "") -> None:
        if not self._bot:
            return
        from aiogram.types import FSInputFile

        input_file = FSInputFile(path)
        ext = path.suffix.lower()
        image_exts = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"}
        try:
            if ext in image_exts:
                await self._bot.send_photo(
                    chat_id=int(chat_id), photo=input_file, caption=caption or None
                )
            else:
                await self._bot.send_document(
                    chat_id=int(chat_id), document=input_file, caption=caption or None
                )
        except Exception as e:
            logger.warning("[派蒙·TG频道] 发送文件失败: {}", e)

    async def make_reply(self, msg: IncomingMessage) -> ChannelReply:
        return TelegramChannelReply(self, msg.chat_id)

    async def start(self) -> None:
        from paimon.channels.telegram.handlers import build_router

        self._bot = Bot(token=self._token, default=DefaultBotProperties())
        self._dp = Dispatcher()

        router = build_router(self)
        self._dp.include_router(router)

        async def on_startup(bot: Bot):
            await bot.set_my_commands(
                [
                    BotCommand(command="new", description="创建新会话"),
                    BotCommand(command="sessions", description="查看所有会话"),
                    BotCommand(command="stop", description="停止当前回复"),
                    BotCommand(command="clear", description="清空当前会话"),
                ]
            )
            logger.info("[派蒙·TG频道] 已就绪")

        self._dp.startup.register(on_startup)

        logger.info("[派蒙·TG频道] 正在启动 (token={}...)", self._token[:8])
        await self._dp.start_polling(self._bot)

    async def stop(self) -> None:
        if self._dp:
            await self._dp.stop_polling()
