"""推送归档 API — push_archive 表的只读 list / get（多个面板拉历史用）。

红点 / 未读计数 / mark_read 已废（推送基础设施被砍后保留 push_archive 表当事件归档）。
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from aiohttp import web

if TYPE_CHECKING:
    from paimon.channels.webui.channel import WebUIChannel


async def push_archive_list_api(channel, request: web.Request) -> web.Response:
    """归档列表，可按 actor / 全文搜索过滤。"""
    if not channel._check_auth(request):
        return web.json_response({"error": "Unauthorized"}, status=401)
    irminsul = channel.state.irminsul
    if not irminsul:
        return web.json_response({"records": []})
    actor = request.query.get("actor", "").strip() or None
    q = (request.query.get("q", "") or "").strip()
    try:
        limit = max(1, min(int(request.query.get("limit", "50")), 200))
    except (TypeError, ValueError):
        limit = 50

    def _parse_ts(name: str) -> float | None:
        raw = (request.query.get(name, "") or "").strip()
        if not raw:
            return None
        try:
            return float(raw)
        except (TypeError, ValueError):
            return None
    since = _parse_ts("since")
    until = _parse_ts("until")

    # 搜索时先大窗口拉再过滤（避免 limit 截断后漏了更早的命中条目）；
    # 没搜索时直接 limit
    fetch_limit = max(limit, 500) if q else limit
    records = await irminsul.push_archive_list(
        actor=actor, since=since, until=until, limit=fetch_limit,
    )
    # 全文搜索：在 message_md / source 上做不区分大小写包含匹配
    if q:
        q_low = q.lower()
        records = [
            r for r in records
            if q_low in (r.message_md or "").lower()
            or q_low in (r.source or "").lower()
        ]
        records = records[:limit]

    return web.json_response({
        "records": [
            {
                "id": r.id,
                "source": r.source,
                "actor": r.actor,
                "message_md": r.message_md,
                "extra": r.extra,
                "created_at": r.created_at,
            }
            for r in records
        ]
    })


async def push_archive_detail_api(channel, request: web.Request) -> web.Response:
    """单条归档详情。"""
    if not channel._check_auth(request):
        return web.json_response({"error": "Unauthorized"}, status=401)
    irminsul = channel.state.irminsul
    if not irminsul:
        return web.json_response({"error": "世界树未就绪"}, status=500)
    rec_id = request.match_info["rec_id"]
    rec = await irminsul.push_archive_get(rec_id)
    if not rec:
        return web.json_response({"error": "记录不存在"}, status=404)
    return web.json_response({
        "id": rec.id,
        "source": rec.source,
        "actor": rec.actor,
        "channel_name": rec.channel_name,
        "chat_id": rec.chat_id,
        "message_md": rec.message_md,
        "extra": rec.extra,
        "created_at": rec.created_at,
    })


def register_routes(app: web.Application, channel: "WebUIChannel") -> None:
    """注册 push_archive 面板的 2 个路由（list / get；红点/标已读已废）。"""
    app.router.add_get("/api/push_archive/list", lambda r, ch=channel: push_archive_list_api(ch, r))
    app.router.add_get("/api/push_archive/{rec_id}", lambda r, ch=channel: push_archive_detail_api(ch, r))
