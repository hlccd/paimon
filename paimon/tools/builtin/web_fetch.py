"""web_fetch — 网页抓取工具（风神用）

抓取 URL 内容，返回纯文本。UA 仿真 Chrome 桌面浏览器，绕过基础反爬。
"""
from __future__ import annotations

from typing import Any

from paimon.tools.base import BaseTool, ToolContext

MAX_LENGTH = 20000

# 真实 Chrome 桌面 UA + Accept-Language（参考 fairy/skills/web/web.py）
# 默认 Paimon/1.0 的 UA 会被小红书等站点直接拦截，这里仿真浏览器
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7",
}


class WebFetchTool(BaseTool):
    name = "web_fetch"
    description = (
        "网页内容抓取工具。输入 URL，返回网页的纯文本正文（已剥离脚本/样式/导航/页脚）。"
        "适合抓取新闻、文章、小红书/B站等内容页。"
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
            "raw": {
                "type": "boolean",
                "description": "是否返回原始 HTML（默认 false，返回正文）。需要从页面正则提取视频直链等场景请设为 true",
                "default": False,
            },
        },
        "required": ["url"],
    }

    async def execute(self, ctx: ToolContext, **kwargs: Any) -> str:
        import httpx

        url = kwargs.get("url", "")
        max_len = kwargs.get("max_length", MAX_LENGTH)
        raw = kwargs.get("raw", False)

        if not url:
            return "缺少 url 参数"
        if not url.startswith(("http://", "https://")):
            return "URL 必须以 http:// 或 https:// 开头"

        try:
            async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
                resp = await client.get(url, headers=_HEADERS)
                resp.raise_for_status()
                html = resp.text
        except httpx.HTTPStatusError as e:
            return f"HTTP 错误 {e.response.status_code}: {url}"
        except httpx.RequestError as e:
            return f"请求失败: {e}"

        content = html if raw else self._extract_text(html)

        if len(content) > max_len:
            content = content[:max_len] + f"\n\n... (截断，共 {len(content)} 字符)"

        return content

    @staticmethod
    def _extract_text(html: str) -> str:
        """用 bs4 提正文：剥脚本/样式/导航；优先 article/main 区域。"""
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, "html.parser")
        for tag in soup(["script", "style", "nav", "footer", "header", "aside", "noscript"]):
            tag.decompose()
        target = soup.select_one("article") or soup.select_one("main") or soup.body or soup
        text = target.get_text(separator="\n", strip=True)
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        body = "\n".join(lines)
        title = soup.title.get_text(strip=True) if soup.title else ""
        return f"# {title}\n\n{body}" if title else body
