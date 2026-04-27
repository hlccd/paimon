from __future__ import annotations

import asyncio
import re
import time
from pathlib import Path
from typing import Any

import botpy
from loguru import logger

from paimon.channels.base import Channel, ChannelReply, IncomingMessage
from paimon.channels.qq.reply import QQ_CHUNK_LIMIT, QQChannelReply, _chunk_text


# 含 markdown 语法的检测——保守路线：宁愿漏检（走纯文本无害），不要误判（普通文本走 md
# 在不支持的客户端上渲染会很怪）。
# 命中以下任一即视为 markdown：
#   - ``` 代码块（最强信号）
#   - 行首 # 标题（# / ## / ###...）
#   - 行首 - / * / 1. 列表项
#   - [text](http://...) 链接
#   - **bold** 成对加粗
#   - 表格（|...| + 下一行 |---|）
_MD_PATTERNS = [
    re.compile(r"```"),
    re.compile(r"^#{1,6}\s+\S", re.MULTILINE),
    re.compile(r"^[\-\*]\s+\S", re.MULTILINE),
    re.compile(r"^\d+\.\s+\S", re.MULTILINE),
    re.compile(r"\[[^\]\n]+\]\(https?://[^)\s]+\)"),
    re.compile(r"\*\*[^*\n]+\*\*"),
    re.compile(r"^\|.+\|\s*\n^\|\s*-+", re.MULTILINE),
]


def _looks_like_markdown(text: str) -> bool:
    if not text:
        return False
    for p in _MD_PATTERNS:
        if p.search(text):
            return True
    return False


class QQChannel(Channel):
    name = "qq"
    # QQ 开放平台限制：主动推送必须依附最近入站消息上下文，无法做真正的定时推送
    # docs 规则：QQ 上不推送，数据仍存，用户需主动查询
    supports_push = False

    def __init__(self, appid: str, secret: str, owner_ids: str = ""):
        self._appid = appid
        self._secret = secret
        self._owner_ids = owner_ids
        self._client: botpy.Client | None = None
        self._task: asyncio.Task | None = None
        self._chat_contexts: dict[str, dict[str, Any]] = {}
        # markdown 进程级降级标志：API 调用失败一次（通常是无权限）后永久关闭 md 尝试，
        # 避免每条 md 消息都先试再 fallback，浪费 API 配额且增加延迟。
        # 重启 paimon 进程会重置（让用户在开通权限后无需改代码就生效）。
        self._md_disabled: bool = False

    def register_chat_context(self, chat_id: str, msg_type: str, msg_id: str):
        self._chat_contexts[chat_id] = {
            "msg_type": msg_type,
            "last_msg_id": msg_id,
            "msg_seq": 1,
            "created_at": time.time(),   # passive window 起点 —— 多 reply 实例共享
        }

    def _get_context(self, chat_id: str) -> dict[str, Any] | None:
        return self._chat_contexts.get(chat_id)

    def take_seq(self, chat_id: str) -> int:
        """返回当前可用 msg_seq，并把 ctx 里的 seq 自增。

        所有发往 QQ 的消息（send_text / reply.send 后 flush / reply.notice）
        都应经此取 seq，避免多个 QQChannelReply 实例各自从 1 开始冲突。
        """
        ctx = self._chat_contexts.get(chat_id)
        if ctx is None:
            return 1
        seq = int(ctx.get("msg_seq", 1) or 1)
        ctx["msg_seq"] = seq + 1
        return seq

    def set_pending_ack(self, chat_id: str, text: str) -> None:
        """ack 暂存到 channel 级 ctx（按 chat_id），跨 reply 实例共享。

        天使路径下 core/chat.py 在 ack 后又 make_reply 起新实例进 run_session_chat，
        若 _pending_ack 是实例级会跟着 reply 一起丢；提升到 ctx 后任何 reply
        实例 flush 时都能取到。
        """
        ctx = self._chat_contexts.get(chat_id)
        if ctx is not None:
            ctx["pending_ack"] = text

    def pop_pending_ack(self, chat_id: str) -> str | None:
        ctx = self._chat_contexts.get(chat_id)
        if ctx is None:
            return None
        return ctx.pop("pending_ack", None)

    def seq_window_open(self, chat_id: str, margin: float = 5.0) -> bool:
        """被动回复窗口是否还开着（留 5s 余量以防卡在边界）。"""
        ctx = self._chat_contexts.get(chat_id)
        if ctx is None:
            return False
        created = float(ctx.get("created_at", 0.0))
        return (time.time() - created) < (290.0 - margin)

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

        ctx = self._get_context(chat_id)
        if msg_type is None:
            if ctx:
                msg_type = ctx["msg_type"]
            else:
                logger.warning("[派蒙·QQ频道] 未找到聊天上下文 chat_id={}", chat_id)
                return
        # msg_id 总从 ctx fallback（不管 msg_type 是否传入）——
        # 之前只在 msg_type is None 时 fallback，send_text 显式传 msg_type 导致
        # msg_id 永远是 None 被腾讯 API 拒绝（被动回复必须有 msg_id）。
        if msg_id is None and ctx:
            msg_id = ctx.get("last_msg_id")

        # markdown 路径：默认开启，仅含 md 语法的消息走 msg_type=2；
        # API 调用失败一次（如 bot 无 md 权限）→ _md_disabled 永久关闭，后续走纯文本。
        use_md = (not self._md_disabled) and _looks_like_markdown(text)

        if use_md:
            try:
                if msg_type == "group":
                    await api.post_group_message(
                        group_openid=chat_id,
                        msg_type=2,
                        markdown={"content": text},
                        msg_id=msg_id,
                        msg_seq=msg_seq,
                    )
                    return
                elif msg_type == "c2c":
                    await api.post_c2c_message(
                        openid=chat_id,
                        msg_type=2,
                        markdown={"content": text},
                        msg_id=msg_id,
                        msg_seq=msg_seq,
                    )
                    return
                else:
                    logger.warning("[派蒙·QQ频道] 未知消息类型 {}", msg_type)
                    return
            except Exception as e:
                # 通常是 bot 无 markdown 权限。记一次 WARNING + 进程级降级 +
                # fallback 到纯文本（避免本条消息丢失）。
                self._md_disabled = True
                logger.warning(
                    "[派蒙·QQ频道] markdown 发送失败，本进程降级为纯文本（重启后会再次尝试 md）: {}",
                    e,
                )
                # 继续走下面的纯文本路径

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

        chunks = _chunk_text(text, QQ_CHUNK_LIMIT)
        for chunk in chunks:
            seq = self.take_seq(chat_id)
            await self._send_message(
                chat_id=chat_id,
                text=chunk,
                msg_type=msg_type,
                msg_seq=seq,
            )

    async def send_file(self, chat_id: str, path: Path, caption: str = "") -> None:
        if caption:
            await self.send_text(chat_id, caption)
        logger.warning("[派蒙·QQ频道] 暂不支持发送文件，已跳过 {}", path.name)

    async def make_reply(self, msg: IncomingMessage) -> ChannelReply:
        ctx = self._get_context(msg.chat_id)
        msg_type = ctx["msg_type"] if ctx else "group"
        msg_id = ctx.get("last_msg_id", "") if ctx else ""
        return QQChannelReply(self, msg.chat_id, msg_id, msg_type)

    async def ask_user(
        self, chat_id: str, prompt: str, *, timeout: float = 30.0,
    ) -> str:
        """QQ 授权询问：发询问消息 + 挂 Future 等用户下条入站消息作答。

        和 WebUI 的 ask_user 共用 state.pending_asks 字典——用户的下条消息
        会被 core.chat.on_channel_message 最前面的 pending 消化逻辑截获，
        直接 set_result 到这里的 Future，不走正常 chat 流程。

        超时抛 asyncio.TimeoutError；并发重入抛 NotImplementedError（由
        pipeline._batch_authorize 兜底，降级为保守拒绝）。
        """
        from paimon.state import state as _state

        channel_key = f"{self.name}:{chat_id}"
        if channel_key in _state.pending_asks:
            raise NotImplementedError("已有挂起的权限询问，拒绝并发")

        # 先挂 Future 再发询问消息 —— 避免 race：
        # 如果先 send_text 再挂 Future，用户秒回的答复消息到 on_channel_message 时
        # pending_asks 还没 Future，答复会走普通 intent 流程而不是 set_result。
        loop = asyncio.get_running_loop()
        fut: asyncio.Future[str] = loop.create_future()
        _state.pending_asks[channel_key] = fut
        try:
            try:
                await self.send_text(
                    chat_id,
                    "🛡️ 权限询问\n\n" + prompt +
                    "\n\n请回复「同意 / 放行」继续，回复「拒绝 / 算了」终止。",
                )
            except Exception as e:
                logger.warning("[派蒙·QQ频道·ask_user] 发询问消息失败: {}", e)
                # 发送失败时直接抛 NotImplementedError 让 pipeline 走保守拒绝路径，
                # 免得用户看不到询问还在那傻等 60s 超时
                raise NotImplementedError(f"询问消息发送失败: {e}") from e
            return await asyncio.wait_for(fut, timeout=timeout)
        finally:
            _state.pending_asks.pop(channel_key, None)

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
