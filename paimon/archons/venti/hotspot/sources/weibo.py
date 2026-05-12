"""微博热搜 collector：playwright + cookies + s.weibo.com/top/summary DOM。

热搜页 DOM 结构（容易变；首跑空时自动 dump 诊断）：
- `tbody tr` 每条；
- `.td-02 a` 标签里 a.text + a.href（href 是 /weibo?q=%23xxx 形式）；
- `.td-02 span` 是热度数字（如 "150.2万"）。
"""
from __future__ import annotations

import re
from urllib.parse import unquote

from loguru import logger

from paimon.foundation.site_cookies import cookies_exists, cookies_path

from .._models import CollectResult, HotItem


_URL = "https://s.weibo.com/top/summary"
_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)


def _parse_hot(text: str) -> int:
    t = (text or "").strip()
    m = re.search(r"([\d.]+)\s*万", t)
    if m:
        try:
            return int(float(m.group(1)) * 10000)
        except ValueError:
            return 0
    m = re.search(r"(\d+)", t)
    return int(m.group(1)) if m else 0


async def collect(limit: int = 30) -> CollectResult:
    if not cookies_exists("weibo"):
        return CollectResult(source="weibo", items=[], error="missing_cookies")

    try:
        from playwright.async_api import async_playwright
    except ImportError:
        return CollectResult(source="weibo", items=[], error="playwright not installed")

    storage_state = str(cookies_path("weibo"))
    items: list[HotItem] = []
    try:
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=True)
            try:
                ctx = await browser.new_context(user_agent=_UA, storage_state=storage_state)
                page = await ctx.new_page()
                await page.goto(_URL, wait_until="domcontentloaded", timeout=20000)
                # 等待热搜表格渲染
                try:
                    await page.wait_for_selector("tbody tr .td-02", timeout=8000)
                except Exception:
                    pass
                rows = await page.query_selector_all("tbody tr")
                rank_seen = 0
                for row in rows:
                    if rank_seen >= limit:
                        break
                    a = await row.query_selector(".td-02 a")
                    if not a:
                        continue
                    title = (await a.inner_text() or "").strip()
                    href = await a.get_attribute("href") or ""
                    if not title or not href:
                        continue
                    # 拿热度数字（td-02 下的 span）
                    span = await row.query_selector(".td-02 span")
                    hot_text = ""
                    if span:
                        hot_text = (await span.inner_text() or "").strip()
                    full_url = (
                        f"https://s.weibo.com{href}" if href.startswith("/") else href
                    )
                    rank_seen += 1
                    items.append(HotItem(
                        source="weibo", rank=rank_seen, title=title,
                        url=full_url, hot_value=_parse_hot(hot_text),
                        extra={"hot_text": hot_text},
                    ))
            finally:
                await browser.close()
        if not items:
            return CollectResult(source="weibo", items=[], error="no_data (selector miss?)")
        logger.info("[hotspot·weibo] 拉到 {} 条", len(items))
        return CollectResult(source="weibo", items=items)
    except Exception as e:
        logger.warning("[hotspot·weibo] 失败: {}", e)
        return CollectResult(source="weibo", items=[], error=str(e)[:120])
