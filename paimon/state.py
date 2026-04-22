from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from paimon.angels.registry import SkillRegistry
    from paimon.channels.base import Channel
    from paimon.config import Config
    from paimon.foundation.gnosis import Gnosis
    from paimon.foundation.irminsul import Irminsul
    from paimon.foundation.leyline import Leyline
    from paimon.foundation.primogem import Primogem
    from paimon.llm import Model
    from paimon.session import SessionManager
    from paimon.tools.registry import ToolRegistry


@dataclass
class RuntimeState:
    cfg: Config | None = None
    irminsul: Irminsul | None = None
    session_mgr: SessionManager | None = None
    model: Model | None = None
    gnosis: Gnosis | None = None
    leyline: Leyline | None = None
    primogem: Primogem | None = None
    tool_registry: ToolRegistry | None = None
    skill_registry: SkillRegistry | None = None
    channels: dict[str, "Channel"] = field(default_factory=dict)
    session_tasks: dict[str, asyncio.Task] = field(default_factory=dict)
    session_task_locks: dict[str, asyncio.Lock] = field(default_factory=dict)


state = RuntimeState()
