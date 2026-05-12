"""小红书热点 collector：playwright + cookies + explore 页 DOM。

小红书没公开"全站热榜"API。explore 页 (xiaohongshu.com/explore) 的"发现"流是
个人化推荐，作为"用户感兴趣的热门内容"近似可用。也尝试 hot-list 接口（若可用）。

DOM 不稳定，首跑可能 0 条；失败时记 sources_fail 让 LLM 在剩余源上综合。
"""
from __future__ import annotations

import re

from loguru import logger

from paimon.foundation.site_cookies import cookies_exists, cookies_path

from .._models import CollectResult, HotItem


_EXPLORE_URL = "https://www.xiaohongshu.com/explore"
_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)


def _parse_int(text: str) -> int:
    t = (text or "").strip()
    m = re.search(r"([\d.]+)\s*([万Ww]?)", t)
    if not m:
        return 0
    try:
        num = float(m.group(1))
    except ValueError:
        return 0
    return int(num * 10000) if m.group(2).lower() in ("万", "w") else int(num)


async def collect(limit: int = 30) -> CollectResult:
    if not cookies_exists("xhs"):
        return CollectResult(source="xhs", items=[], error="missing_cookies")

    try:
        from playwright.async_api import async_playwright
    except ImportError:
        return CollectResult(source="xhs", items=[], error="playwright not installed")

    storage_state = str(cookies_path("xhs"))
    items: list[HotItem] = []
    try:
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=True)
            try:
                ctx = await browser.new_context(user_agent=_UA, storage_state=storage_state)
                page = await ctx.new_page()
                await page.goto(_EXPLORE_URL, wait_until="domcontentloaded", timeout=20000)
                # 等待瀑布流卡片渲染
                try:
                    await page.wait_for_selector("section.note-item", timeout=10000)
                except Exception:
                    pass
                cards = await page.query_selector_all("section.note-item")
                rank_seen = 0
                for c in cards:
                    if rank_seen >= limit:
                        break
                    a = await c.query_selector("a.cover")
                    if not a:
                        a = await c.query_selector("a")
                    if not a:
                        continue
                    href = await a.get_attribute("href") or ""
                    if not href:
                        continue
                    title_el = (
                        await c.query_selector(".title span")
                        or await c.query_selector("a.title")
                        or await c.query_selector(".footer .title")
                    )
                    title = ""
                    if title_el:
                        title = (await title_el.inner_text() or "").strip()
                    if not title:
                        continue
                    # 点赞数（.like-wrapper .count 或类似）
                    like_el = await c.query_selector(".like-wrapper .count, .like .count")
                    like_text = ""
                    if like_el:
                        like_text = (await like_el.inner_text() or "").strip()
                    full_url = (
                        f"https://www.xiaohongshu.com{href}" if href.startswith("/")
                        else href
                    )
                    rank_seen += 1
                    items.append(HotItem(
                        source="xhs", rank=rank_seen, title=title,
                        url=full_url, hot_value=_parse_int(like_text),
                        extra={"like_text": like_text},
                    ))
            finally:
                await browser.close()
        if not items:
            return CollectResult(source="xhs", items=[], error="no_data (selector miss)")
        logger.info("[hotspot·xhs] 拉到 {} 条", len(items))
        return CollectResult(source="xhs", items=items)
    except Exception as e:
        logger.warning("[hotspot·xhs] 失败: {}", e)
        return CollectResult(source="xhs", items=[], error=str(e)[:120])
