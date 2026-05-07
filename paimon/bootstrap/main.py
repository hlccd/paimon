"""派蒙启动总流程 create_app：按顺序拉起世界树→model→archon→cron→authz→channel→leyline 订阅。

每个 phase 独立 try/except 失败不阻塞启动；最后返回所有已注册的 channels。
"""
from __future__ import annotations

from loguru import logger

from paimon.channels.base import Channel
from paimon.config import Config
from paimon.foundation.gnosis import Gnosis
from paimon.foundation.irminsul import Irminsul
from paimon.foundation.leyline import Leyline
from paimon.foundation.march import MarchService
from paimon.foundation.primogem import Primogem
from paimon.foundation.gnosis import make_provider_from_profile
from paimon.llm import Model
from paimon.session import SessionManager
from paimon.state import state

from ._handlers import (
    _on_llm_profile_updated,
    _on_llm_route_updated,
    _on_march_ring,
    _on_skill_loaded,
)
from ._llm import _make_provider, _seed_llm_profiles_if_empty
from ._phases import (
    _autoallow_loaded_skills_and_archons,
    _ensure_dividend_cron,
    _ensure_hygiene_cron,
    _ensure_mihoyo_collect_cron,
    _ensure_startup_subscriptions,
)


async def create_app(cfg: Config) -> list[Channel]:
    """启动主流程：基础组件 → archon 注册 → cron + 订阅 ensure → channel + leyline 订阅。"""
    state.cfg = cfg
    state.session_tasks.clear()
    state.session_task_locks.clear()

    cfg.paimon_home.mkdir(parents=True, exist_ok=True)

    # 世界树最早初始化（全系统唯一存储层）
    state.irminsul = Irminsul(cfg.paimon_home)
    await state.irminsul.initialize()

    # 首次启动从 .env 种 LLM Profile（M1：面板管理，不影响启动 provider 选择）
    await _seed_llm_profiles_if_empty(state.irminsul, cfg)

    # 会话管理器从世界树恢复
    state.session_mgr = await SessionManager.load(state.irminsul)

    # 地脉事件总线
    state.leyline = Leyline()

    # 三月调度服务
    state.march = MarchService(state.irminsul, state.leyline)

    # 原石持有世界树引用（服务层）
    state.primogem = Primogem(state.irminsul)

    gnosis = Gnosis(cfg)
    gnosis.attach_irminsul(state.irminsul)   # M2：让 gnosis 能按 profile_id 读世界树
    state.gnosis = gnosis

    # M3：优先从默认 profile 启动；profile 表空 / 默认缺 key 时回落 .env。
    # 启动后的 primary_provider 作为 Model._pick_provider 的最终 env 兜底——
    # 当 gnosis.get_default_provider 也取不到时（极端场景）仍有 provider 能用。
    default_profile = await state.irminsul.llm_profile_get_default()
    if default_profile and default_profile.api_key:
        primary_provider = make_provider_from_profile(
            default_profile, max_tokens=cfg.max_tokens,
        )
        primary_name = default_profile.name
        logger.info(
            "[派蒙·启动] 从默认 profile 启动 name={} model={}",
            default_profile.name, default_profile.model,
        )
    else:
        primary_provider = _make_provider(cfg, cfg.llm_provider)
        primary_name = cfg.llm_provider
        logger.info(
            "[派蒙·启动] 默认 profile 不可用，.env 回落 LLM_PROVIDER={}",
            cfg.llm_provider,
        )
    gnosis.register(primary_name, primary_provider)

    # deep pool 向后兼容（当前代码未真正使用，保留注册保持 gnosis.get_provider
    # fallback 行为；失败不阻塞启动）
    deep_name = cfg.llm_deep_provider or cfg.llm_provider
    if deep_name != primary_name:
        try:
            deep_provider = _make_provider(cfg, deep_name)
            gnosis.register(deep_name, deep_provider)
        except Exception as e:
            logger.warning(
                "[派蒙·启动] deep pool '{}' 注册失败（向后兼容路径）: {}",
                deep_name, e,
            )

    # M2：路由器加载（llm_routes 表；空表时全走默认 profile）
    from paimon.foundation.model_router import ModelRouter
    router = ModelRouter(state.irminsul)
    await router.load()
    state.model_router = router

    state.model = Model(primary_provider, gnosis, router=router)

    from pathlib import Path
    from paimon.tools.registry import ToolRegistry
    from paimon.skill_loader.registry import SkillRegistry

    project_root = Path(__file__).parent.parent.parent
    state.tool_registry = ToolRegistry.load(project_root / "tools")
    state.skill_registry = SkillRegistry(project_root / "skills")
    state.skill_registry.scan_and_load()
    # 冰神职责：把内存 registry 持久化到世界树 skill_declarations 表
    await state.skill_registry.sync_to_irminsul(state.irminsul)

    # 冰神 B-2：skill 目录热加载（docs/angels/angels.md §热加载）
    state.skill_hot_loader = None
    if cfg.skills_hot_reload:
        from paimon.skill_loader.watcher import SkillHotLoader
        state.skill_hot_loader = SkillHotLoader(
            state.skill_registry, state.irminsul, state.model,
        )
        if state.skill_hot_loader.start():
            logger.info("[冰神·启动] 热加载已开启（skills_hot_reload=True）")
        else:
            state.skill_hot_loader = None

    # 风神单例（供三月 cron 触发订阅采集；四影管线另走 archon registry 路径）
    from paimon.archons.venti import (
        VentiArchon,
        register_task_types as _venti_reg,
        register_subscription_types as _venti_sub_reg,
    )
    state.venti = VentiArchon()

    # 岩神单例（红利股追踪 cron 触发；同上）
    from paimon.archons.zhongli import ZhongliArchon
    from paimon.archons.zhongli.zhongli import register_task_types as _zhongli_reg
    state.zhongli = ZhongliArchon()

    # 水神·游戏单例（米哈游账号/签到/便笺/抽卡）
    from paimon.archons.furina_game import FurinaGameService
    state.furina_game = FurinaGameService(state.irminsul)

    # 方案 D：注册各神名下的周期任务类型到中央 task_types registry。
    # /tasks 面板可见 + bootstrap._on_march_ring 分派都走这套；
    # 未来新神加周期任务的唯一接入点。
    _venti_reg()
    _zhongli_reg()
    from paimon.archons.furina_game import register_task_types as _furina_game_reg
    _furina_game_reg()
    from paimon.core.memory_classifier import register_task_types as _hygiene_reg
    _hygiene_reg()

    # 订阅类型注册（venti.collect_subscription dispatch 时按 binding_kind 查表）
    # venti 注册 'manual'（用户手填）；其他 archon 各自实装自己的 binding_kind
    _venti_sub_reg()
    from paimon.archons.furina_game import (
        register_subscription_types as _furina_sub_reg,
    )
    _furina_sub_reg()  # 水神·游戏注册 'mihoyo_game'
    from paimon.archons.zhongli.zhongli import (
        register_subscription_types as _zhongli_sub_reg,
    )
    _zhongli_sub_reg()  # 岩神·关注股注册 'stock_watch'

    # 启动 ensure 阶段：业务订阅 + cron 任务（每个 phase 独立 try/except）
    await _ensure_startup_subscriptions()
    await _ensure_dividend_cron(cfg)
    await _ensure_mihoyo_collect_cron()
    await _ensure_hygiene_cron()

    # 授权体系：世界树灌缓存 + 决策器初始化
    from paimon.core.authz import AuthzCache, AuthzDecision
    state.authz_cache = AuthzCache()
    await state.authz_cache.load(state.irminsul)
    state.authz_decision = AuthzDecision(
        state.authz_cache, state.irminsul, state.skill_registry,
    )

    # 启动时自动放行 builtin skill + 7 个 archon
    await _autoallow_loaded_skills_and_archons()

    # 三月·自检服务（docs/foundation/march.md §自检体系）
    if cfg.selfcheck_enabled:
        from paimon.foundation.selfcheck import SelfCheckService
        state.selfcheck = SelfCheckService(
            cfg, state.irminsul, state.model, state.march,
        )
        # 启动时清 zombie running：上次进程被 kill / crash 时留下的"永远 running"记录
        # 新进程的内存态 _deep_busy=False，DB 对齐后一切干净
        try:
            zombies = await state.irminsul.selfcheck_sweep_zombie(actor="三月·自检")
            if zombies:
                logger.warning(
                    "[三月·自检] 启动清理 {} 条 zombie running → failed", zombies,
                )
        except Exception as e:
            logger.warning("[三月·自检] zombie 清扫失败（跳过）: {}", e)
        logger.info("[三月·自检] 服务已就绪（Quick + Deep）")

    channels: list[Channel] = []

    if cfg.webui_enabled:
        from paimon.channels.webui import WebUIChannel
        webui_channel = WebUIChannel(state)
        channels.append(webui_channel)

    if cfg.bot_token:
        from paimon.channels.telegram import TelegramChannel
        tg_channel = TelegramChannel(
            token=cfg.bot_token,
            owner_id=cfg.owner_id,
        )
        channels.append(tg_channel)

    if cfg.qq_appid and cfg.qq_secret:
        from paimon.channels.qq import QQChannel
        qq_channel = QQChannel(
            appid=cfg.qq_appid,
            secret=cfg.qq_secret,
            owner_ids=cfg.qq_owner_ids,
        )
        channels.append(qq_channel)

    state.channels = {ch.name: ch for ch in channels}

    # 派蒙订阅三月响铃 → 投递给用户
    state.leyline.subscribe("march.ring", _on_march_ring)

    # 权限缓存：新 skill 上线（冰神审过 → 四影通知）/ skill 被撤销时失效对应缓存
    state.leyline.subscribe("skill.loaded", _on_skill_loaded)
    # 热卸载 / orphan 场景：撤销后也失效 authz 缓存（避免 dangling 授权被消费）
    state.leyline.subscribe("skill.revoked", _on_skill_loaded)

    # M2：profile / route 热切换（面板保存后触发对应缓存失效）
    state.leyline.subscribe("llm.profile.updated", _on_llm_profile_updated)
    state.leyline.subscribe("llm.route.updated", _on_llm_route_updated)

    logger.info(
        "[派蒙·启动] 系统就绪 (模型={}, 频道={})",
        cfg.model,
        [ch.name for ch in channels],
    )
    return channels
