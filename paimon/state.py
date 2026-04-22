from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from paimon.angels.registry import SkillRegistry
    from paimon.channels.base import Channel
    from paimon.channels.webui.push_hub import PushHub
    from paimon.config import Config
    from paimon.core.authz import AuthzCache, AuthzDecision
    from paimon.foundation.gnosis import Gnosis
    from paimon.foundation.irminsul import Irminsul
    from paimon.foundation.leyline import Leyline
    from paimon.foundation.march import MarchService
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
    march: MarchService | None = None
    primogem: Primogem | None = None
    tool_registry: ToolRegistry | None = None
    skill_registry: SkillRegistry | None = None
    channels: dict[str, "Channel"] = field(default_factory=dict)
    session_tasks: dict[str, asyncio.Task] = field(default_factory=dict)
    session_task_locks: dict[str, asyncio.Lock] = field(default_factory=dict)
    # 授权体系
    authz_cache: AuthzCache | None = None
    authz_decision: AuthzDecision | None = None
    # 挂起中的权限询问 future：channel_key -> Future[str]
    pending_asks: dict[str, asyncio.Future] = field(default_factory=dict)
    # WebUI 推送扇出器（长连接 SSE 的消息队列管理）
    push_hub: PushHub | None = None


state = RuntimeState()
