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
from paimon.foundation.irminsul.llm_profile import LLMProfile
from paimon.llm import Model
from paimon.llm.base import Provider
from paimon.session import SessionManager
from paimon.state import state


def _env_to_profile(cfg: Config, name: str) -> LLMProfile:
    """把 .env 里名叫 name 的 provider 配置转成临时 LLMProfile 对象（不落库）。

    seed / .env 回落启动都复用这个 helper，保证单一来源；真正构造 Provider
    统一交给 `make_provider_from_profile`，避免两套 SDK 构造代码（M3 DRY）。
    """
    if name == "claude-xiaomi":
        return LLMProfile(
            name=name, provider_kind="anthropic",
            api_key=cfg.claude_xiaomi_api_key,
            base_url=cfg.claude_xiaomi_base_url,
            model=cfg.claude_xiaomi_model,
            max_tokens=cfg.max_tokens,
            notes="小米内网代理 Claude",
        )
    elif name == "claude-official":
        return LLMProfile(
            name=name, provider_kind="anthropic",
            api_key=cfg.claude_official_api_key,
            base_url=cfg.claude_official_base_url,
            model=cfg.claude_official_model,
            max_tokens=cfg.max_tokens,
            notes="Claude 官方 API",
        )
    elif name == "openai":
        return LLMProfile(
            name=name, provider_kind="openai",
            api_key=cfg.openai_api_key,
            base_url=cfg.openai_base_url,
            model=cfg.openai_model,
            notes="OpenAI 兼容入口",
        )
    elif name == "deepseek-pro":
        return LLMProfile(
            name=name, provider_kind="openai",
            api_key=cfg.deepseek_api_key,
            base_url=cfg.deepseek_base_url,
            model=cfg.deepseek_pro_model,
            reasoning_effort=(
                cfg.deepseek_reasoning_effort
                if cfg.deepseek_pro_thinking else ""
            ),
            extra_body=(
                {"thinking": {"type": "enabled"}}
                if cfg.deepseek_pro_thinking else {}
            ),
            notes="DeepSeek v4-pro（强推理）",
        )
    elif name == "deepseek-flash":
        return LLMProfile(
            name=name, provider_kind="openai",
            api_key=cfg.deepseek_api_key,
            base_url=cfg.deepseek_base_url,
            model=cfg.deepseek_flash_model,
            reasoning_effort=(
                cfg.deepseek_reasoning_effort
                if cfg.deepseek_flash_thinking else ""
            ),
            extra_body=(
                {"thinking": {"type": "enabled"}}
                if cfg.deepseek_flash_thinking else {}
            ),
            notes="DeepSeek v4-flash（轻量）",
        )
    else:
        raise ValueError(f"未知的 Provider: {name}")


def _make_provider(cfg: Config, name: str) -> Provider:
    """M3：薄壳——先把 .env 配置转成临时 LLMProfile，再走统一工厂。"""
    return make_provider_from_profile(
        _env_to_profile(cfg, name), max_tokens=cfg.max_tokens,
    )


def _build_llm_profile_seeds(cfg: Config) -> list:
    """从 .env 的 5 个 provider 配置派生初始 LLMProfile 列表（跳过 api_key 为空的）。

    只在首次启动（世界树 llm_profiles 表为空）时种入。.env 变更不影响已种数据。
    M3：复用 _env_to_profile 单一来源。
    """
    candidates = [
        ("claude-xiaomi", cfg.claude_xiaomi_api_key),
        ("claude-official", cfg.claude_official_api_key),
        ("openai", cfg.openai_api_key),
        ("deepseek-pro", cfg.deepseek_api_key),
        ("deepseek-flash", cfg.deepseek_api_key),
    ]
    return [
        _env_to_profile(cfg, name)
        for name, key in candidates if key
    ]


async def _seed_llm_profiles_if_empty(irminsul: Irminsul, cfg: Config) -> None:
    """首次启动种初始 profile。llm_profiles 表非空时跳过（幂等）。"""
    existing = await irminsul.llm_profile_list()
    if existing:
        return
    seeds = _build_llm_profile_seeds(cfg)
    if not seeds:
        logger.info("[派蒙·启动] LLM Profile seed 跳过（.env 无任何 api_key）")
        return
    created_names: list[str] = []
    for profile in seeds:
        try:
            await irminsul.llm_profile_create(profile, actor="seed")
            created_names.append(profile.name)
        except Exception as e:
            logger.warning("[派蒙·启动] seed profile '{}' 失败: {}", profile.name, e)
    # 把 .env 当前 LLM_PROVIDER 对应那条标为默认
    if cfg.llm_provider in created_names:
        try:
            await irminsul.llm_profile_set_default_by_name(
                cfg.llm_provider, actor="seed",
            )
        except Exception as e:
            logger.warning("[派蒙·启动] seed 设默认 '{}' 失败: {}", cfg.llm_provider, e)
    logger.info(
        "[派蒙·启动] LLM Profile seed 完成 共 {} 条 default={}",
        len(created_names), cfg.llm_provider,
    )


async def create_app(cfg: Config) -> list[Channel]:
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
    from paimon.angels.registry import SkillRegistry

    project_root = Path(__file__).parent.parent
    state.tool_registry = ToolRegistry.load(project_root / "tools")
    state.skill_registry = SkillRegistry(project_root / "skills")
    state.skill_registry.scan_and_load()
    # 冰神职责：把内存 registry 持久化到世界树 skill_declarations 表
    await state.skill_registry.sync_to_irminsul(state.irminsul)

    # 冰神 B-2：skill 目录热加载（docs/angels/angels.md §热加载）
    state.skill_hot_loader = None
    if cfg.skills_hot_reload:
        from paimon.angels.watcher import SkillHotLoader
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
        ensure_mihoyo_subscriptions as _furina_ensure_sub,
    )
    _furina_sub_reg()  # 水神·游戏注册 'mihoyo_game'

    # 启动时给所有米哈游账号 ensure 游戏资讯订阅（幂等：已存在仅触发迁移逻辑）
    # ensure_mihoyo_subscriptions 内含 task_type 迁移：feed_collect → mihoyo_game_collect
    # 不能 if existing: continue 跳过，否则迁移代码永远跑不到
    try:
        from paimon.channels.webui.channel import PUSH_CHAT_ID
        accs = await state.irminsul.mihoyo_account_list()
        for acc in accs:
            await _furina_ensure_sub(
                state.irminsul, state.march,
                uid=acc.uid, game=acc.game,
                chat_id=PUSH_CHAT_ID, channel_name="webui",
            )
        if accs:
            logger.info(
                "[水神·游戏订阅·启动 ensure] 处理 {} 个账号（含 task_type 迁移）",
                len(accs),
            )
    except Exception as e:
        logger.warning("[水神·游戏订阅·启动 ensure] 失败（不阻塞启动）: {}", e)

    # 岩神·红利股定时任务：默认启用（dividend_auto_enable=True）
    # 单用户自用场景开箱即用；只创建缺失的 cron，不恢复被 /dividend off 过的
    if cfg.dividend_auto_enable:
        try:
            from paimon.core.commands import toggle_dividend_cron
            from paimon.channels.webui.channel import PUSH_CHAT_ID
            ok, msg = await toggle_dividend_cron(
                enable=True,
                channel_name="webui",
                chat_id=PUSH_CHAT_ID,
                restore_disabled=False,   # 尊重用户的 /dividend off
            )
            if ok:
                logger.info("[岩神·启动] {}（可用 DIVIDEND_AUTO_ENABLE=false 关闭）", msg)
            else:
                logger.warning("[岩神·启动] 自动启用失败: {}", msg)
        except Exception as e:
            logger.warning("[岩神·启动] 自动启用异常（不阻塞）: {}", e)

    # 水神·游戏每日采集 cron：8:05 一次，只在有绑定账号时默认开启
    try:
        from paimon.channels.webui.channel import PUSH_CHAT_ID
        existing = await state.march.list_tasks()
        types_present = {t.task_type for t in existing}
        if "mihoyo_collect" not in types_present:
            # 有账号才默认创建，避免用户从未绑定却有无效 cron
            accs = await state.irminsul.mihoyo_account_list()
            if accs:
                await state.march.create_task(
                    chat_id=PUSH_CHAT_ID, channel_name="webui", prompt="",
                    trigger_type="cron", trigger_value={"expr": "5 8 * * *"},
                    task_type="mihoyo_collect", source_entity_id="all",
                )
                logger.info("[水神·游戏·启动] 已创建每日采集 cron（8:05）")
    except Exception as e:
        logger.warning("[水神·游戏·启动] 创建 cron 异常（不阻塞）: {}", e)

    # 草神·记忆 + 知识库整理 cron：周一 00:00 / 00:10 当地时间，错峰避免两个同时跑
    try:
        from paimon.channels.webui.channel import PUSH_CHAT_ID
        existing = await state.march.list_tasks()
        types_present = {t.task_type for t in existing}
        if "memory_hygiene" not in types_present:
            await state.march.create_task(
                chat_id=PUSH_CHAT_ID, channel_name="webui", prompt="",
                trigger_type="cron", trigger_value={"expr": "0 0 * * 1"},
                task_type="memory_hygiene", source_entity_id="all",
            )
            logger.info("[草神·启动] 已创建记忆整理 cron（周一 00:00）")
        if "kb_hygiene" not in types_present:
            await state.march.create_task(
                chat_id=PUSH_CHAT_ID, channel_name="webui", prompt="",
                trigger_type="cron", trigger_value={"expr": "10 0 * * 1"},
                task_type="kb_hygiene", source_entity_id="all",
            )
            logger.info("[草神·启动] 已创建知识库整理 cron（周一 00:10）")
    except Exception as e:
        logger.warning("[草神·启动] 创建整理 cron 异常（不阻塞）: {}", e)

    # 授权体系：世界树灌缓存 + 决策器初始化
    from paimon.core.authz import AuthzCache, AuthzDecision
    state.authz_cache = AuthzCache()
    await state.authz_cache.load(state.irminsul)
    state.authz_decision = AuthzDecision(
        state.authz_cache, state.irminsul, state.skill_registry,
    )

    # 启动时自动放行：单用户自用场景下，已加载的 builtin skill + 7 个 archon
    # 视为可信（git review 已把过关；真破坏命令由 pre_filter 拦）。运行时通过
    # watcher 加载的 plugin / AI 生成 skill 不在此白名单，仍走死执 review。
    # 仅跳过用户已显式 permanent_deny 的，避免覆盖严格意图。
    # 详见 docs/todo.md「权限体系 v2 重新设计」。
    try:
        snapshot = await state.irminsul.authz_snapshot()
        from paimon.shades.asmoday import _ARCHON_REGISTRY
        targets: list[tuple[str, str]] = []
        targets.extend(("skill", s.name) for s in state.skill_registry.list_all())
        targets.extend(("shades_node", n) for n in _ARCHON_REGISTRY.keys())
        auto_count = 0
        for subj_type, subj_id in targets:
            existing = snapshot.get((subj_type, subj_id))
            if existing == "permanent_deny":
                continue   # 用户明确禁止过，不覆盖
            if existing == "permanent_allow":
                continue   # 已经放行，不重复写
            await state.irminsul.authz_set(
                subj_type, subj_id, "permanent_allow",
                actor="启动·自动放行",
                reason="启动时已加载，单用户自用场景默认放行",
            )
            auto_count += 1
        if auto_count:
            await state.authz_cache.load(state.irminsul)  # 让本次写入立刻生效
            logger.info("[派蒙·授权] 启动时自动放行 {} 项（skill + archon）", auto_count)
    except Exception as e:
        logger.warning("[派蒙·授权] 启动时自动放行失败（不阻塞）: {}", e)

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
        logger.info("[派蒙·启动] WebUI频道已启用 http://{}:{}", cfg.webui_host, cfg.webui_port)

    if cfg.bot_token:
        from paimon.channels.telegram import TelegramChannel
        tg_channel = TelegramChannel(
            token=cfg.bot_token,
            owner_id=cfg.owner_id,
        )
        channels.append(tg_channel)
        logger.info("[派蒙·启动] Telegram频道已启用")

    if cfg.qq_appid and cfg.qq_secret:
        from paimon.channels.qq import QQChannel
        qq_channel = QQChannel(
            appid=cfg.qq_appid,
            secret=cfg.qq_secret,
            owner_ids=cfg.qq_owner_ids,
        )
        channels.append(qq_channel)
        logger.info("[派蒙·启动] QQ频道已启用")

    state.channels = {ch.name: ch for ch in channels}

    # 派蒙订阅三月响铃 → 投递给用户
    from paimon.foundation.leyline import Event

    async def _on_march_ring(event: Event) -> None:
        payload = event.payload
        channel_name = payload.get("channel_name", "")
        chat_id = payload.get("chat_id", "")
        prompt = payload.get("prompt", "")
        task_id = payload.get("task_id", "")

        # ---- 方案 D：非 user 类型的周期任务经 task_types registry 分派 ----
        # payload 需带 task_id（由 march._fire_task 注入），拉完整 ScheduledTask
        # 读 task_type 和 source_entity_id；dispatcher 由各 archon 注册时注入。
        if task_id and state.irminsul:
            task = None
            try:
                task = await state.irminsul.schedule_get(task_id)
            except Exception as e:
                logger.debug("[三月·分派] 读任务失败 task_id={}: {}", task_id, e)
            if task and task.task_type and task.task_type != "user":
                from paimon.foundation import task_types as _tt
                meta = _tt.get(task.task_type)
                if meta is None:
                    logger.warning(
                        "[三月·分派] 未知 task_type={} task_id={}（未注册；"
                        "不 fallback 到 LLM 以避免把内部任务误当用户 prompt）",
                        task.task_type, task_id,
                    )
                    return
                try:
                    await meta.dispatcher(task, state)
                except Exception as e:
                    logger.exception(
                        "[三月·{}] 分派异常 task_id={}: {}",
                        meta.display_label, task_id, e,
                    )
                return

        # 三月·Deep 自检的 [SELFCHECK_DEEP] cron 分派已撤销（docs/todo.md §
        # 三月·自检·Deep 暂缓）。当前 LLM 模型对 check skill 跑不充分，
        # 周期性自动触发没意义；底层 SelfCheckService.run_deep 代码保留，
        # 只留手动入口（/selfcheck --deep，受 selfcheck_deep_hidden 开关）。

        channel = state.channels.get(channel_name)
        if not channel:
            logger.warning("[派蒙·响铃] 频道不存在: {}", channel_name)
            return

        # 频道能力分流（docs/aimon.md §2.6）：QQ 等不支持主动推送的频道静默跳过
        if not getattr(channel, "supports_push", True):
            logger.info(
                "[派蒙·响铃] 频道 {} 不支持推送，跳过投递（数据已落盘，用户需主动查询）",
                channel_name,
            )
            return

        if prompt and state.model:
            try:
                from paimon.session import Session
                # 每次响铃用独立 session id，避免并发任务的 token 记录全聚合到 "march-tmp"
                task_id = payload.get("task_id", "")
                tmp_sid = f"march-{task_id[:12]}" if task_id else "march-tmp"
                temp_session = Session(id=tmp_sid, name="三月任务")
                text_parts = []
                async for chunk in state.model.chat(
                    temp_session, prompt,
                    component="march", purpose="定时任务",
                ):
                    text_parts.append(chunk)
                result = "".join(text_parts)
                if result.strip():
                    await channel.send_text(chat_id, result)
            except Exception as e:
                logger.error("[派蒙·响铃] LLM 处理失败 task={}: {}", payload.get("task_id", ""), e)
                try:
                    await channel.send_text(chat_id, f"定时任务执行失败: {e}")
                except Exception as e2:
                    logger.error("[派蒙·响铃] 错误信息投递也失败: {}", e2)
        else:
            message = payload.get("message", "")
            if message:
                try:
                    await channel.send_text(chat_id, message)
                except Exception as e:
                    logger.error("[派蒙·响铃] 无 prompt 投递失败: {}", e)

    state.leyline.subscribe("march.ring", _on_march_ring)

    # 权限缓存：新 skill 上线（冰神审过 → 四影通知）/ skill 被撤销时失效对应缓存
    async def _on_skill_loaded(event: Event) -> None:
        payload = event.payload
        name = payload.get("name")
        if state.authz_cache and name:
            state.authz_cache.invalidate("skill", name)

    state.leyline.subscribe("skill.loaded", _on_skill_loaded)
    # 热卸载 / orphan 场景：撤销后也失效 authz 缓存（避免 dangling 授权被消费）
    state.leyline.subscribe("skill.revoked", _on_skill_loaded)

    # M2：profile / route 热切换（面板保存后触发对应缓存失效）
    async def _on_llm_profile_updated(event: Event) -> None:
        payload = event.payload or {}
        pid = payload.get("profile_id", "")
        action = payload.get("action", "")
        if pid and state.gnosis:
            state.gnosis.invalidate_profile(pid)
        # 删除 profile 时 DB FK CASCADE 已清 llm_routes 的对应行，但
        # ModelRouter 内存缓存还持有旧映射；reload 同步之。set_default
        # 不影响路由表，无需 reload。
        if action == "delete" and state.model_router:
            await state.model_router.reload()

    async def _on_llm_route_updated(event: Event) -> None:
        if state.model_router:
            await state.model_router.reload()

    state.leyline.subscribe("llm.profile.updated", _on_llm_profile_updated)
    state.leyline.subscribe("llm.route.updated", _on_llm_route_updated)

    logger.info(
        "[派蒙·启动] 系统就绪 (模型={}, 频道={})",
        cfg.model,
        [ch.name for ch in channels],
    )
    return channels
