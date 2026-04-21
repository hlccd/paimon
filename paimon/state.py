from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from paimon.channels.base import Channel
    from paimon.config import Config
    from paimon.llm import Model
    from paimon.session import SessionManager


@dataclass
class RuntimeState:
    cfg: Config | None = None
    session_mgr: SessionManager | None = None
    model: Model | None = None
    channels: dict[str, "Channel"] = field(default_factory=dict)
    session_tasks: dict[str, asyncio.Task] = field(default_factory=dict)
    session_task_locks: dict[str, asyncio.Lock] = field(default_factory=dict)


state = RuntimeState()
