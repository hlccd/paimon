"""原石 token 用量统计 API（按 component / 时间线维度）。"""
from __future__ import annotations

from typing import TYPE_CHECKING

from aiohttp import web
from loguru import logger

if TYPE_CHECKING:
    from paimon.channels.webui.channel import WebUIChannel


async def token_stats(channel, request: web.Request) -> web.Response:
    if channel.require_auth:
        token = request.cookies.get("paimon_token")
        if not token or token not in channel.valid_tokens:
            return web.json_response({"error": "Unauthorized"}, status=401)

    primogem = channel.state.primogem
    if not primogem:
        return web.json_response({"error": "原石模块未启用"}, status=500)

    global_stats = await primogem.get_global_stats()
    detail_stats = await primogem.get_detail_stats()

    return web.json_response({
        "global": global_stats,
        "detail": detail_stats,
    })


async def token_stats_timeline(channel, request: web.Request) -> web.Response:
    if channel.require_auth:
        token = request.cookies.get("paimon_token")
        if not token or token not in channel.valid_tokens:
            return web.json_response({"error": "Unauthorized"}, status=401)

    primogem = channel.state.primogem
    if not primogem:
        return web.json_response({"error": "原石模块未启用"}, status=500)

    period = request.query.get("period", "day")
    count = min(int(request.query.get("count", "7")), 365)

    if period in ("hour", "weekday"):
        data = await primogem.get_distribution_stats(by=period)
    else:
        data = await primogem.get_timeline_stats(period, count)

    return web.json_response({"period": period, "data": data})


def register_routes(app: web.Application, channel: "WebUIChannel") -> None:
    """注册 token 面板的 2 个路由。"""
    app.router.add_get("/api/token_stats", lambda r, ch=channel: token_stats(ch, r))
    app.router.add_get("/api/token_stats/timeline", lambda r, ch=channel: token_stats_timeline(ch, r))
