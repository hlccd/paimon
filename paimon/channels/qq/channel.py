from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import botpy
from loguru import logger

from paimon.channels.base import Channel, ChannelReply, IncomingMessage
from paimon.channels.qq.reply import QQ_MAX_MESSAGE_LENGTH, QQChannelReply, _chunk_text


class QQChannel(Channel):
    name = "qq"

    def __init__(self, appid: str, secret: str, owner_ids: str = ""):
        self._appid = appid
        self._secret = secret
        self._owner_ids = owner_ids
        self._client: botpy.Client | None = None
        self._task: asyncio.Task | None = None
        self._chat_contexts: dict[str, dict[str, Any]] = {}

    def register_chat_context(self, chat_id: str, msg_type: str, msg_id: str):
        self._chat_contexts[chat_id] = {
            "msg_type": msg_type,
            "last_msg_id": msg_id,
            "msg_seq": 1,
        }

    def _get_context(self, chat_id: str) -> dict[str, Any] | None:
        return self._chat_contexts.get(chat_id)

    async def _send_message(
        self,
        chat_id: str,
        text: str,
        msg_type: str | None = None,
        msg_id: str | None = None,
        msg_seq: int = 1,
    ) -> None:
        if not self._client:
            return
        api = self._client.api

        if msg_type is None:
            ctx = self._get_context(chat_id)
            if ctx:
                msg_type = ctx["msg_type"]
                if msg_id is None:
                    msg_id = ctx.get("last_msg_id")
            else:
                logger.warning("[派蒙·QQ频道] 未找到聊天上下文 chat_id={}", chat_id)
                return

        try:
            if msg_type == "group":
                await api.post_group_message(
                    group_openid=chat_id,
                    msg_type=0,
                    content=text,
                    msg_id=msg_id,
                    msg_seq=msg_seq,
                )
            elif msg_type == "c2c":
                await api.post_c2c_message(
                    openid=chat_id,
                    msg_type=0,
                    content=text,
                    msg_id=msg_id,
                    msg_seq=msg_seq,
                )
            else:
                logger.warning("[派蒙·QQ频道] 未知消息类型 {}", msg_type)
        except Exception as e:
            logger.warning("[派蒙·QQ频道] 发送消息失败: {}", e)

    async def send_text(self, chat_id: str, text: str) -> None:
        if not text or not text.strip():
            return
        ctx = self._get_context(chat_id)
        msg_type = ctx["msg_type"] if ctx else None
        msg_seq = ctx.get("msg_seq", 1) if ctx else 1

        chunks = _chunk_text(text, QQ_MAX_MESSAGE_LENGTH)
        for chunk in chunks:
            await self._send_message(
                chat_id=chat_id,
                text=chunk,
                msg_type=msg_type,
                msg_seq=msg_seq,
            )
            msg_seq += 1

        if ctx:
            ctx["msg_seq"] = msg_seq

    async def send_file(self, chat_id: str, path: Path, caption: str = "") -> None:
        if caption:
            await self.send_text(chat_id, caption)
        logger.warning("[派蒙·QQ频道] 暂不支持发送文件，已跳过 {}", path.name)

    async def make_reply(self, msg: IncomingMessage) -> ChannelReply:
        ctx = self._get_context(msg.chat_id)
        msg_type = ctx["msg_type"] if ctx else "group"
        msg_id = ctx.get("last_msg_id", "") if ctx else ""
        return QQChannelReply(self, msg.chat_id, msg_id, msg_type)

    async def start(self) -> None:
        from paimon.channels.qq.handlers import PaimonQQClient

        intents = botpy.Intents(
            public_guild_messages=False,
            public_messages=True,
            direct_message=True,
        )

        self._client = PaimonQQClient(
            channel=self,
            intents=intents,
            bot_log=None,
        )

        logger.info("[派蒙·QQ频道] 正在启动 (appid={}...)", self._appid[:6])
        self._task = asyncio.create_task(
            self._client.start(appid=self._appid, secret=self._secret)
        )
        logger.info("[派蒙·QQ频道] 已就绪")

    async def stop(self) -> None:
        if self._client:
            await self._client.close()
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
