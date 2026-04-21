from __future__ import annotations

from loguru import logger

from paimon.channels.base import Channel
from paimon.config import Config
from paimon.foundation.gnosis import Gnosis
from paimon.foundation.irminsul import Irminsul
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

    logger.info(
        "[派蒙·启动] 系统就绪 (模型={}, 频道={})",
        cfg.model,
        [ch.name for ch in channels],
    )
    return channels
