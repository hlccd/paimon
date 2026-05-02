"""风神 · 日报组装 mixin：传统 _compose_digest + 事件级 _compose_event_digest + 兼容 helper。"""
from __future__ import annotations

import asyncio
import json
import time
from typing import TYPE_CHECKING

from loguru import logger

from ._models import (
    _DIGEST_PROMPT,
    _DIGEST_RETRY_DELAYS,
    _EVENT_DIGEST_PROMPT,
    _build_event_fallback_digest,
    _build_fallback_digest,
)

if TYPE_CHECKING:
    from paimon.foundation.irminsul.subscription import Subscription
    from paimon.llm.model import Model


class _DigestMixin:
    """日报组装方法集合（传统模式 + L1 事件模式）。"""

    async def _compose_digest(
        self, query: str, items: list[dict], model: Model,
    ) -> str:
        """浅池 LLM 写早报；失败降级到模板。"""
        system = _DIGEST_PROMPT.format(query=query, n=len(items))
        # 给 LLM 的条目裁剪 description，避免过长
        trimmed = [
            {
                "title": it.get("title", "")[:200],
                "url": it.get("url", ""),
                "description": it.get("description", "")[:400],
                "engine": it.get("engine", ""),
            }
            for it in items
        ]
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": json.dumps(trimmed, ensure_ascii=False)},
        ]
        try:
            raw, usage = await model._stream_text(messages, component="风神", purpose="订阅早报")
            await model._record_primogem(
                "", "风神", usage, purpose="订阅早报",
            )
        except Exception as e:
            logger.warning("[风神·订阅] LLM 早报失败，降级模板: {}", e)
            return _build_fallback_digest(query, items)

        text = raw.strip()
        # 清理可能的 code fence
        if text.startswith("```"):
            lines = text.splitlines()
            if len(lines) >= 2 and lines[-1].strip() == "```":
                text = "\n".join(lines[1:-1]).strip()
        if not text:
            return _build_fallback_digest(query, items)
        return text

    @staticmethod
    def _feed_event_to_processed(
        ev: "FeedEvent", first_url: str, day_start: float,
    ) -> "ProcessedEvent":
        """把 feed_events 表中的事件转成 ProcessedEvent，喂给日报合成。

        累计模式（dedup_per_day 用）下不知道「本批次」是哪批，所以：
        - is_new = first_seen_at 是否落在今日窗口内
        - severity_changed / base_severity 缺失（设默认值），LLM prompt 里这两
          字段是参考性的，缺失只是损失一点叙述深度，不影响推送决策
        - first_url 由调用方传入（取该事件今日 feed_items 里第一条 url）
        """
        from paimon.archons.venti_event import ProcessedEvent
        return ProcessedEvent(
            event_id=ev.id,
            severity=ev.severity,
            base_severity="",
            is_new=ev.first_seen_at >= day_start,
            severity_changed=False,
            title=ev.title,
            summary=ev.summary,
            first_url=first_url or "",
            item_count=ev.item_count,
            sentiment_label=ev.sentiment_label,
            sentiment_score=ev.sentiment_score,
            last_seen_at=ev.last_seen_at,
            timeline=ev.timeline or [],
        )

    async def _compose_event_digest(
        self, query: str, processed_events: list, model: Model,
    ) -> str:
        """阶段 C 事件型日报。

        把本批次 ProcessedEvents 给 LLM，按 severity 分区组织成 markdown。
        LLM 调用按 _DIGEST_RETRY_DELAYS 重试；用尽后走 P0+P1 兜底模板。
        """
        if not processed_events:
            # 不应该到这里——调用方应已判过；保险返个空提示
            return f"**风神·订阅日报【{query}】** 本次无新事件。"

        import time as _time
        # 给 LLM 的事件结构（裁剪冗长字段；last_seen_at / timeline 给时效过滤用）
        events_payload = [
            {
                "title": (ev.title or "")[:80],
                "summary": (ev.summary or "")[:200],
                "severity": ev.severity,
                "sentiment_label": ev.sentiment_label,
                "sentiment_score": round(ev.sentiment_score, 2),
                "first_url": ev.first_url or "",
                "is_new": ev.is_new,
                "severity_changed": ev.severity_changed,
                "base_severity": ev.base_severity,
                "item_count": ev.item_count,
                "last_seen_at": _time.strftime(
                    "%Y-%m-%d %H:%M",
                    _time.localtime(ev.last_seen_at),
                ) if ev.last_seen_at else "",
                "timeline": ev.timeline or [],
            }
            for ev in processed_events
        ]
        today_date = _time.strftime("%Y-%m-%d", _time.localtime())
        system = _EVENT_DIGEST_PROMPT.format(
            query=query, n=len(processed_events),
            today_date=today_date,
        )
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": json.dumps(events_payload, ensure_ascii=False)},
        ]

        total_attempts = len(_DIGEST_RETRY_DELAYS) + 1
        last_err: Exception | str | None = None
        for attempt in range(total_attempts):
            try:
                raw, usage = await model._stream_text(messages, component="风神", purpose="事件日报")
                await model._record_primogem(
                    "", "风神", usage, purpose="事件日报",
                )
                text = (raw or "").strip()
                # 剥可能的 code fence（analysis prompt 已强约束，但兜一道）
                if text.startswith("```"):
                    lines_ = text.splitlines()
                    if len(lines_) >= 2 and lines_[-1].strip() == "```":
                        text = "\n".join(lines_[1:-1]).strip()
                if text:
                    if attempt > 0:
                        logger.info(
                            "[风神·订阅] 事件型日报 LLM 第 {}/{} 次重试成功",
                            attempt + 1, total_attempts,
                        )
                    return text
                # 空内容也按失败处理，可能是流被截或 prompt 触发拒答
                last_err = "LLM 返回空内容"
            except Exception as e:
                last_err = e

            if attempt + 1 < total_attempts:
                wait = _DIGEST_RETRY_DELAYS[attempt]
                logger.warning(
                    "[风神·订阅] 事件型日报 LLM 第 {}/{} 次失败: {}（{}s 后重试）",
                    attempt + 1, total_attempts, last_err, int(wait),
                )
                await asyncio.sleep(wait)
            else:
                logger.warning(
                    "[风神·订阅] 事件型日报 LLM 第 {}/{} 次失败: {}（重试用尽，降级 P0+P1 模板）",
                    attempt + 1, total_attempts, last_err,
                )

        return _build_event_fallback_digest(query, processed_events)
