from __future__ import annotations

from loguru import logger

from paimon.channels.base import Channel
from paimon.config import Config
from paimon.foundation.gnosis import Gnosis
from paimon.foundation.irminsul import Irminsul
from paimon.foundation.leyline import Leyline
from paimon.foundation.march import MarchService
from paimon.foundation.primogem import Primogem
from paimon.llm import AnthropicProvider, Model, OpenAIProvider
from paimon.llm.base import Provider
from paimon.session import SessionManager
from paimon.state import state


def _make_provider(cfg: Config, name: str) -> Provider:
    if name == "claude-xiaomi":
        return AnthropicProvider.from_params(
            api_key=cfg.claude_xiaomi_api_key,
            base_url=cfg.claude_xiaomi_base_url,
            model=cfg.claude_xiaomi_model,
            max_tokens=cfg.max_tokens,
        )
    elif name == "claude-official":
        return AnthropicProvider.from_params(
            api_key=cfg.claude_official_api_key,
            base_url=cfg.claude_official_base_url,
            model=cfg.claude_official_model,
            max_tokens=cfg.max_tokens,
        )
    elif name == "openai":
        return OpenAIProvider.from_params(
            api_key=cfg.openai_api_key,
            base_url=cfg.openai_base_url,
            model=cfg.openai_model,
        )
    else:
        raise ValueError(f"未知的 Provider: {name}")


async def create_app(cfg: Config) -> list[Channel]:
    state.cfg = cfg
    state.session_tasks.clear()
    state.session_task_locks.clear()

    cfg.paimon_home.mkdir(parents=True, exist_ok=True)

    # 世界树最早初始化（全系统唯一存储层）
    state.irminsul = Irminsul(cfg.paimon_home)
    await state.irminsul.initialize()

    # 会话管理器从世界树恢复
    state.session_mgr = await SessionManager.load(state.irminsul)

    # 地脉事件总线
    state.leyline = Leyline()

    # 三月调度服务
    state.march = MarchService(state.irminsul, state.leyline)

    # 原石持有世界树引用（服务层）
    state.primogem = Primogem(state.irminsul)

    gnosis = Gnosis(cfg)
    state.gnosis = gnosis

    primary_provider = _make_provider(cfg, cfg.llm_provider)
    gnosis.register(cfg.llm_provider, primary_provider)

    deep_name = cfg.llm_deep_provider or cfg.llm_provider
    if deep_name != cfg.llm_provider:
        deep_provider = _make_provider(cfg, deep_name)
        gnosis.register(deep_name, deep_provider)

    state.model = Model(primary_provider, gnosis)

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
    from paimon.archons.venti import VentiArchon
    state.venti = VentiArchon()

    # 岩神单例（红利股追踪 cron 触发；同上）
    from paimon.archons.zhongli import ZhongliArchon
    state.zhongli = ZhongliArchon()

    # 授权体系：世界树灌缓存 + 决策器初始化
    from paimon.core.authz import AuthzCache, AuthzDecision
    state.authz_cache = AuthzCache()
    await state.authz_cache.load(state.irminsul)
    state.authz_decision = AuthzDecision(
        state.authz_cache, state.irminsul, state.skill_registry,
    )

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

        # ---- 岩神红利股采集（前缀分派，不走频道投递）----
        # scheduled_tasks.task_prompt 形如 "[DIVIDEND_SCAN] full|daily|rescore"
        # 由 /dividend on 创建两个 cron（daily + full）；rescore 为手动触发。
        if prompt.startswith("[DIVIDEND_SCAN] "):
            mode = prompt.split(" ", 1)[1].strip()
            if not state.zhongli:
                logger.error("[岩神·采集] 岩神未就绪，跳过 mode={}", mode)
                return
            try:
                await state.zhongli.collect_dividend(
                    mode=mode,
                    irminsul=state.irminsul,
                    march=state.march,
                    chat_id=chat_id,
                    channel_name=channel_name,
                )
            except Exception as e:
                logger.exception("[岩神·采集] 异常 mode={}: {}", mode, e)
            return

        # ---- 风神订阅采集（前缀分派，不走频道投递）----
        # scheduled_tasks.task_prompt 形如 "[FEED_COLLECT] <sub_id>"
        # 由 /subscribe 指令创建；cron 到点触发后由风神采集 + 内部再 ring_event 推送。
        # 无论 state.venti 是否就绪都必须拦截前缀 prompt，避免误发给 LLM。
        if prompt.startswith("[FEED_COLLECT] "):
            sub_id = prompt.split(" ", 1)[1].strip()
            if not state.venti:
                logger.error("[风神·订阅] 风神未就绪，跳过采集 sub={}", sub_id)
                return
            try:
                await state.venti.collect_subscription(
                    sub_id,
                    irminsul=state.irminsul,
                    model=state.model,
                    march=state.march,
                )
            except Exception as e:
                logger.exception("[风神·订阅] 采集异常 sub={}: {}", sub_id, e)
                if state.irminsul:
                    try:
                        await state.irminsul.subscription_update(
                            sub_id, actor="风神", last_error=str(e)[:500],
                        )
                    except Exception:
                        pass
            return

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

    logger.info(
        "[派蒙·启动] 系统就绪 (模型={}, 频道={})",
        cfg.model,
        [ch.name for ch in channels],
    )
    return channels
