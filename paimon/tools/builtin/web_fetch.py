"""web_fetch — 网页抓取工具（风神用）

抓取 URL 内容，返回纯文本。
"""
from __future__ import annotations

import re
from typing import Any

from paimon.tools.base import BaseTool, ToolContext

MAX_LENGTH = 20000


class WebFetchTool(BaseTool):
    name = "web_fetch"
    description = (
        "网页内容抓取工具。输入 URL，返回网页的纯文本内容。"
        "适合抓取新闻、文章、搜索结果等。"
    )
    parameters = {
        "type": "object",
        "properties": {
            "url": {
                "type": "string",
                "description": "要抓取的 URL",
            },
            "max_length": {
                "type": "integer",
                "description": "最大返回字符数，默认 20000",
                "default": 20000,
            },
        },
        "required": ["url"],
    }

    async def execute(self, ctx: ToolContext, **kwargs: Any) -> str:
        import httpx

        url = kwargs.get("url", "")
        max_len = kwargs.get("max_length", MAX_LENGTH)

        if not url:
            return "缺少 url 参数"
        if not url.startswith(("http://", "https://")):
            return "URL 必须以 http:// 或 https:// 开头"

        try:
            async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
                resp = await client.get(url, headers={
                    "User-Agent": "Mozilla/5.0 (compatible; Paimon/1.0)",
                })
                resp.raise_for_status()
                html = resp.text
        except httpx.HTTPStatusError as e:
            return f"HTTP 错误 {e.response.status_code}: {url}"
        except httpx.RequestError as e:
            return f"请求失败: {e}"

        text = self._html_to_text(html)

        if len(text) > max_len:
            text = text[:max_len] + f"\n\n... (截断，共 {len(text)} 字符)"

        return text

    @staticmethod
    def _html_to_text(html: str) -> str:
        text = re.sub(r'<script[^>]*>.*?</script>', '', html, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r'<style[^>]*>.*?</style>', '', text, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r'<[^>]+>', ' ', text)
        text = re.sub(r'&nbsp;', ' ', text)
        text = re.sub(r'&lt;', '<', text)
        text = re.sub(r'&gt;', '>', text)
        text = re.sub(r'&amp;', '&', text)
        text = re.sub(r'&#\d+;', '', text)
        text = re.sub(r'\s+', ' ', text)
        lines = [line.strip() for line in text.split('\n') if line.strip()]
        return '\n'.join(lines)
