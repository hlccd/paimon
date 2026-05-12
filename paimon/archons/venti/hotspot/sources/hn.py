"""HackerNews 热榜 collector：firebase API（免登录）。

topstories.json → 前 N 个 story id → /v0/item/{id}.json 并发拿详情。
"""
from __future__ import annotations

import asyncio

import aiohttp
from loguru import logger

from .._models import CollectResult, HotItem


_API_TOP = "https://hacker-news.firebaseio.com/v0/topstories.json"
_API_ITEM = "https://hacker-news.firebaseio.com/v0/item/{}.json"


async def collect(limit: int = 30) -> CollectResult:
    timeout = aiohttp.ClientTimeout(total=20)
    try:
        async with aiohttp.ClientSession(timeout=timeout) as sess:
            async with sess.get(_API_TOP) as r:
                ids = await r.json()
            if not ids:
                return CollectResult(source="hn", items=[], error="topstories empty")
            wanted = ids[:limit]
            tasks = [sess.get(_API_ITEM.format(sid)) for sid in wanted]
            details = []
            for resp in await asyncio.gather(*tasks, return_exceptions=True):
                if isinstance(resp, Exception):
                    continue
                async with resp:
                    try:
                        d = await resp.json()
                        if d:
                            details.append(d)
                    except Exception:
                        pass
        items: list[HotItem] = []
        for i, d in enumerate(details[:limit], 1):
            title = (d.get("title") or "").strip()
            url = d.get("url") or f"https://news.ycombinator.com/item?id={d.get('id')}"
            score = int(d.get("score") or 0)
            if not title:
                continue
            items.append(HotItem(
                source="hn", rank=i, title=title, url=url, hot_value=score,
                extra={"by": d.get("by", ""), "descendants": d.get("descendants") or 0},
            ))
        logger.info("[hotspot·hn] 拉到 {} 条", len(items))
        return CollectResult(source="hn", items=items)
    except Exception as e:
        logger.warning("[hotspot·hn] 失败: {}", e)
        return CollectResult(source="hn", items=[], error=str(e)[:120])
