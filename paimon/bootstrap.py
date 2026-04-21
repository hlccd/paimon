from __future__ import annotations

from loguru import logger

from paimon.channels.base import Channel
from paimon.config import Config
from paimon.llm import AnthropicProvider, Model, OpenAIProvider
from paimon.session import SessionManager
from paimon.state import state


def create_app(cfg: Config) -> list[Channel]:
    state.cfg = cfg
    state.session_tasks.clear()
    state.session_task_locks.clear()

    cfg.paimon_home.mkdir(parents=True, exist_ok=True)

    state.session_mgr = SessionManager.load(cfg.paimon_home)

    if cfg.provider == "anthropic":
        provider = AnthropicProvider(cfg)
    else:
        provider = OpenAIProvider(cfg)
    state.model = Model(provider)

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
