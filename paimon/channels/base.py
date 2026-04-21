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
    @abstractmethod
    async def send(self, text: str) -> None: ...

    async def flush(self) -> None:
        pass


class Channel(ABC):
    name: str

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
