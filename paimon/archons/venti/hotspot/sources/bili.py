"""B 站热榜 collector：popular API（免登录）。

API: https://api.bilibili.com/x/web-interface/popular?ps=30&pn=1
返回 data.list[].{bvid, title, stat.view, owner.name, ...}
"""
from __future__ import annotations

import aiohttp
from loguru import logger

from .._models import CollectResult, HotItem


_API = "https://api.bilibili.com/x/web-interface/popular"
_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)


async def collect(limit: int = 30) -> CollectResult:
    headers = {"User-Agent": _UA, "Referer": "https://www.bilibili.com/"}
    timeout = aiohttp.ClientTimeout(total=15)
    try:
        async with aiohttp.ClientSession(headers=headers, timeout=timeout) as sess:
            async with sess.get(_API, params={"ps": limit, "pn": 1}) as r:
                data = await r.json()
        if data.get("code") != 0:
            return CollectResult(source="bili", items=[], error=f"api code={data.get('code')}")
        items: list[HotItem] = []
        for i, it in enumerate(data.get("data", {}).get("list", [])[:limit], 1):
            bvid = it.get("bvid", "")
            title = (it.get("title") or "").strip()
            view = (it.get("stat") or {}).get("view") or 0
            if not bvid or not title:
                continue
            items.append(HotItem(
                source="bili", rank=i, title=title,
                url=f"https://www.bilibili.com/video/{bvid}",
                hot_value=int(view),
                extra={"author": (it.get("owner") or {}).get("name", "")},
            ))
        logger.info("[hotspot·bili] 拉到 {} 条", len(items))
        return CollectResult(source="bili", items=items)
    except Exception as e:
        logger.warning("[hotspot·bili] 失败: {}", e)
        return CollectResult(source="bili", items=[], error=str(e)[:120])
