"""风神 · 事件处理 process 主流程：聚类 LLM → 分析 LLM → upsert feed_events。"""
from __future__ import annotations

import json
import time
from typing import TYPE_CHECKING, Any
from urllib.parse import urlparse

from loguru import logger

from ._models import (
    LOOKBACK_SECONDS, MAX_DESC_LEN, MAX_ITEMS_PER_EVENT,
    MAX_RECENT_CANDIDATES, MAX_SUMMARY_LEN, MAX_TITLE_LEN,
    _VALID_SENTIMENT_LABEL, _VALID_SEVERITY,
    ProcessedEvent, _extract_domain, _strip_code_fence, _truncate,
)

from paimon.foundation.irminsul.feed_event import FeedEvent

if TYPE_CHECKING:
    from paimon.foundation.irminsul.subscription import Subscription


class _ProcessMixin:
    """风神事件处理主流程方法集合（process）。"""

    async def process(
        self, sub: "Subscription", item_rows: list[dict[str, Any]],
    ) -> list[ProcessedEvent]:
        """主入口。

        item_rows: 来自 feed_items_insert 后的条目，每个 dict 必须含
        {id(int from db), title, url, description, captured_at}
        """
        if not item_rows:
            return []

        now = time.time()

        # 1) 准备聚类候选（同订阅 7 天内）
        recent: list[FeedEvent] = []
        if not self._force_new:
            recent = await self._iru.feed_event_list(
                sub_id=sub.id,
                since=now - LOOKBACK_SECONDS,
                limit=MAX_RECENT_CANDIDATES,
            )

        # 2) 聚类：grouping 决策
        # - force_new=True：跳过 LLM，每条独立成一组（仅用于排查 / fallback）
        # - 否则：调 LLM 做 grouping。同批次内多条是同事件时合并成一组；
        #   recent 即使为空（首次跑 / 周期内无历史）也调，让 LLM 至少做同批次内合并。
        #   单条输入也调（极便宜，但保证一致性）
        if self._force_new:
            groups: list[dict[str, Any]] = [
                {"item_indices": [i], "merge_with_event_id": None}
                for i in range(len(item_rows))
            ]
        elif len(item_rows) <= 1:
            # 单条没合并空间，省一次 LLM
            groups = [
                {"item_indices": [i], "merge_with_event_id": None}
                for i in range(len(item_rows))
            ]
        else:
            groups = await self._llm_cluster(sub.query, recent, item_rows)

        # 漏标兜底：LLM 没列入任何 group 的 item，单条独立成新事件
        # （宁可分裂也不丢条目；feed_items 已落库不能没 event_id）
        covered_idxs: set[int] = set()
        for g in groups:
            covered_idxs.update(g.get("item_indices") or [])
        missing = [i for i in range(len(item_rows)) if i not in covered_idxs]
        if missing:
            logger.warning(
                "[风神·事件] 聚类 LLM 漏标 {} 条 → 强制独立 new 兜底",
                len(missing),
            )
            for i in missing:
                groups.append({"item_indices": [i], "merge_with_event_id": None})

        # 3) 逐组：分析 → upsert → attach feed_items
        results: list[ProcessedEvent] = []
        recent_by_id = {ev.id: ev for ev in recent}
        llm_calls_used = 0  # LLM 调用预算计数（不含聚类那一次）

        for group in groups:
            idxs: list[int] = list(group.get("item_indices") or [])
            if not idxs:
                continue
            # 单事件最多 MAX_ITEMS_PER_EVENT 条
            idxs = idxs[:MAX_ITEMS_PER_EVENT]
            group_items = [item_rows[i] for i in idxs]
            merge_target_id = group.get("merge_with_event_id") or ""

            base_event = None
            if merge_target_id:
                base_event = recent_by_id.get(merge_target_id)
                # 二次保险：在并发场景下事件可能刚被 sweep
                if base_event is None:
                    base_event = await self._iru.feed_event_get(merge_target_id)

            # 超预算后剩余事件走 fallback，不再调 LLM
            budget_exceeded = (
                self._max_llm_calls is not None
                and llm_calls_used >= self._max_llm_calls
            )
            if budget_exceeded:
                if llm_calls_used == self._max_llm_calls:
                    # 第一次踩线提示一次（避免每个 group 都打 warning）
                    logger.warning(
                        "[风神·事件] LLM 预算 {} 已耗尽，剩余事件走 fallback",
                        self._max_llm_calls,
                    )
                analysis = self._fallback_analysis(group_items, base_event)
            else:
                try:
                    analysis = await self._llm_analyze(
                        sub.query, group_items, base_event,
                    )
                    llm_calls_used += 1
                except Exception as e:
                    logger.warning(
                        "[风神·事件] analyze LLM 异常 sub={} merge={}: {}",
                        sub.id, merge_target_id or "(new)", e,
                    )
                    analysis = self._fallback_analysis(group_items, base_event)

            sources = sorted({
                _extract_domain(it.get("url") or "")
                for it in group_items
            } - {""})

            if base_event is not None:
                # merge：累计 item_count、合并 sources、更新所有分析字段
                merged_sources = sorted(set(base_event.sources) | set(sources))
                await self._iru.feed_event_update(
                    base_event.id, actor="风神",
                    title=analysis["title"],
                    summary=analysis["summary"],
                    entities=analysis["entities"],
                    timeline=analysis["timeline"],
                    severity=analysis["severity"],
                    sentiment_score=analysis["sentiment_score"],
                    sentiment_label=analysis["sentiment_label"],
                    last_seen_at=now,
                    sources=merged_sources,
                    item_count_inc=len(group_items),
                )
                event_id = base_event.id
                base_severity = base_event.severity
                is_new = False
            else:
                # new：建事件
                from paimon.foundation.irminsul import FeedEvent as _FE
                new_event = _FE(
                    subscription_id=sub.id,
                    title=analysis["title"],
                    summary=analysis["summary"],
                    entities=analysis["entities"],
                    timeline=analysis["timeline"],
                    severity=analysis["severity"],
                    sentiment_score=analysis["sentiment_score"],
                    sentiment_label=analysis["sentiment_label"],
                    item_count=len(group_items),
                    first_seen_at=now,
                    last_seen_at=now,
                    sources=sources,
                )
                event_id = await self._iru.feed_event_create(
                    new_event, actor="风神",
                )
                base_severity = ""
                is_new = True

            # 5) 回写 feed_items.event_id + sentiment
            item_ids = [it["id"] for it in group_items]
            await self._iru.feed_items_attach_event(
                item_ids, event_id,
                sentiment_score=analysis["sentiment_score"],
                sentiment_label=analysis["sentiment_label"],
                actor="风神",
            )

            results.append(ProcessedEvent(
                event_id=event_id,
                severity=analysis["severity"],
                base_severity=base_severity,
                is_new=is_new,
                severity_changed=(analysis["severity"] != base_severity),
                title=analysis["title"],
                summary=analysis["summary"],
                first_url=(group_items[0].get("url") or ""),
                item_count=len(group_items),
                sentiment_label=analysis["sentiment_label"],
                sentiment_score=float(analysis["sentiment_score"]),
                last_seen_at=now,
                timeline=list(analysis.get("timeline") or []),
            ))

        logger.info(
            "[风神·事件] 处理完成 sub={} 输入={} 事件={}（新={} 合并={}）",
            sub.id, len(item_rows), len(results),
            sum(1 for r in results if r.is_new),
            sum(1 for r in results if not r.is_new),
        )
        return results
