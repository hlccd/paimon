"""超薄 HTTP 客户端：stdlib only，避开依赖 requests/httpx 的版本冲突。"""
from __future__ import annotations

import json as _json
import urllib.error
import urllib.request
from typing import Any
from urllib.parse import urlencode

DEFAULT_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)


class HTTPError(Exception):
    def __init__(self, status: int, body: str = ""):
        self.status = status
        self.body = body
        super().__init__(f"HTTP {status}: {body[:200]}")


def request(
    method: str,
    url: str,
    *,
    params: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    data: bytes | str | None = None,
    timeout: float = 15.0,
    expect_json: bool = True,
) -> Any:
    """单次 GET/POST。expect_json=True 自动解析；False 返回原始 str。"""
    if params:
        url = f"{url}?{urlencode(params)}"
    h = {"User-Agent": DEFAULT_UA}
    if headers:
        h.update(headers)
    body = data.encode("utf-8") if isinstance(data, str) else data
    req = urllib.request.Request(url, data=body, headers=h, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            return _json.loads(raw) if expect_json else raw
    except urllib.error.HTTPError as e:
        raise HTTPError(e.code, e.read().decode("utf-8", errors="replace") if e.fp else "") from e
    except urllib.error.URLError as e:
        raise HTTPError(0, str(e)) from e
