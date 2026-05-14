"""风神 · 日报组装 mixin：_compose_digest（业务订阅 light 版）+ fallback。"""
from __future__ import annotations

import asyncio
import json
from typing import TYPE_CHECKING

from loguru import logger

from ._models import (
    _DIGEST_PROMPT,
    _build_fallback_digest,
)

if TYPE_CHECKING:
    from paimon.llm.model import Model


class _DigestMixin:
    """日报组装方法集合（业务订阅 light 版用，岩神 stock_watch 等复用）。"""

    async def _compose_digest(
        self, query: str, items: list[dict], model: Model,
        *, component: str, purpose: str,
    ) -> str:
        """浅池 LLM 写日报；失败降级到模板。

        component / purpose 由调用方传入，标识真实业务方（不是默认风神）。
        例如岩神 stock_watch 调用时传 ("岩神", "关注股日报")。
        """
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
            raw, usage = await model._stream_text(
                messages, component=component, purpose=purpose,
            )
            await model._record_primogem("", component, usage, purpose=purpose)
        except Exception as e:
            logger.warning("[{}·{}] LLM 日报失败，降级模板: {}", component, purpose, e)
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
