"""风神 · 订阅采集 mixin：collect_subscription 入口（按 binding_kind 分发）。"""
from __future__ import annotations

from typing import TYPE_CHECKING

from loguru import logger

if TYPE_CHECKING:
    from paimon.foundation.irminsul import Irminsul
    from paimon.foundation.march import MarchService
    from paimon.llm.model import Model


class _CollectMixin:
    """订阅采集相关方法集合。"""

    async def collect_subscription(
        self, sub_id: str, *,
        irminsul: Irminsul,
        model: Model,
        march: MarchService,
    ) -> None:
        """订阅采集 dispatcher：按 sub.binding_kind 路由到对应 collector。

        - 'topic_research' → 风神 topic UGC 调研（run_topic_research_collect）
        - 'mihoyo_game' → 水神（run_furina_news_collect）
        - 'stock_watch' → 岩神（run_stock_topic_collect）
        - 其他 archon 注册的 binding_kind → 各自 collector

        feed_collect ScheduledTask 由 bootstrap._on_march_ring 触发，所有 binding_kind
        都走这里 dispatch；inflight 防重在 dispatcher 层做。
        """
        if sub_id in self._inflight:
            logger.info("[风神·订阅] 已在采集中，跳过重复触发 sub={}", sub_id)
            return
        self._inflight.add(sub_id)
        try:
            sub = await irminsul.subscription_get(sub_id)
            if not sub:
                logger.warning("[风神·订阅] 订阅不存在 sub_id={}", sub_id)
                return
            from paimon.foundation import subscription_types
            kind = sub.binding_kind or ""
            meta = subscription_types.get(kind)
            if meta is None:
                logger.warning(
                    "[风神·订阅] 未知 binding_kind={} sub={}（无 collector 注册）",
                    kind, sub_id,
                )
                return
            # 通过 state 调 collector（签名 (sub, state)）
            from paimon.state import state as _state
            await meta.collector(sub, _state)
        finally:
            self._inflight.discard(sub_id)

