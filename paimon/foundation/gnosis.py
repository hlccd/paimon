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
    from paimon.llm.base import Provider

Depth = Literal["shallow", "deep"]

_HEALTH_COOLDOWN = 60.0


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

    def register(self, name: str, provider: Provider) -> None:
        self._providers[name] = ProviderHealth(name=name, provider=provider)
        logger.info("[神之心·注册] Provider '{}' (model={})", name, provider.model_name)

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
