"""推送归档 API — 全局红点抽屉数据源（push_archive 域只读 + 标已读）。"""
from __future__ import annotations

from typing import TYPE_CHECKING

from aiohttp import web

if TYPE_CHECKING:
    from paimon.channels.webui.channel import WebUIChannel


async def push_archive_unread_api(channel, request: web.Request) -> web.Response:
    """全局未读计数 + 按 actor 分组（导航栏红点 30s 轮询）。"""
    if not channel._check_auth(request):
        return web.json_response({"error": "Unauthorized"}, status=401)
    irminsul = channel.state.irminsul
    if not irminsul:
        return web.json_response({"total": 0, "by_actor": {}})
    grouped = await irminsul.push_archive_count_unread_grouped()
    total = sum(grouped.values())
    return web.json_response({"total": total, "by_actor": grouped})


async def push_archive_list_api(channel, request: web.Request) -> web.Response:
    """归档列表，可按 actor / 仅未读 / 全文搜索过滤。"""
    if not channel._check_auth(request):
        return web.json_response({"error": "Unauthorized"}, status=401)
    irminsul = channel.state.irminsul
    if not irminsul:
        return web.json_response({"records": []})
    actor = request.query.get("actor", "").strip() or None
    only_unread = request.query.get("unread", "").strip().lower() in ("1", "true", "yes")
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
        actor=actor, only_unread=only_unread,
        since=since, until=until, limit=fetch_limit,
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
                "level": r.level,
                "message_md": r.message_md,
                "extra": r.extra,
                "created_at": r.created_at,
                "read_at": r.read_at,
            }
            for r in records
        ]
    })


async def push_archive_detail_api(channel, request: web.Request) -> web.Response:
    """单条归档详情（看时不自动 mark_read，前端拉完后单独调 read 接口）。"""
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
        "level": rec.level,
        "channel_name": rec.channel_name,
        "chat_id": rec.chat_id,
        "message_md": rec.message_md,
        "extra": rec.extra,
        "created_at": rec.created_at,
        "read_at": rec.read_at,
    })


async def push_archive_mark_read_api(channel, request: web.Request) -> web.Response:
    if not channel._check_auth(request):
        return web.json_response({"error": "Unauthorized"}, status=401)
    irminsul = channel.state.irminsul
    if not irminsul:
        return web.json_response({"ok": False, "error": "世界树未就绪"}, status=500)
    rec_id = request.match_info["rec_id"]
    ok = await irminsul.push_archive_mark_read(rec_id)
    return web.json_response({"ok": ok})


async def push_archive_mark_read_all_api(channel, request: web.Request) -> web.Response:
    if not channel._check_auth(request):
        return web.json_response({"error": "Unauthorized"}, status=401)
    irminsul = channel.state.irminsul
    if not irminsul:
        return web.json_response({"ok": False, "error": "世界树未就绪"}, status=500)
    actor = request.query.get("actor", "").strip() or None
    n = await irminsul.push_archive_mark_read_all(actor=actor)
    return web.json_response({"ok": True, "marked": n})


def register_routes(app: web.Application, channel: "WebUIChannel") -> None:
    """注册 push_archive 面板的 5 个路由（只读列表 + 标已读）。"""
    app.router.add_get("/api/push_archive/unread_count", lambda r, ch=channel: push_archive_unread_api(ch, r))
    app.router.add_get("/api/push_archive/list", lambda r, ch=channel: push_archive_list_api(ch, r))
    app.router.add_get("/api/push_archive/{rec_id}", lambda r, ch=channel: push_archive_detail_api(ch, r))
    app.router.add_post("/api/push_archive/{rec_id}/read", lambda r, ch=channel: push_archive_mark_read_api(ch, r))
    app.router.add_post("/api/push_archive/read_all", lambda r, ch=channel: push_archive_mark_read_all_api(ch, r))
