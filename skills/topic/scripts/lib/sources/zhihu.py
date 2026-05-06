"""知乎 collector：用登录态 cookies 调知乎搜索 v3 API。

cookies 来源：~/.paimon/cookies/zhihu.json（playwright storage_state 格式）
首次登录：在 webui `/feed` 面板的「站点登录」tab 扫码

知乎搜索 API：
    GET https://www.zhihu.com/api/v4/search_v3?t=general&q=<topic>&offset=0&limit=20

返回类型混合：question / answer / article / zvideo / topic / search_card
本 collector 处理 question / answer / article 三种主要类型；其他类型跳过。
"""
from __future__ import annotations

import re
from html import unescape
from typing import Any
from urllib.parse import quote

from ..core import http, log
from ..core.dates import in_window, parse_unix
from ..core.schema import Item

_EM_TAGS = re.compile(r'<em[^>]*>(.*?)</em>', re.IGNORECASE | re.DOTALL)


def _clean_em(text: str) -> str:
    """剥 <em class="keyword">XXX</em> 高亮标签 + HTML 实体解码。"""
    if not text:
        return ""
    return unescape(_EM_TAGS.sub(r"\1", text))


_SEARCH_URL = "https://www.zhihu.com/api/v4/search_v3"
_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)


def _load_cookies_header() -> str | None:
    """读 <paimon_home>/cookies/zhihu.json → Cookie header。无 cookies 返回 None。"""
    from paimon.foundation.site_cookies import cookies_to_header
    return cookies_to_header("zhihu")


def _get_obj(d: dict, *path: str) -> Any:
    """链式取嵌套字段，任一层缺失或非 dict 返回 None。"""
    cur = d
    for k in path:
        if not isinstance(cur, dict):
            return None
        cur = cur.get(k)
    return cur


def _result_to_item(r: dict, range_from: str, range_to: str) -> Item | None:
    """search v3 一条 hit → Item；不在 30 天窗或类型不支持返回 None。

    search_v3 的实际结构：
        r = {"type": "search_result", "object": {"type": "answer", ...真实数据}}
    所以真实类型永远在 obj.type，r.type 只是 wrapper 标识。
    """
    obj = r.get("object") or {}
    if not obj:
        obj = r
    # 真实类型：obj.type 优先，r.type 仅作降级（除非是 wrapper 类型）
    outer_t = r.get("type") or ""
    inner_t = obj.get("type") or ""
    _wrappers = {"search_result", "search_section", "search_card"}
    t = inner_t if (outer_t in _wrappers or not outer_t) else outer_t

    item_id: str = ""
    title: str = ""
    url: str = ""
    body: str = ""
    author: str = ""
    ts: int = 0
    engagement: dict[str, int] = {}

    if t == "answer":
        item_id = str(obj.get("id") or "")
        question = obj.get("question") or {}
        title = question.get("title") or obj.get("excerpt", "")[:60] or ""
        qid = question.get("id") or obj.get("question_id")
        url = f"https://www.zhihu.com/question/{qid}/answer/{item_id}" if qid else f"https://www.zhihu.com/answer/{item_id}"
        body = obj.get("excerpt", "") or obj.get("content", "")
        author = _get_obj(obj, "author", "name") or ""
        ts = int(obj.get("created_time") or obj.get("updated_time") or 0)
        engagement = {
            "like": int(obj.get("voteup_count") or 0),
            "comment": int(obj.get("comment_count") or 0),
            "favorite": int(obj.get("collect_count") or 0),
            "thanks": int(obj.get("thanks_count") or 0),
        }
    elif t == "article":
        item_id = str(obj.get("id") or "")
        title = obj.get("title") or ""
        url = obj.get("url") or f"https://zhuanlan.zhihu.com/p/{item_id}"
        body = obj.get("excerpt", "") or obj.get("content", "")
        author = _get_obj(obj, "author", "name") or ""
        ts = int(obj.get("created") or obj.get("created_time") or obj.get("updated") or 0)
        engagement = {
            "like": int(obj.get("voteup_count") or 0),
            "comment": int(obj.get("comment_count") or 0),
        }
    elif t == "question":
        item_id = str(obj.get("id") or "")
        title = obj.get("title") or ""
        url = f"https://www.zhihu.com/question/{item_id}"
        body = obj.get("excerpt", "")
        ts = int(obj.get("created") or obj.get("created_time") or 0)
        engagement = {
            "follower": int(obj.get("follower_count") or 0),
            "answer": int(obj.get("answer_count") or 0),
            "view": int(obj.get("visit_count") or 0),
        }
    else:
        return None

    if not item_id or not title:
        return None

    pub_date = parse_unix(ts) if ts else ""
    if not in_window(pub_date, range_from, range_to):
        return None

    return Item(
        source="zhihu",
        item_id=f"{t}_{item_id}",
        title=_clean_em(title).strip(),
        url=url,
        body=_clean_em(body)[:500],
        author=author,
        published_at=pub_date,
        engagement=engagement,
        metadata={"zhihu_type": t},
    )


def collect(
    topic: str,
    range_from: str,
    range_to: str,
    *,
    limit: int = 20,
    max_pages: int = 2,
) -> list[Item]:
    """知乎 collector 入口。

    需要 cookies；无 cookies 返回 [] + log warning。
    """
    cookie_header = _load_cookies_header()
    if not cookie_header:
        log.source_log("zhihu", "无 cookies；请到 webui /feed 面板的「站点登录」tab 扫码")
        return []

    log.source_log("zhihu", f"search topic={topic!r}")
    headers = {
        "User-Agent": _UA,
        "Cookie": cookie_header,
        "Referer": f"https://www.zhihu.com/search?q={quote(topic)}",
        "x-requested-with": "fetch",
        "Accept": "*/*",
        "Accept-Language": "zh-CN,zh;q=0.9",
    }

    items: list[Item] = []
    type_counts: dict[str, int] = {}
    skipped_unsupported = 0
    skipped_window = 0
    page_size = 20
    for page in range(max_pages):
        # 重试：知乎搜索偶发短暂风控 / 返回空 data，sleep 1s 重试 1-2 次能恢复
        resp = None
        last_err = ""
        for attempt in range(3):
            try:
                r = http.request(
                    "GET", _SEARCH_URL,
                    params={
                        "t": "general",
                        "q": topic,
                        "limit": str(page_size),
                        "offset": str(page * page_size),
                    },
                    headers=headers,
                    timeout=15,
                )
                # 200 但 data 为空也算"软失败"重试（风控期 zhihu 会返 200+空数组）
                got_data = bool((r or {}).get("data"))
                if got_data or page > 0:
                    resp = r
                    break
                last_err = "data 为空"
            except http.HTTPError as e:
                last_err = f"HTTP {e.status}"
            if attempt < 2:
                import time as _time
                log.source_log("zhihu", f"search 第 {attempt+1}/3 次失败（{last_err}），1s 后重试")
                _time.sleep(1)
        if resp is None:
            log.source_log("zhihu", f"search 3 次都失败（{last_err}；cookies 可能失效，到 webui /feed「站点登录」tab 扫码续期）")
            break
        data = (resp or {}).get("data") or []
        if not data:
            log.source_log("zhihu", f"page={page} 空响应 keys={list((resp or {}).keys())[:5]}")
            break
        for r in data:
            obj = r.get("object") or {}
            outer_t = r.get("type") or ""
            inner_t = obj.get("type") or ""
            t = inner_t or outer_t or "_unknown"
            type_counts[t] = type_counts.get(t, 0) + 1
            it = _result_to_item(r, range_from, range_to)
            if it:
                items.append(it)
            elif t not in ("answer", "article", "question"):
                skipped_unsupported += 1
            else:
                skipped_window += 1
            if len(items) >= limit:
                break
        if len(items) >= limit:
            break

    if type_counts:
        log.source_log("zhihu", f"hit 类型分布: " + ", ".join(f"{t}={c}" for t, c in type_counts.items()))
    if skipped_unsupported:
        log.source_log("zhihu", f"跳过 {skipped_unsupported} 个不支持的 hit 类型")
    if skipped_window:
        log.source_log("zhihu", f"跳过 {skipped_window} 个 30 天窗外/无日期 hit")
    log.source_log("zhihu", f"采集 {len(items)} 条")
    return items
