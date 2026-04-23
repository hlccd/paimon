"""百度引擎（www.baidu.com/s）。

解析思路参考 open-webSearch 的 baidu.ts，但用 BeautifulSoup 独立实现：
  结果容器：#content_left 下的直接子元素（每个子 div 对应一条结果）
  - 标题：h3 文本
  - URL：子元素下第一个 href 以 http(s) 开头的 <a>（百度真链是跳转，暂不解
        跳转，保留 baidu.com 的 redirect URL；LLM 点开会自动跳）
  - 描述：.cos-row 或 .c-font-normal.c-color-text 或 .c-abstract（版本差异大，多级兜底）

百度的反爬策略：
  - 参数漂移（rsv_pq / rsv_t 等），这里只传最稳定的几个核心参数
  - UA 伪装为 Chrome on Win10
  - 某些 IP 段会被要求人机验证；命中时抛异常让调用方降级
"""
from __future__ import annotations

import os
from typing import Any

import httpx
from bs4 import BeautifulSoup

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Referer": "https://www.baidu.com/",
    "Upgrade-Insecure-Requests": "1",
}

_BASE = "https://www.baidu.com/s"

_BOT_KEYWORDS = (
    "百度安全验证",
    "verify.baidu.com",
    "wappass.baidu.com/static/captcha",
    "请完成安全验证",
    "人机验证",
)


def _is_bot_page(html: str) -> bool:
    return any(k in html for k in _BOT_KEYWORDS)


async def search(query: str, limit: int) -> list[dict[str, Any]]:
    if not query.strip():
        return []

    params = {
        "wd": query,
        "pn": "0",        # 从第 0 条开始
        "rn": str(max(limit, 10)),  # request number
        "ie": "utf-8",
        "tn": "baidu",
    }

    async with httpx.AsyncClient(
        headers=_HEADERS, timeout=15.0, follow_redirects=True,
    ) as client:
        resp = await client.get(_BASE, params=params)
        resp.raise_for_status()
        # 百度偶尔 200 但返回验证页，下面 is_bot_page 拦
        html = resp.text

    if os.getenv("WEBSEARCH_DEBUG"):
        print(f"[baidu] HTTP {resp.status_code} len={len(html)}", flush=True)

    if _is_bot_page(html):
        raise RuntimeError("baidu 命中反爬（安全验证）")

    soup = BeautifulSoup(html, "lxml")
    results: list[dict[str, Any]] = []

    container = soup.select_one("#content_left")
    if not container:
        return []

    # 百度结果是 #content_left 下的直接子元素（含 .result / .result-op 等）
    for item in container.find_all(recursive=False):
        h3 = item.find("h3")
        if not h3:
            continue
        # 标题的 <a>
        title_a = h3.find("a")
        if not title_a:
            continue
        url = (title_a.get("href") or "").strip()
        if not url.startswith(("http://", "https://")):
            continue
        title = title_a.get_text(" ", strip=True)
        if not title:
            continue

        # 描述：多级兜底（百度版本差异大）
        desc_el = (
            item.select_one(".cos-row")
            or item.select_one(".c-font-normal.c-color-text")
            or item.select_one(".c-abstract")
            or item.select_one("[class*='abstract']")
            or item.select_one("[class*='content-right']")
        )
        description = desc_el.get_text(" ", strip=True) if desc_el else ""

        results.append({
            "title": title,
            "url": url,          # 百度是跳转 URL，点开后自动 302 到真 URL
            "description": description,
            "engine": "baidu",
        })
        if len(results) >= limit:
            break

    if os.getenv("WEBSEARCH_DEBUG"):
        print(f"[baidu] parsed {len(results)} results", flush=True)

    return results
