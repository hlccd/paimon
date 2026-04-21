from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import Message, TelegramObject
from loguru import logger

from paimon.state import state


class AuthMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        cfg = state.cfg
        if isinstance(event, Message) and cfg:
            user = event.from_user
            if cfg.owner_id and (not user or user.id != cfg.owner_id):
                logger.debug("[派蒙·TG频道] 拒绝未授权用户 {}", user.id if user else "unknown")
                await event.reply("你不在派蒙的授权列表中哦~")
                return None
        return await handler(event, data)
