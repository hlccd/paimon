"""风神订阅面板 API — 订阅 CRUD + topic 调研结果展示 + 站点登录。"""
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


async def feed_subs_list_api(channel, request: web.Request) -> web.Response:
    if not channel._check_auth(request):
        return web.json_response({"error": "Unauthorized"}, status=401)
    irminsul = channel.state.irminsul
    if not irminsul:
        return web.json_response({"subs": []})
    # 风神面板只展示 topic_research 订阅（mihoyo_game / stock_watch 由各自 archon 面板管）
    subs = await irminsul.subscription_list_by_binding("topic_research")
    venti = channel.state.venti
    out = []
    for s in subs:
        out.append({
            "id": s.id,
            "query": s.query,
            "channel_name": s.channel_name,
            "chat_id": s.chat_id,
            "schedule_cron": s.schedule_cron,
            "enabled": s.enabled,
            "last_run_at": s.last_run_at,
            "last_error": s.last_error,
            "created_at": s.created_at,
            "binding_kind": s.binding_kind,
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
    except Exception:
        return web.json_response({"ok": False, "error": "请求体 JSON 无效"}, status=400)

    from paimon.core.commands import create_subscription

    try:
        ok, message = await create_subscription(
            query=query, cron=cron,
            channel_name=channel.name,
            chat_id=PUSH_CHAT_ID,
            supports_push=getattr(channel, "supports_push", True),
            binding_kind="topic_research",
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


async def feed_topic_research_api(channel, request: web.Request) -> web.Response:
    """读 topic_research 订阅最新一条覆盖式快照（每订阅一条；不返历史）。"""
    if not channel._check_auth(request):
        return web.json_response({"error": "Unauthorized"}, status=401)
    sub_id = request.match_info["sub_id"]
    irminsul = channel.state.irminsul
    if not irminsul:
        return web.json_response({"research": None})
    rec = await irminsul.feed_topic_research_get(sub_id)
    return web.json_response({"research": rec})


# ─────────────────────────────────────────────────────────────
# 每日热点 API（cron 11/17 跑；前端进面板拉最新一份展示）
# ─────────────────────────────────────────────────────────────

async def hotspot_today_api(channel, request: web.Request) -> web.Response:
    """拉最新一份每日热点（按 captured_at 倒序第一条）+ inflight 状态。"""
    if not channel._check_auth(request):
        return web.json_response({"error": "Unauthorized"}, status=401)
    irminsul = channel.state.irminsul
    venti = channel.state.venti
    running = bool(venti and venti.is_hotspot_running())
    if not irminsul:
        return web.json_response({"hotspot": None, "running": running})
    rec = await irminsul.daily_hotspot_get_latest()
    return web.json_response({"hotspot": rec, "running": running})


async def hotspot_list_api(channel, request: web.Request) -> web.Response:
    """近 N 天的所有 slot 列表（最多 N×2 条，倒序）。"""
    if not channel._check_auth(request):
        return web.json_response({"error": "Unauthorized"}, status=401)
    irminsul = channel.state.irminsul
    if not irminsul:
        return web.json_response({"items": []})
    try:
        days = max(1, min(int(request.query.get("days", "7")), 30))
    except (TypeError, ValueError):
        days = 7
    items = await irminsul.daily_hotspot_list_recent(days)
    return web.json_response({"items": items})


async def hotspot_run_api(channel, request: web.Request) -> web.Response:
    """手动触发一次每日热点采集（前端「立即跑」按钮）。

    同步设 inflight=True 后再 bg：保证 API 返回时 venti.is_hotspot_running()=true，
    前端立刻拉 /today 也能看到 running=true（避免 race 闪回）。
    """
    if not channel._check_auth(request):
        return web.json_response({"error": "Unauthorized"}, status=401)
    venti = channel.state.venti
    if not venti or not channel.state.irminsul or not channel.state.model:
        return web.json_response({"ok": False, "error": "依赖未就绪"}, status=500)
    if venti.is_hotspot_running():
        return web.json_response({"ok": False, "error": "已在采集中"})

    venti._hotspot_inflight = True  # 同步设上，return 时必然 true

    async def _go():
        from paimon.archons.venti.hotspot import run_daily_hotspot_collect
        try:
            await run_daily_hotspot_collect(channel.state)
        except Exception as e:
            logger.exception("[风神·hotspot] 手动采集异常: {}", e)
        finally:
            venti._hotspot_inflight = False
    bg(_go(), label="venti·hotspot·webui-manual")
    return web.json_response({"ok": True})


async def weekly_latest_api(channel, request: web.Request) -> web.Response:
    """拉最新一份近期回顾（整张表只 1 条）+ inflight 状态。"""
    if not channel._check_auth(request):
        return web.json_response({"error": "Unauthorized"}, status=401)
    irminsul = channel.state.irminsul
    venti = channel.state.venti
    running = bool(venti and venti.is_weekly_running())
    if not irminsul:
        return web.json_response({"weekly": None, "running": running})
    rec = await irminsul.weekly_hotspot_get_latest()
    return web.json_response({"weekly": rec, "running": running})


async def weekly_run_api(channel, request: web.Request) -> web.Response:
    """手动触发一次近期回顾（同 hotspot：同步设 inflight 后 bg）。"""
    if not channel._check_auth(request):
        return web.json_response({"error": "Unauthorized"}, status=401)
    venti = channel.state.venti
    if not venti or not channel.state.irminsul or not channel.state.model:
        return web.json_response({"ok": False, "error": "依赖未就绪"}, status=500)
    if venti.is_weekly_running():
        return web.json_response({"ok": False, "error": "已在生成中"})

    venti._weekly_inflight = True

    async def _go():
        from paimon.archons.venti.hotspot import run_weekly_hotspot_collect
        try:
            await run_weekly_hotspot_collect(channel.state)
        except Exception as e:
            logger.exception("[风神·近期回顾] 手动生成异常: {}", e)
        finally:
            venti._weekly_inflight = False
    bg(_go(), label="venti·weekly·webui-manual")
    return web.json_response({"ok": True})


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


async def login_sms_form_api(channel, request: web.Request) -> web.Response:
    """SMS 验证页截图（awaiting_sms 时前端 <img> 指向这里展示给用户参考）。"""
    if not channel._check_auth(request):
        return web.Response(status=401, text="Unauthorized")
    venti = channel.state.venti
    if not venti:
        return web.Response(status=500, text="venti 未就绪")
    session_id = request.match_info.get("session_id", "")
    img = venti.login_sms_form(session_id)
    if not img:
        return web.Response(status=404, text="SMS 表单未生成或会话过期")
    return web.Response(body=img, content_type="image/png", headers={
        "Cache-Control": "no-cache, no-store, must-revalidate",
        "Pragma": "no-cache",
    })


async def login_submit_sms_api(channel, request: web.Request) -> web.Response:
    """用户在 webui 输入验证码 → 转交给 LoginSession.submit_sms。"""
    if not channel._check_auth(request):
        return web.json_response({"error": "Unauthorized"}, status=401)
    venti = channel.state.venti
    if not venti:
        return web.json_response({"ok": False, "error": "风神未就绪"}, status=500)
    session_id = request.match_info.get("session_id", "")
    try:
        data = await request.json()
    except Exception:
        return web.json_response({"ok": False, "error": "JSON 无效"}, status=400)
    code = (data.get("code") or "").strip()
    return web.json_response(venti.login_submit_sms(session_id, code))


def register_routes(app: web.Application, channel: "WebUIChannel") -> None:
    """注册 feed 面板的路由（订阅 + 站点登录）。"""
    app.router.add_get("/feed", lambda r, ch=channel: feed_page(ch, r))
    app.router.add_get("/api/feed/subs", lambda r, ch=channel: feed_subs_list_api(ch, r))
    app.router.add_post("/api/feed/subs", lambda r, ch=channel: feed_subs_create_api(ch, r))
    app.router.add_patch("/api/feed/subs/{sub_id}", lambda r, ch=channel: feed_subs_patch_api(ch, r))
    app.router.add_delete("/api/feed/subs/{sub_id}", lambda r, ch=channel: feed_subs_delete_api(ch, r))
    app.router.add_post("/api/feed/subs/{sub_id}/run", lambda r, ch=channel: feed_subs_run_api(ch, r))
    app.router.add_get("/api/feed/topic_research/{sub_id}", lambda r, ch=channel: feed_topic_research_api(ch, r))
    app.router.add_get("/api/feed/hotspot/today", lambda r, ch=channel: hotspot_today_api(ch, r))
    app.router.add_get("/api/feed/hotspot/list", lambda r, ch=channel: hotspot_list_api(ch, r))
    app.router.add_post("/api/feed/hotspot/run", lambda r, ch=channel: hotspot_run_api(ch, r))
    app.router.add_get("/api/feed/weekly/latest", lambda r, ch=channel: weekly_latest_api(ch, r))
    app.router.add_post("/api/feed/weekly/run", lambda r, ch=channel: weekly_run_api(ch, r))
    # 站点登录扫码
    app.router.add_get("/api/feed/login/overview", lambda r, ch=channel: login_overview_api(ch, r))
    app.router.add_post("/api/feed/login/start", lambda r, ch=channel: login_start_api(ch, r))
    app.router.add_get("/api/feed/login/status/{session_id}", lambda r, ch=channel: login_status_api(ch, r))
    app.router.add_get("/api/feed/login/qr/{session_id}", lambda r, ch=channel: login_qr_api(ch, r))
    app.router.add_get("/api/feed/login/sms-form/{session_id}", lambda r, ch=channel: login_sms_form_api(ch, r))
    app.router.add_post("/api/feed/login/sms/{session_id}", lambda r, ch=channel: login_submit_sms_api(ch, r))
