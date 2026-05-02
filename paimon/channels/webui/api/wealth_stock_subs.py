"""岩神理财面板 - 关注股资讯订阅段（list/toggle/run）。"""
from __future__ import annotations

from typing import TYPE_CHECKING

from aiohttp import web
from loguru import logger

from paimon.foundation.bg import bg

if TYPE_CHECKING:
    from paimon.channels.webui.channel import WebUIChannel


async def wealth_stock_subs_list_api(channel, request: web.Request) -> web.Response:
    """列岩神关注股资讯订阅（binding_kind='stock_watch'）。"""
    if not channel._check_auth(request):
        return web.json_response({"error": "Unauthorized"}, status=401)
    irminsul = channel.state.irminsul
    if not irminsul:
        return web.json_response({"subs": []})
    subs = await irminsul.subscription_list_by_binding("stock_watch")
    venti = channel.state.venti
    out = []
    for s in subs:
        item_count = await irminsul.feed_items_count(sub_id=s.id)
        out.append({
            "id": s.id,
            "stock_code": s.binding_id,
            "query": s.query,
            "schedule_cron": s.schedule_cron,
            "enabled": s.enabled,
            "last_run_at": s.last_run_at,
            "last_error": s.last_error,
            "item_count": item_count,
            "running": bool(venti and venti.is_running(s.id)),
        })
    return web.json_response({"subs": out})


async def wealth_stock_subs_toggle_api(channel, request: web.Request,
) -> web.Response:
    """启停岩神关注股订阅。"""
    if not channel._check_auth(request):
        return web.json_response({"error": "Unauthorized"}, status=401)
    irminsul = channel.state.irminsul
    if not irminsul:
        return web.json_response({"ok": False, "error": "世界树未就绪"})
    sub_id = request.match_info["sub_id"]
    try:
        data = await request.json()
        enabled = bool(data.get("enabled"))
    except Exception:
        return web.json_response({"ok": False, "error": "JSON 无效"}, status=400)
    sub = await irminsul.subscription_get(sub_id)
    if not sub or sub.binding_kind != "stock_watch":
        return web.json_response(
            {"ok": False, "error": "非岩神关注股订阅"}, status=400,
        )
    await irminsul.subscription_update(
        sub_id, actor="WebUI·理财面板", enabled=enabled,
    )
    if sub.linked_task_id and channel.state.march:
        try:
            if enabled:
                await channel.state.march.resume_task(sub.linked_task_id)
            else:
                await channel.state.march.pause_task(sub.linked_task_id)
        except Exception as e:
            logger.warning(
                "[岩神·关注股订阅] 同步 task 启停失败 sub={}: {}", sub_id, e,
            )
    return web.json_response({"ok": True})


async def wealth_stock_subs_run_api(channel, request: web.Request,
) -> web.Response:
    """立即触发一次岩神关注股资讯采集。"""
    if not channel._check_auth(request):
        return web.json_response({"error": "Unauthorized"}, status=401)
    irminsul = channel.state.irminsul
    venti = channel.state.venti
    if not irminsul or not venti:
        return web.json_response({"ok": False, "error": "依赖未就绪"})
    sub_id = request.match_info["sub_id"]
    sub = await irminsul.subscription_get(sub_id)
    if not sub or sub.binding_kind != "stock_watch":
        return web.json_response(
            {"ok": False, "error": "非岩神关注股订阅"}, status=400,
        )
    async def _run():
        try:
            await venti.collect_subscription(
                sub_id, irminsul=irminsul,
                model=channel.state.model, march=channel.state.march,
            )
        except Exception as e:
            logger.exception(
                "[岩神·关注股订阅] 手动触发采集异常 sub={}: {}", sub_id, e,
            )
    bg(_run(), label=f"venti·关注股订阅采集·{sub_id[:8]}·webui")
    return web.json_response({"ok": True, "message": "已触发，稍候刷新"})


def register_routes(app: web.Application, channel: "WebUIChannel") -> None:
    """注册 wealth_stock_subs 面板的 3 个路由。"""
    app.router.add_get("/api/wealth/stock_subscriptions", lambda r, ch=channel: wealth_stock_subs_list_api(ch, r))
    app.router.add_post("/api/wealth/stock_subscriptions/{sub_id}/toggle", lambda r, ch=channel: wealth_stock_subs_toggle_api(ch, r))
    app.router.add_post("/api/wealth/stock_subscriptions/{sub_id}/run", lambda r, ch=channel: wealth_stock_subs_run_api(ch, r))
