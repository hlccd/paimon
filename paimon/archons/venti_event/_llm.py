"""风神 · 事件聚类 / 分析 LLM 调用 + 失败兜底。"""
from __future__ import annotations

import json
import time
from typing import TYPE_CHECKING, Any
from urllib.parse import urlparse

from loguru import logger

from ._models import (
    MAX_DESC_LEN, MAX_ITEMS_PER_EVENT, MAX_RECENT_CANDIDATES,
    MAX_SUMMARY_LEN, MAX_TITLE_LEN,
    _VALID_SENTIMENT_LABEL, _VALID_SEVERITY,
    _ANALYZE_SYSTEM, _CLUSTER_SYSTEM,
    _extract_domain, _strip_code_fence, _truncate,
)

if TYPE_CHECKING:
    from paimon.foundation.irminsul.feed_event import FeedEvent


class _LLMMixin:
    """风神事件 LLM 调用 + fallback 方法集合。"""

    async def _llm_cluster(
        self, query: str, recent: list["FeedEvent"],
        item_rows: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """聚类 LLM。

        返回 grouping list，每个 group 形如：
        {"item_indices": [int, ...], "merge_with_event_id": str | None}

        失败兜底：每条 item 独立成一组（merge_with_event_id=None），
        等价于"全部新建事件"，不会丢条目。
        """
        n = len(item_rows)
        fallback_groups: list[dict[str, Any]] = [
            {"item_indices": [i], "merge_with_event_id": None}
            for i in range(n)
        ]

        candidates_part = "\n".join(
            f"- event_id={ev.id} severity={ev.severity} title={ev.title}"
            f"\n  summary: {_truncate(ev.summary, 120)}"
            for ev in recent
        ) or "（暂无候选）"
        items_part = "\n".join(
            f"[{i}] title: {_truncate(it.get('title', ''), 100)}"
            f"\n     url: {it.get('url', '')}"
            f"\n     desc: {_truncate(it.get('description', ''), 150)}"
            for i, it in enumerate(item_rows)
        )
        user_msg = (
            f"订阅关键词: {query}\n\n"
            f"## 候选事件（近 7 天，最多 {MAX_RECENT_CANDIDATES} 条）\n"
            f"{candidates_part}\n\n"
            f"## 待判定的新条目（共 {n} 条；下标 0~{n-1}）\n"
            f"{items_part}\n"
        )
        messages = [
            {"role": "system", "content": _CLUSTER_SYSTEM},
            {"role": "user", "content": user_msg},
        ]
        try:
            raw, usage = await self._model._stream_text(messages, component="风神", purpose="事件聚类")
            await self._model._record_primogem(
                "", "风神", usage, purpose="事件聚类",
            )
        except Exception as e:
            logger.warning("[风神·事件·聚类] LLM 异常 → 每条独立 new: {}", e)
            return fallback_groups

        try:
            data = json.loads(_strip_code_fence(raw))
            groups = data.get("groups")
            if not isinstance(groups, list) or not groups:
                raise ValueError("groups 缺失或空列表")
            recent_ids = {ev.id for ev in recent}
            normalized: list[dict[str, Any]] = []
            seen_idxs: set[int] = set()
            for g in groups:
                if not isinstance(g, dict):
                    continue
                indices_raw = g.get("item_indices") or []
                if not isinstance(indices_raw, list):
                    continue
                # 过滤越界、非 int、重复
                clean_idxs: list[int] = []
                for x in indices_raw:
                    try:
                        i = int(x)
                    except (TypeError, ValueError):
                        continue
                    if 0 <= i < n and i not in seen_idxs:
                        seen_idxs.add(i)
                        clean_idxs.append(i)
                if not clean_idxs:
                    continue
                merge_id = g.get("merge_with_event_id")
                if isinstance(merge_id, str) and merge_id and merge_id in recent_ids:
                    merge_target: str | None = merge_id
                else:
                    merge_target = None  # LLM 编造了不存在的 event_id → 强制新建
                normalized.append({
                    "item_indices": clean_idxs,
                    "merge_with_event_id": merge_target,
                })
            if not normalized:
                raise ValueError("解析后 groups 为空")
            return normalized
        except Exception as e:
            logger.warning(
                "[风神·事件·聚类] JSON 解析失败 → 每条独立 new: {} | raw[:200]={}",
                e, raw[:200],
            )
            return fallback_groups

    async def _llm_analyze(
        self, query: str, items: list[dict[str, Any]],
        base_event: "FeedEvent | None",
    ) -> dict:
        """事件分析 LLM。失败抛异常，由调用方走 _fallback_analysis 兜底。"""
        items_part = "\n".join(
            f"[{i}] title: {it.get('title', '')}"
            f"\n     url: {it.get('url', '')}"
            f"\n     desc: {_truncate(it.get('description', ''), MAX_DESC_LEN)}"
            for i, it in enumerate(items)
        )
        base_part = ""
        if base_event is not None:
            base_part = (
                "\n## 已有事件 base 摘要（merge 模式）\n"
                f"title: {base_event.title}\n"
                f"summary: {base_event.summary}\n"
                f"severity(旧): {base_event.severity}\n"
                f"sentiment_label(旧): {base_event.sentiment_label}\n"
                f"item_count(旧): {base_event.item_count}\n\n"
                "请在 base 基础上做「增量演进」，summary 突出「新发展」，"
                "不要从头复述。\n"
            )
        user_msg = (
            f"订阅关键词: {query}\n"
            f"{base_part}\n"
            f"## 本组条目（{len(items)} 条）\n"
            f"{items_part}\n"
        )
        messages = [
            {"role": "system", "content": _ANALYZE_SYSTEM},
            {"role": "user", "content": user_msg},
        ]
        raw, usage = await self._model._stream_text(messages, component="风神", purpose="事件分析")
        await self._model._record_primogem(
            "", "风神", usage, purpose="事件分析",
        )

        data = json.loads(_strip_code_fence(raw))
        # 字段校验 + 边界规范
        title = _truncate(str(data.get("title") or ""), MAX_TITLE_LEN)
        summary = _truncate(str(data.get("summary") or ""), MAX_SUMMARY_LEN)
        if not title:
            raise ValueError("title 为空")

        entities = data.get("entities") or []
        if not isinstance(entities, list):
            entities = []
        entities = [str(e)[:40] for e in entities[:8]]

        timeline = data.get("timeline") or []
        if not isinstance(timeline, list):
            timeline = []
        norm_timeline: list[dict] = []
        for tl in timeline[:5]:
            if not isinstance(tl, dict):
                continue
            try:
                ts = float(tl.get("ts") or 0)
            except (TypeError, ValueError):
                ts = 0.0
            point = _truncate(str(tl.get("point") or ""), 100)
            if point:
                norm_timeline.append({"ts": ts, "point": point})

        severity = str(data.get("severity") or "p3").lower().strip()
        if severity not in _VALID_SEVERITY:
            severity = "p3"

        try:
            score = float(data.get("sentiment_score") or 0.0)
        except (TypeError, ValueError):
            score = 0.0
        score = max(-1.0, min(1.0, score))

        label = str(data.get("sentiment_label") or "neutral").lower().strip()
        if label not in _VALID_SENTIMENT_LABEL:
            label = "neutral"

        return {
            "title": title,
            "summary": summary,
            "entities": entities,
            "timeline": norm_timeline,
            "severity": severity,
            "sentiment_score": score,
            "sentiment_label": label,
        }

    @staticmethod
    def _fallback_analysis(
        items: list[dict[str, Any]],
        base_event: "FeedEvent | None",
    ) -> dict:
        """LLM 失败 / JSON 解析失败时的模板事件，severity=p3、neutral。"""
        first = items[0] if items else {}
        title = _truncate(
            str(first.get("title") or "（无标题）"),
            MAX_TITLE_LEN,
        )
        summary = _truncate(
            str(first.get("description") or first.get("title") or ""),
            MAX_SUMMARY_LEN,
        )
        if base_event is not None:
            # merge 兜底：保留 base 字段，仅在 summary 后追加"+ N 条新报道"
            return {
                "title": base_event.title,
                "summary": _truncate(
                    f"{base_event.summary}（+{len(items)} 条新报道）",
                    MAX_SUMMARY_LEN,
                ),
                "entities": base_event.entities,
                "timeline": base_event.timeline,
                "severity": base_event.severity,
                "sentiment_score": base_event.sentiment_score,
                "sentiment_label": base_event.sentiment_label,
            }
        return {
            "title": title,
            "summary": summary,
            "entities": [],
            "timeline": [],
            "severity": "p3",
            "sentiment_score": 0.0,
            "sentiment_label": "neutral",
        }
