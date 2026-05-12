"""知乎热榜 collector：hot-lists API + cookies。

API: https://www.zhihu.com/api/v3/feed/topstory/hot-lists/total?limit=50&desktop=true
返回 data[].target.{title, url}, data[].detail_text
"""
from __future__ import annotations

import aiohttp
from loguru import logger

from paimon.foundation.site_cookies import cookies_exists, load_storage_state

from .._models import CollectResult, HotItem


_API = "https://www.zhihu.com/api/v3/feed/topstory/hot-lists/total"
_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)


def _build_cookie_header() -> str | None:
    """从 playwright storage_state 拼 Cookie header。"""
    if not cookies_exists("zhihu"):
        return None
    try:
        ss = load_storage_state("zhihu")
        cookies = ss.get("cookies", []) or []
        return "; ".join(f"{c['name']}={c['value']}" for c in cookies if c.get("name"))
    except Exception:
        return None


async def collect(limit: int = 30) -> CollectResult:
    cookie_hdr = _build_cookie_header()
    if not cookie_hdr:
        return CollectResult(source="zhihu", items=[], error="missing_cookies")

    headers = {
        "User-Agent": _UA,
        "Referer": "https://www.zhihu.com/hot",
        "Cookie": cookie_hdr,
        "x-requested-with": "fetch",
        # 知乎默认返 brotli 压缩；aiohttp 没装 brotli 库会 "Can not decode content-encoding"
        # 只接受 gzip/deflate（aiohttp 内置支持）
        "Accept-Encoding": "gzip, deflate",
    }
    timeout = aiohttp.ClientTimeout(total=15)
    try:
        async with aiohttp.ClientSession(headers=headers, timeout=timeout) as sess:
            async with sess.get(_API, params={"limit": max(limit, 50), "desktop": "true"}) as r:
                if r.status != 200:
                    return CollectResult(source="zhihu", items=[], error=f"http {r.status}")
                data = await r.json()
        items: list[HotItem] = []
        for i, hit in enumerate(data.get("data", [])[:limit], 1):
            target = hit.get("target") or {}
            title = (target.get("title") or "").strip()
            qid = target.get("id") or ""
            url = f"https://www.zhihu.com/question/{qid}" if qid else (target.get("url") or "")
            # detail_text 通常是"X 万热度"
            detail = (hit.get("detail_text") or "").strip()
            hot_value = _parse_hot(detail)
            if not title:
                continue
            items.append(HotItem(
                source="zhihu", rank=i, title=title, url=url, hot_value=hot_value,
                extra={"detail": detail},
            ))
        logger.info("[hotspot·zhihu] 拉到 {} 条", len(items))
        return CollectResult(source="zhihu", items=items)
    except Exception as e:
        logger.warning("[hotspot·zhihu] 失败: {}", e)
        return CollectResult(source="zhihu", items=[], error=str(e)[:120])


def _parse_hot(text: str) -> int:
    """ "1234.5 万热度" → 12345000；纯数字 → int"""
    import re
    if not text:
        return 0
    m = re.search(r"([\d.]+)\s*万", text)
    if m:
        try:
            return int(float(m.group(1)) * 10000)
        except ValueError:
            return 0
    m = re.search(r"(\d+)", text)
    return int(m.group(1)) if m else 0
