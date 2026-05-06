"""风神信息流面板 API — 订阅 CRUD + 条目列表。"""
from __future__ import annotations

import time

from typing import TYPE_CHECKING

from aiohttp import web
from loguru import logger

from paimon.foundation.bg import bg

from paimon.channels.webui.channel import PUSH_CHAT_ID

if TYPE_CHECKING:
    from paimon.channels.webui.channel import WebUIChannel


async def feed_page(channel, request: web.Request) -> web.Response:
    if not channel._check_auth(request):
        return web.Response(text=channel._get_login_html(), content_type="text/html")

    from paimon.channels.webui.feed_html import build_feed_html
    return web.Response(
        text=build_feed_html(),
        content_type="text/html",
        headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
    )


async def feed_stats_api(channel, request: web.Request) -> web.Response:
    if not channel._check_auth(request):
        return web.json_response({"error": "Unauthorized"}, status=401)
    irminsul = channel.state.irminsul
    if not irminsul:
        return web.json_response({"sub_count": 0, "items_today": 0, "items_week": 0})
    now = time.time()
    subs = await irminsul.subscription_list()
    today = await irminsul.feed_items_count(since=now - 86400)
    week = await irminsul.feed_items_count(since=now - 7 * 86400)
    return web.json_response({
        "sub_count": len(subs),
        "items_today": today,
        "items_week": week,
    })


async def feed_subs_list_api(channel, request: web.Request) -> web.Response:
    if not channel._check_auth(request):
        return web.json_response({"error": "Unauthorized"}, status=401)
    irminsul = channel.state.irminsul
    if not irminsul:
        return web.json_response({"subs": []})
    # 风神面板只展示用户手填的 manual 订阅；
    # 业务实体衍生订阅（mihoyo_game / 未来 stock_watch 等）由各自 archon 面板管理
    subs = await irminsul.subscription_list_by_binding("manual")
    venti = channel.state.venti
    # PERF-002：N 个订阅并发拉 item_count + event_count，N=20 时旧版 40 次串行 await
    # → 改 gather 后总耗时 ≈ 单次 query（<100ms 而非 4-8s）
    import asyncio as _asyncio
    counts = await _asyncio.gather(
        *[irminsul.feed_items_count(sub_id=s.id) for s in subs],
        *[irminsul.feed_event_count(sub_id=s.id) for s in subs],
    )
    n = len(subs)
    item_counts = counts[:n]
    event_counts = counts[n:]
    out = []
    for i, s in enumerate(subs):
        out.append({
            "id": s.id,
            "query": s.query,
            "channel_name": s.channel_name,
            "chat_id": s.chat_id,
            "schedule_cron": s.schedule_cron,
            "engine": s.engine,
            "enabled": s.enabled,
            "max_items": s.max_items,
            "last_run_at": s.last_run_at,
            "last_error": s.last_error,
            "created_at": s.created_at,
            "item_count": item_counts[i],
            "event_count": event_counts[i],
            "running": bool(venti and venti.is_running(s.id)),
        })
    return web.json_response({"subs": out})


async def feed_subs_create_api(channel, request: web.Request) -> web.Response:
    """WebUI 新增订阅入口，直接调 core.commands.create_subscription helper。"""
    if not channel._check_auth(request):
        return web.json_response({"error": "Unauthorized"}, status=401)
    try:
        data = await request.json()
        query = (data.get("query") or "").strip()
        cron = (data.get("cron") or "").strip()
        engine = (data.get("engine") or "").strip()
    except Exception:
        return web.json_response({"ok": False, "error": "请求体 JSON 无效"}, status=400)

    from paimon.core.commands import create_subscription

    try:
        ok, message = await create_subscription(
            query=query, cron=cron, engine=engine,
            channel_name=channel.name,
            chat_id=PUSH_CHAT_ID,
            supports_push=getattr(channel, "supports_push", True),
        )
    except Exception as e:
        logger.error("[派蒙·WebUI·订阅] 创建异常: {}", e)
        return web.json_response({"ok": False, "error": str(e)}, status=500)

    if ok:
        return web.json_response({"ok": True, "message": message})
    return web.json_response({"ok": False, "error": message})


async def feed_subs_patch_api(channel, request: web.Request) -> web.Response:
    if not channel._check_auth(request):
        return web.json_response({"error": "Unauthorized"}, status=401)
    sub_id = request.match_info["sub_id"]
    try:
        data = await request.json()
    except Exception:
        return web.json_response({"ok": False, "error": "JSON 无效"}, status=400)

    irminsul = channel.state.irminsul
    march = channel.state.march
    if not irminsul:
        return web.json_response({"ok": False, "error": "世界树未就绪"}, status=500)

    sub = await irminsul.subscription_get(sub_id)
    if not sub:
        return web.json_response({"ok": False, "error": "订阅不存在"}, status=404)

    if "enabled" in data:
        enable = bool(data["enabled"])
        await irminsul.subscription_update(sub_id, actor="WebUI", enabled=enable)
        if sub.linked_task_id and march:
            try:
                if enable:
                    await march.resume_task(sub.linked_task_id)
                else:
                    await march.pause_task(sub.linked_task_id)
            except Exception as e:
                logger.warning("[WebUI·订阅] 同步定时任务启停失败: {}", e)
    return web.json_response({"ok": True})


async def feed_subs_delete_api(channel, request: web.Request) -> web.Response:
    if not channel._check_auth(request):
        return web.json_response({"error": "Unauthorized"}, status=401)
    sub_id = request.match_info["sub_id"]
    irminsul = channel.state.irminsul
    march = channel.state.march
    if not irminsul:
        return web.json_response({"ok": False, "error": "世界树未就绪"}, status=500)

    sub = await irminsul.subscription_get(sub_id)
    if not sub:
        return web.json_response({"ok": False, "error": "订阅不存在"}, status=404)
    if sub.linked_task_id and march:
        try:
            await march.delete_task(sub.linked_task_id)
        except Exception as e:
            logger.warning("[WebUI·订阅] 删定时任务失败: {}", e)
    await irminsul.subscription_delete(sub_id, actor="WebUI")
    return web.json_response({"ok": True})


async def feed_subs_run_api(channel, request: web.Request) -> web.Response:
    if not channel._check_auth(request):
        return web.json_response({"error": "Unauthorized"}, status=401)
    sub_id = request.match_info["sub_id"]
    if not channel.state.venti or not channel.state.irminsul:
        return web.json_response({"ok": False, "error": "风神未就绪"}, status=500)
    sub = await channel.state.irminsul.subscription_get(sub_id)
    if not sub:
        return web.json_response({"ok": False, "error": "订阅不存在"}, status=404)
    bg(channel.state.venti.collect_subscription(
        sub_id,
        irminsul=channel.state.irminsul,
        model=channel.state.model,
        march=channel.state.march,
    ), label=f"venti·订阅采集·{sub_id[:8]}·webui")
    return web.json_response({"ok": True})


async def feed_items_api(channel, request: web.Request) -> web.Response:
    if not channel._check_auth(request):
        return web.json_response({"error": "Unauthorized"}, status=401)
    irminsul = channel.state.irminsul
    if not irminsul:
        return web.json_response({"items": []})

    sub_id = request.query.get("sub_id", "").strip() or None
    since_sec = 0
    try:
        since_sec = int(request.query.get("since", "0"))
    except (TypeError, ValueError):
        since_sec = 0
    since_ts = time.time() - since_sec if since_sec > 0 else None

    limit = min(int(request.query.get("limit", "200")), 500)
    items = await irminsul.feed_items_list(
        sub_id=sub_id, since=since_ts, limit=limit,
    )
    return web.json_response({
        "items": [
            {
                "id": it.id,
                "subscription_id": it.subscription_id,
                "url": it.url,
                "title": it.title,
                "description": it.description,
                "engine": it.engine,
                "captured_at": it.captured_at,
                "pushed_at": it.pushed_at,
                "digest_id": it.digest_id,
            }
            for it in items
        ]
    })


# ─────────────────────────────────────────────────────────────
# 站点登录 API（cookies 扫码管理；归风神主管，给 topic 等登录态 collector 用）
# ─────────────────────────────────────────────────────────────

async def login_overview_api(channel, request: web.Request) -> web.Response:
    """各站点 cookies 配置状态总览。"""
    if not channel._check_auth(request):
        return web.json_response({"error": "Unauthorized"}, status=401)
    venti = channel.state.venti
    if not venti:
        return web.json_response({"sites": []})
    return web.json_response({"sites": venti.login_overview()})


async def login_start_api(channel, request: web.Request) -> web.Response:
    """启动一次扫码登录会话。"""
    if not channel._check_auth(request):
        return web.json_response({"error": "Unauthorized"}, status=401)
    venti = channel.state.venti
    if not venti:
        return web.json_response({"ok": False, "error": "风神未就绪"}, status=500)
    try:
        data = await request.json()
    except Exception:
        return web.json_response({"ok": False, "error": "JSON 无效"}, status=400)
    site = (data.get("site") or "").strip()
    if not site:
        return web.json_response({"ok": False, "error": "site 必填"}, status=400)
    return web.json_response(await venti.login_start(site))


async def login_status_api(channel, request: web.Request) -> web.Response:
    """轮询会话状态（前端循环调）。"""
    if not channel._check_auth(request):
        return web.json_response({"error": "Unauthorized"}, status=401)
    venti = channel.state.venti
    if not venti:
        return web.json_response({"ok": False, "error": "风神未就绪"})
    session_id = request.match_info.get("session_id", "")
    return web.json_response(venti.login_status(session_id))


async def login_qr_api(channel, request: web.Request) -> web.Response:
    """拿当前 QR PNG（前端 <img> src 指向这里）。"""
    if not channel._check_auth(request):
        return web.Response(status=401, text="Unauthorized")
    venti = channel.state.venti
    if not venti:
        return web.Response(status=500, text="venti 未就绪")
    session_id = request.match_info.get("session_id", "")
    qr = venti.login_qr(session_id)
    if not qr:
        return web.Response(status=404, text="QR 未生成或会话过期")
    # 不缓存，每次刷新拿最新
    return web.Response(body=qr, content_type="image/png", headers={
        "Cache-Control": "no-cache, no-store, must-revalidate",
        "Pragma": "no-cache",
    })


def register_routes(app: web.Application, channel: "WebUIChannel") -> None:
    """注册 feed 面板的路由（订阅 + 站点登录）。"""
    app.router.add_get("/feed", lambda r, ch=channel: feed_page(ch, r))
    app.router.add_get("/api/feed/stats", lambda r, ch=channel: feed_stats_api(ch, r))
    app.router.add_get("/api/feed/subs", lambda r, ch=channel: feed_subs_list_api(ch, r))
    app.router.add_post("/api/feed/subs", lambda r, ch=channel: feed_subs_create_api(ch, r))
    app.router.add_patch("/api/feed/subs/{sub_id}", lambda r, ch=channel: feed_subs_patch_api(ch, r))
    app.router.add_delete("/api/feed/subs/{sub_id}", lambda r, ch=channel: feed_subs_delete_api(ch, r))
    app.router.add_post("/api/feed/subs/{sub_id}/run", lambda r, ch=channel: feed_subs_run_api(ch, r))
    app.router.add_get("/api/feed/items", lambda r, ch=channel: feed_items_api(ch, r))
    # 站点登录扫码
    app.router.add_get("/api/feed/login/overview", lambda r, ch=channel: login_overview_api(ch, r))
    app.router.add_post("/api/feed/login/start", lambda r, ch=channel: login_start_api(ch, r))
    app.router.add_get("/api/feed/login/status/{session_id}", lambda r, ch=channel: login_status_api(ch, r))
    app.router.add_get("/api/feed/login/qr/{session_id}", lambda r, ch=channel: login_qr_api(ch, r))
