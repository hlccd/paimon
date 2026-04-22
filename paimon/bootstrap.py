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

        channel = state.channels.get(channel_name)
        if not channel:
            logger.warning("[派蒙·响铃] 频道不存在: {}", channel_name)
            return

        if prompt and state.model:
            try:
                from paimon.session import Session
                temp_session = Session(id="march-tmp", name="三月任务")
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
                logger.error("[派蒙·响铃] LLM 处理失败: {}", e)
                await channel.send_text(chat_id, f"定时任务执行失败: {e}")
        else:
            message = payload.get("message", "")
            if message:
                await channel.send_text(chat_id, message)

    state.leyline.subscribe("march.ring", _on_march_ring)

    # 权限缓存：新 skill 上线（冰神审过 → 四影通知）时失效对应缓存
    async def _on_skill_loaded(event: Event) -> None:
        payload = event.payload
        name = payload.get("name")
        if state.authz_cache and name:
            state.authz_cache.invalidate("skill", name)

    state.leyline.subscribe("skill.loaded", _on_skill_loaded)

    logger.info(
        "[派蒙·启动] 系统就绪 (模型={}, 频道={})",
        cfg.model,
        [ch.name for ch in channels],
    )
    return channels
