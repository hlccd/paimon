"""B 站 collector：直接走 B 站官方搜索 API（免签名免登录）。

API: https://api.bilibili.com/x/web-interface/search/all/v2
返回字段直接含：bvid / title / description / author / pubdate /
              play / video_review(弹幕) / favorites / tag

不需要 wbi 签名，不需要 yt-dlp 二次拉——MVP 一步到位。
未来若要 like/coin/comment，二次调 view stat API（P2 优化项）。
"""
from __future__ import annotations

import re
from html import unescape

from . import http, log
from .dates import in_window, parse_unix
from .schema import Item

_SEARCH_URL = "https://api.bilibili.com/x/web-interface/search/all/v2"
_VIEW_URL = "https://api.bilibili.com/x/web-interface/view"
_EM_TAGS = re.compile(r'<em[^>]*class="keyword"[^>]*>(.*?)</em>', re.IGNORECASE | re.DOTALL)


def _clean_em(text: str) -> str:
    """B 站标题里高亮关键词被包了 <em class="keyword">XXX</em>，剥掉。"""
    if not text:
        return ""
    return unescape(_EM_TAGS.sub(r"\1", text))


def _video_to_item(v: dict, range_from: str, range_to: str) -> Item | None:
    bvid = v.get("bvid") or ""
    if not bvid:
        return None
    pub = parse_unix(v.get("pubdate") or 0)
    if not in_window(pub, range_from, range_to):
        return None
    title = _clean_em(v.get("title") or "")
    desc = _clean_em(v.get("description") or "")
    return Item(
        source="bili",
        item_id=bvid,
        title=title,
        url=f"https://www.bilibili.com/video/{bvid}",
        body=desc[:500],
        author=v.get("author") or "",
        published_at=pub,
        engagement={
            "view":     int(v.get("play") or 0),
            "danmaku":  int(v.get("video_review") or v.get("danmaku") or 0),
            "favorite": int(v.get("favorites") or 0),
            # 评论 / 点赞 / 投币 search API 不返回；P2 二次拉 view stat
        },
        metadata={
            "tag": v.get("tag", ""),
            "duration": v.get("duration", ""),  # 形如 "12:34"
        },
    )


def _search(topic: str, page: int = 1) -> list[dict]:
    """调 B 站搜索 API，返回视频组的 data 列表。"""
    try:
        resp = http.request(
            "GET", _SEARCH_URL,
            params={"keyword": topic, "page": str(page)},
            timeout=15,
        )
    except http.HTTPError as e:
        log.source_log("bili", f"search HTTP 错误 {e.status}")
        return []
    if (resp or {}).get("code") != 0:
        log.source_log("bili", f"search code={resp.get('code')} msg={resp.get('message','')[:80]}")
        return []
    for group in resp.get("data", {}).get("result", []) or []:
        if group.get("result_type") == "video":
            return group.get("data", []) or []
    return []


def collect(
    topic: str,
    range_from: str,
    range_to: str,
    *,
    limit: int = 20,
    max_pages: int = 2,
) -> list[Item]:
    """B 站 collector 入口（不再依赖外部 discover）。

    返回 30 天窗内的 Item 列表，按 search 原序（B 站综合排序）。
    """
    log.source_log("bili", f"search topic={topic!r}")
    items: list[Item] = []
    for page in range(1, max_pages + 1):
        videos = _search(topic, page=page)
        if not videos:
            break
        for v in videos:
            it = _video_to_item(v, range_from, range_to)
            if it:
                items.append(it)
            if len(items) >= limit:
                break
        if len(items) >= limit:
            break
    log.source_log("bili", f"采集 {len(items)} 条（窗口 {range_from}~{range_to}）")
    return items
