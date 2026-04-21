from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from paimon.channels.base import Channel
    from paimon.session import Session
    from paimon.tools.registry import ToolRegistry


@dataclass
class ToolContext:
    registry: ToolRegistry
    channel: Channel | None
    chat_id: str
    session: Session | None = None


class BaseTool:
    name: str = ""
    description: str = ""
    parameters: dict = {}

    async def execute(self, ctx: ToolContext, **kwargs: Any) -> str:
        raise NotImplementedError
