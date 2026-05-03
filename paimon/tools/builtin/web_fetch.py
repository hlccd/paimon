"""web_fetch — 网页抓取工具（风神用）

抓取 URL 内容，返回纯文本。UA 仿真 Chrome 桌面浏览器，绕过基础反爬。

SEC-004 SSRF 防护：
- 只允许 http/https 协议
- DNS 解析后检查 IP 是否在私有/loopback/链路本地/保留段，命中即拒绝
- httpx event hook 在每次 redirect 时重新校验目标 URL（防 redirect 到内网）
"""
from __future__ import annotations

import ipaddress
import socket
from typing import Any
from urllib.parse import urlparse

from paimon.tools.base import BaseTool, ToolContext

MAX_LENGTH = 20000

# 真实 Chrome 桌面 UA + Accept-Language
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


def _is_blocked_ip(ip_str: str) -> bool:
    """判定 IP 是否在禁止段：私有/loopback/链路本地/保留/multicast。"""
    try:
        ip = ipaddress.ip_address(ip_str)
    except ValueError:
        return False
    return (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_reserved
        or ip.is_multicast
        or ip.is_unspecified
    )


def _check_url_safe(url: str) -> str | None:
    """SSRF 防护：检查 URL 是否安全。返回拒绝原因，None 表示通过。"""
    try:
        parsed = urlparse(url)
    except Exception as e:
        return f"URL 解析失败: {e}"
    scheme = (parsed.scheme or "").lower()
    if scheme not in ("http", "https"):
        return f"不允许的协议: {scheme!r}（只支持 http/https）"
    host = parsed.hostname
    if not host:
        return "URL 缺少 host"
    # 1. 直接是 IP 字面量的情况
    try:
        if _is_blocked_ip(host):
            return f"拒绝访问私有/保留 IP: {host}"
    except (ValueError, OSError):
        pass
    # 2. DNS 解析后查每个 IP（包括 IPv4/IPv6 全部）
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror as e:
        return f"DNS 解析失败: {host}（{e}）"
    except Exception as e:
        return f"DNS 异常: {host}（{e}）"
    for info in infos:
        ip_str = info[4][0]
        if _is_blocked_ip(ip_str):
            return f"DNS 解析到私有/保留 IP: {host} → {ip_str}"
    return None


class WebFetchTool(BaseTool):
    name = "web_fetch"
    description = (
        "网页内容抓取工具。输入 URL，返回网页的纯文本正文（已剥离脚本/样式/导航/页脚）。"
        "适合抓取新闻、文章、小红书/B站等内容页。"
        "出于安全考虑：只允许 http/https；不允许访问私有/loopback/内网 IP；redirect 到内网会被拦截。"
    )
    parameters = {
        "type": "object",
        "properties": {
            "url": {
                "type": "string",
                "description": "要抓取的 URL（http/https，公网地址）",
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

        # 入口 URL SSRF 检查
        err = _check_url_safe(url)
        if err:
            return f"SSRF 防护拦截: {err}"

        # redirect 校验 hook：每次发出新 request（含 redirect 目标）都校验
        async def _validate_request(request: "httpx.Request") -> None:
            err2 = _check_url_safe(str(request.url))
            if err2:
                # 抛出 RequestError 让外层 except httpx.RequestError 兜底
                raise httpx.RequestError(
                    f"redirect SSRF 拦截: {err2}", request=request,
                )

        try:
            async with httpx.AsyncClient(
                timeout=30.0,
                follow_redirects=True,
                event_hooks={"request": [_validate_request]},
            ) as client:
                resp = await client.get(url, headers=_HEADERS)
                resp.raise_for_status()
                html = resp.text
        except httpx.HTTPStatusError as e:
            return f"HTTP 错误 {e.response.status_code}: {url}"
        except httpx.RequestError as e:
            return f"请求失败: {e}"

        content = self._extract_text(html)

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
