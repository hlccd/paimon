"""Bing 引擎（cn.bing.com，国内直连）。

解析思路参考 open-webSearch 的 bing/parser.ts，但用 BeautifulSoup 独立实现：
  结果容器：ol#b_results 下的 li.b_algo
  - 标题：h2 a（含 href）
  - 描述：.b_caption p 或 .b_lineclamp*
  - 子链接 / 卡片类结果（.b_ans / .b_ad）忽略，只要主结果
"""
from __future__ import annotations

import os
from typing import Any

import httpx
from bs4 import BeautifulSoup

# 浏览器级 UA；cn.bing 对 headless UA 敏感
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/133.0.0.0 Safari/537.36"
    ),
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;q=0.9,"
        "image/avif,image/webp,image/apng,*/*;q=0.8"
    ),
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Upgrade-Insecure-Requests": "1",
    "Cache-Control": "no-cache",
}

_BASE = "https://cn.bing.com/search"

# 强信号机器人验证关键词（只保留不会在正常搜索结果里出现的）
# 移除了 "access denied" / "too many requests" / "blocked" 这类可能出现在
# 普通结果标题/描述里的弱信号词，避免假阳性。
_BOT_KEYWORDS = (
    "captcha",
    "verify you are human",
    "人机验证",
    "验证码",
    "请完成安全验证",
)


def _is_bot_page(html: str) -> bool:
    """判断是否机器人验证页。

    机器人验证页通常**很短**（<30KB）且含强信号关键词。搜索结果页
    通常 >80KB。对"长页面恰好含 captcha 字样"的情况不误判。
    """
    if len(html) > 30_000:
        return False
    low = html.lower()
    return any(k in low for k in _BOT_KEYWORDS)


async def search(query: str, limit: int) -> list[dict[str, Any]]:
    """返回最多 `limit` 条结果。单次 GET，不内部重试。"""
    if not query.strip():
        return []

    params = {
        "q": query,
        "count": max(limit, 10),  # Bing 对小 count 响应不稳定，拉多一些再截断
        "FORM": "QBLH",
    }

    async with httpx.AsyncClient(
        headers=_HEADERS, timeout=15.0, follow_redirects=True,
    ) as client:
        resp = await client.get(_BASE, params=params)
        resp.raise_for_status()
        html = resp.text

    if os.getenv("WEBSEARCH_DEBUG"):
        print(f"[bing] HTTP {resp.status_code} len={len(html)}", flush=True)

    if _is_bot_page(html):
        raise RuntimeError("bing 命中反爬（captcha/验证码）")

    soup = BeautifulSoup(html, "lxml")
    results: list[dict[str, Any]] = []

    for item in soup.select("li.b_algo"):
        title_a = item.select_one("h2 a")
        if not title_a:
            continue
        url = (title_a.get("href") or "").strip()
        if not url.startswith(("http://", "https://")):
            continue
        title = title_a.get_text(strip=True)
        if not title:
            continue

        # 描述：优先 .b_caption p，其次 .b_lineclamp, 再其次 dd
        desc_el = (
            item.select_one(".b_caption p")
            or item.select_one("[class*='b_lineclamp']")
            or item.select_one("dd")
        )
        description = desc_el.get_text(" ", strip=True) if desc_el else ""

        results.append({
            "title": title,
            "url": url,
            "description": description,
            "engine": "bing",
        })
        if len(results) >= limit:
            break

    if os.getenv("WEBSEARCH_DEBUG"):
        print(f"[bing] parsed {len(results)} results", flush=True)

    return results
