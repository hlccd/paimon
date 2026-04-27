from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Awaitable, Callable


@dataclass
class IncomingMessage:
    channel_name: str
    chat_id: str
    text: str
    raw: Any = None
    _reply: Callable[[str], Awaitable[None]] | None = field(default=None, repr=False)

    @property
    def channel_key(self) -> str:
        return f"{self.channel_name}:{self.chat_id}"

    async def reply(self, text: str) -> None:
        if self._reply:
            await self._reply(text)


class ChannelReply(ABC):
    # 是否是"逐 chunk 即时送达"的流式渠道。
    # WebUI SSE=True（每 chunk 立刻推）；QQ / TG=False（累加到 buffer，flush 才发）。
    # 业务层不用这个判断，只给想优化节奏的地方（比如 watchdog 只在流式渠道开）。
    streaming: bool = False

    @abstractmethod
    async def send(self, text: str) -> None: ...

    async def notice(self, text: str, *, kind: str = "milestone") -> None:
        """中间状态提示（非正文）。

        kind 取值：ack / milestone / tool / thinking / done_recap。
        语义见 docs/interaction.md §1.2。

        默认 no-op——渠道按能力各自实现（丢弃 / 立即发 / 节流 / 延迟等）。
        调用方只负责打标签，不关心渠道怎么处理。
        """

    async def flush(self) -> None:
        pass


class Channel(ABC):
    name: str
    # 是否支持由派蒙主动推送（定时任务、事件响铃等）
    # docs/aimon.md §2.6：派蒙是推送出口，但具体频道是否支持由频道自己决定
    # WebUI / Telegram 默认 True；QQ 技术上不允许主动推送（必须依附入站消息）
    supports_push: bool = True

    @abstractmethod
    async def send_text(self, chat_id: str, text: str) -> None: ...

    @abstractmethod
    async def send_file(self, chat_id: str, path: Path, caption: str = "") -> None: ...

    @abstractmethod
    async def make_reply(self, msg: IncomingMessage) -> ChannelReply: ...

    @abstractmethod
    async def start(self) -> None: ...

    @abstractmethod
    async def stop(self) -> None: ...

    async def ask_user(self, chat_id: str, prompt: str, *, timeout: float = 30.0) -> str:
        """向用户询问并等待纯文本答复。

        默认实现抛 NotImplementedError —— 表示该频道不支持交互式询问；
        调用方（如授权决策）应捕获并降级（通常保守拒绝）。
        超时抛 asyncio.TimeoutError。
        """
        raise NotImplementedError(f"频道 {getattr(self, 'name', '?')} 未实现 ask_user")
