from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from paimon.angels.registry import SkillRegistry
    from paimon.angels.watcher import SkillHotLoader
    from paimon.archons.venti import VentiArchon
    from paimon.archons.zhongli import ZhongliArchon
    from paimon.channels.base import Channel
    from paimon.channels.webui.push_hub import PushHub
    from paimon.config import Config
    from paimon.core.authz import AuthzCache, AuthzDecision
    from paimon.foundation.gnosis import Gnosis
    from paimon.foundation.irminsul import Irminsul
    from paimon.foundation.leyline import Leyline
    from paimon.foundation.march import MarchService
    from paimon.foundation.model_router import ModelRouter
    from paimon.foundation.primogem import Primogem
    from paimon.foundation.selfcheck import SelfCheckService
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
    # M2：LLM 路由器（按 (component, purpose) 选 profile）
    model_router: "ModelRouter | None" = None
    leyline: Leyline | None = None
    march: MarchService | None = None
    primogem: Primogem | None = None
    tool_registry: ToolRegistry | None = None
    skill_registry: SkillRegistry | None = None
    skill_hot_loader: "SkillHotLoader | None" = None
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
    # 风神单例（订阅采集入口；bootstrap 初始化）
    venti: "VentiArchon | None" = None
    # 岩神单例（红利股采集入口；bootstrap 初始化）
    zhongli: "ZhongliArchon | None" = None
    # 三月·自检服务（Quick 探针 + Deep 调度）
    selfcheck: "SelfCheckService | None" = None
    # /task-list 编号缓存：channel_key -> (task_ids, expires_at)
    # docs/interaction.md §四：列表后短暂有效（TTL 10 分钟），重新 list 自动重编号
    task_list_index: dict[str, tuple[list[str], float]] = field(default_factory=dict)
    # 后台未跟踪的 fire-and-forget task 防 GC（如 WebUI 断开后的 finalize_after_execute）。
    # Python asyncio 只对事件循环根任务保强引用；create_task 返回的任务若无外部引用，
    # 可能被提前 GC 并被日志静默 cancel。这里挂全局 set + task.add_done_callback(discard)。
    pending_bg_tasks: set[asyncio.Task] = field(default_factory=set)


state = RuntimeState()
