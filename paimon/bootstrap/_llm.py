"""启动期 LLM 配置 helper：把 .env 5 个 provider 写法转 LLMProfile + 首启 seed 入库。"""
from __future__ import annotations

from loguru import logger

from paimon.config import Config
from paimon.foundation.gnosis import make_provider_from_profile
from paimon.foundation.irminsul import Irminsul
from paimon.foundation.irminsul.llm_profile import LLMProfile
from paimon.llm.base import Provider


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
