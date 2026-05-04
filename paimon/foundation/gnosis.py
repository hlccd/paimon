"""
神之心 (Gnosis) — LLM 资源池管理

浅层池: 轻量任务 (闲聊/标题/压缩)
深层池: 重型任务 (Agent/DAG编排)
非抢占式调度: semaphore 限制并发
故障切换: provider 失败时自动切换到备选
"""
from __future__ import annotations

import asyncio
import time
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Literal

from loguru import logger

if TYPE_CHECKING:
    from paimon.config import Config
    from paimon.foundation.irminsul import Irminsul
    from paimon.foundation.irminsul.llm_profile import LLMProfile
    from paimon.llm.base import Provider

Depth = Literal["shallow", "deep"]

_HEALTH_COOLDOWN = 60.0


def make_provider_from_profile(profile: "LLMProfile", *, max_tokens: int = 64000):
    """按 LLMProfile.provider_kind 构造对应 Provider 实例。

    M2 新抽：让 Gnosis 按 profile_id 按需构造 / 缓存 Provider，无需再跟
    `.env LLM_PROVIDER` 绑死。bootstrap._make_provider 作为 .env 启动路径
    的兜底仍保留，两条路径最终都会并存于 Gnosis._providers。
    """
    from paimon.llm import AnthropicProvider, OpenAIProvider

    kind = (profile.provider_kind or "openai").strip().lower()
    if kind == "anthropic":
        return AnthropicProvider.from_params(
            api_key=profile.api_key,
            base_url=profile.base_url,
            model=profile.model,
            max_tokens=profile.max_tokens or max_tokens,
        )
    # openai 兼容
    return OpenAIProvider.from_params(
        api_key=profile.api_key,
        base_url=profile.base_url,
        model=profile.model,
        extra_body=profile.extra_body or None,
        reasoning_effort=profile.reasoning_effort or None,
    )


@dataclass
class ProviderHealth:
    name: str
    provider: Provider
    healthy: bool = True
    last_failure: float = 0.0
    failure_count: int = 0


@dataclass
class Pool:
    depth: Depth
    primary: str
    semaphore: asyncio.Semaphore | None = None
    fallback_order: list[str] = field(default_factory=list)


class Gnosis:
    def __init__(self, cfg: Config):
        self._providers: dict[str, ProviderHealth] = {}
        self._pools: dict[Depth, Pool] = {}
        self._cfg = cfg
        # M2：按 profile_id 缓存 Provider 实例（构造成本：新建 SDK client）
        # 热切换时由 leyline `llm.profile.updated` 触发 invalidate_profile
        self._by_profile: dict[str, ProviderHealth] = {}
        # 并发 cache miss 时互斥构造（避免同 pid 构造两次 client 泄露）
        self._profile_build_lock = asyncio.Lock()
        self._irminsul: "Irminsul | None" = None  # bootstrap 注入，get_provider_by_profile_id 用

    def register(self, name: str, provider: Provider) -> None:
        self._providers[name] = ProviderHealth(name=name, provider=provider)
        logger.debug("[神之心·注册] Provider '{}' (model={})", name, provider.model_name)

    def setup_pools(self) -> None:
        cfg = self._cfg
        shallow_name = cfg.llm_provider
        deep_name = cfg.llm_deep_provider or cfg.llm_provider

        all_names = list(self._providers.keys())

        self._pools["shallow"] = Pool(
            depth="shallow",
            primary=shallow_name,
            semaphore=asyncio.Semaphore(cfg.gnosis_shallow_concurrency),
            fallback_order=[n for n in all_names if n != shallow_name],
        )
        self._pools["deep"] = Pool(
            depth="deep",
            primary=deep_name,
            semaphore=asyncio.Semaphore(cfg.gnosis_deep_concurrency),
            fallback_order=[n for n in all_names if n != deep_name],
        )
        logger.info(
            "[神之心·调度] 资源池就绪 shallow={}/{} deep={}/{}",
            shallow_name, cfg.gnosis_shallow_concurrency,
            deep_name, cfg.gnosis_deep_concurrency,
        )

    def get_provider(self, depth: Depth = "shallow") -> Provider:
        pool = self._pools.get(depth)
        if not pool:
            return self._any_provider()

        ph = self._providers.get(pool.primary)
        if ph and self._is_available(ph):
            return ph.provider

        for name in pool.fallback_order:
            ph = self._providers.get(name)
            if ph and self._is_available(ph):
                logger.warning("[神之心·故障切换] {}池主力不可用，切换到 '{}'", depth, name)
                return ph.provider

        return self._providers[pool.primary].provider

    @asynccontextmanager
    async def acquire(self, depth: Depth = "shallow"):
        pool = self._pools.get(depth)
        if pool and pool.semaphore:
            await pool.semaphore.acquire()
            try:
                yield self.get_provider(depth)
            finally:
                pool.semaphore.release()
        else:
            yield self.get_provider(depth)

    def report_failure(self, provider_name: str) -> None:
        ph = self._providers.get(provider_name)
        if not ph:
            return
        ph.healthy = False
        ph.last_failure = time.time()
        ph.failure_count += 1
        logger.warning(
            "[神之心·故障] Provider '{}' 标记为不可用 (连续失败={})",
            provider_name, ph.failure_count,
        )

    def report_success(self, provider_name: str) -> None:
        ph = self._providers.get(provider_name)
        if ph and not ph.healthy:
            ph.healthy = True
            ph.failure_count = 0
            logger.info("[神之心·恢复] Provider '{}' 恢复正常", provider_name)

    def _is_available(self, ph: ProviderHealth) -> bool:
        if ph.healthy:
            return True
        return time.time() - ph.last_failure > _HEALTH_COOLDOWN

    def _any_provider(self) -> Provider:
        return next(iter(self._providers.values())).provider

    # ==================== M2: profile 级 Provider 管理 ====================

    def attach_irminsul(self, irminsul: "Irminsul") -> None:
        """bootstrap 完成 irminsul 初始化后注入，供 get_provider_by_profile_id 读 profile。"""
        self._irminsul = irminsul

    async def get_provider_by_profile_id(self, profile_id: str) -> "Provider | None":
        """按 profile_id 取 Provider；不在缓存则从世界树按需构造。

        返回 None 的情况：profile 不存在 / api_key 缺失 / 当前不健康且未过冷却窗口。
        上层收到 None 应回落到 get_default_provider / self.provider。

        并发安全：fast path 无锁（命中缓存 + 健康）；miss 路径上 lock 避免
        同 pid 并发构造出两个 client（双 double-check 模式）。
        """
        if not profile_id:
            return None
        # Fast path: 命中且健康直接返（热路径，避免锁）
        ph = self._by_profile.get(profile_id)
        if ph and self._is_available(ph):
            return ph.provider
        if ph and not self._is_available(ph):
            return None   # 不健康，让上层回落

        # Slow path: 需要构造，加锁避免并发重复构造
        async with self._profile_build_lock:
            # double-check：拿锁过程中可能别的协程已构造好
            ph = self._by_profile.get(profile_id)
            if ph and self._is_available(ph):
                return ph.provider
            if ph and not self._is_available(ph):
                return None
            # 真的 miss → 从世界树读 profile 构造
            if self._irminsul is None:
                logger.warning("[神之心] get_provider_by_profile_id 调用时 irminsul 未注入")
                return None
            try:
                profile = await self._irminsul.llm_profile_get(
                    profile_id, include_key=True,
                )
            except Exception as e:
                logger.error("[神之心] 读 profile 失败 {}: {}", profile_id, e)
                return None
            if profile is None:
                logger.warning("[神之心] profile 不存在 {}", profile_id)
                return None
            if not profile.api_key:
                logger.warning(
                    "[神之心] profile '{}' 无 api_key，跳过构造", profile.name,
                )
                return None
            try:
                provider = make_provider_from_profile(
                    profile, max_tokens=self._cfg.max_tokens,
                )
            except Exception as e:
                logger.error(
                    "[神之心] 构造 Provider 失败 profile='{}': {}", profile.name, e,
                )
                return None
            self._by_profile[profile_id] = ProviderHealth(
                name=f"profile:{profile.name}", provider=provider,
            )
            logger.info(
                "[神之心·注册] profile '{}' ({}) -> {} 构造完成",
                profile.name, profile_id, profile.model,
            )
            return provider

    async def get_default_provider(self) -> "Provider | None":
        """全局默认 profile 的 Provider；路由未命中时的兜底。"""
        if self._irminsul is None:
            return None
        try:
            default = await self._irminsul.llm_profile_get_default()
        except Exception:
            return None
        if default is None:
            return None
        return await self.get_provider_by_profile_id(default.id)

    def invalidate_profile(self, profile_id: str) -> None:
        """Leyline `llm.profile.updated/deleted` 回调时调；清指定 profile 的 Provider 缓存。"""
        if not profile_id:
            return
        if profile_id in self._by_profile:
            del self._by_profile[profile_id]
            logger.info("[神之心·热切换] profile {} 缓存失效", profile_id)

    def report_failure_by_profile(self, profile_id: str) -> None:
        ph = self._by_profile.get(profile_id)
        if not ph:
            return
        ph.healthy = False
        ph.last_failure = time.time()
        ph.failure_count += 1
        logger.warning(
            "[神之心·故障] profile '{}' 标记不可用 (连续失败={})",
            ph.name, ph.failure_count,
        )

    def report_success_by_profile(self, profile_id: str) -> None:
        ph = self._by_profile.get(profile_id)
        if ph and not ph.healthy:
            ph.healthy = True
            ph.failure_count = 0
            logger.info("[神之心·恢复] profile '{}' 恢复正常", ph.name)
