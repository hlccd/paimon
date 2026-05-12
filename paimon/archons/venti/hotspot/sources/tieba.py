"""百度热搜 collector：top.baidu.com/board?tab=realtime（cookies 用 baidu/tieba 域）。

注：贴吧本身没有"全站热榜"，最贴近"中文舆论代表"的是百度热搜实时榜。
百度热搜支持匿名访问；为通用性，若 baidu cookies 存在则带上（可避免风控限流）。
"""
from __future__ import annotations

import re

from loguru import logger

from paimon.foundation.site_cookies import cookies_exists, cookies_path

from .._models import CollectResult, HotItem


_URL = "https://top.baidu.com/board?tab=realtime"
_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)


def _parse_hot(text: str) -> int:
    t = (text or "").strip()
    m = re.search(r"([\d.]+)", t)
    return int(float(m.group(1))) if m else 0


async def collect(limit: int = 30) -> CollectResult:
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        return CollectResult(source="tieba", items=[], error="playwright not installed")

    storage_state = (
        str(cookies_path("baidu")) if cookies_exists("baidu")
        else (str(cookies_path("tieba")) if cookies_exists("tieba") else None)
    )
    items: list[HotItem] = []
    try:
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=True)
            try:
                ctx_kwargs = {"user_agent": _UA}
                if storage_state:
                    ctx_kwargs["storage_state"] = storage_state
                ctx = await browser.new_context(**ctx_kwargs)
                page = await ctx.new_page()
                await page.goto(_URL, wait_until="domcontentloaded", timeout=20000)
                # 百度热搜 DOM：每条 .category-wrap_iQLoo 或 [class*="category-wrap"]
                # 标题 .c-single-text-ellipsis；链接外层 a
                try:
                    await page.wait_for_selector('[class*="category-wrap"]', timeout=10000)
                except Exception:
                    pass
                rows = await page.query_selector_all('[class*="category-wrap"]')
                rank_seen = 0
                for row in rows:
                    if rank_seen >= limit:
                        break
                    title_el = await row.query_selector('[class*="c-single-text-ellipsis"]')
                    if not title_el:
                        continue
                    title = (await title_el.inner_text() or "").strip()
                    if not title:
                        continue
                    a = await row.query_selector("a")
                    href = (await a.get_attribute("href") or "") if a else ""
                    full_url = href if href.startswith("http") else (
                        f"https://top.baidu.com{href}" if href else _URL
                    )
                    hot_el = await row.query_selector('[class*="hot-index"]')
                    hot_text = (await hot_el.inner_text() or "").strip() if hot_el else ""
                    rank_seen += 1
                    items.append(HotItem(
                        source="tieba", rank=rank_seen, title=title,
                        url=full_url, hot_value=_parse_hot(hot_text),
                        extra={"hot_text": hot_text},
                    ))
            finally:
                await browser.close()
        if not items:
            return CollectResult(source="tieba", items=[], error="no_data (selector miss)")
        logger.info("[hotspot·tieba/baidu热搜] 拉到 {} 条", len(items))
        return CollectResult(source="tieba", items=items)
    except Exception as e:
        logger.warning("[hotspot·tieba/baidu热搜] 失败: {}", e)
        return CollectResult(source="tieba", items=[], error=str(e)[:120])
