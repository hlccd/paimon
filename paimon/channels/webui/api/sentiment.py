"""风神舆情看板 API — L1 事件级聚类 + 时间线 + 来源统计。"""
from __future__ import annotations

import time

from typing import TYPE_CHECKING

from aiohttp import web
from loguru import logger

if TYPE_CHECKING:
    from paimon.channels.webui.channel import WebUIChannel


async def sentiment_page(channel, request: web.Request) -> web.Response:
    if not channel._check_auth(request):
        return web.Response(
            text=channel._get_login_html(), content_type="text/html",
        )
    from paimon.channels.webui.sentiment_html import build_sentiment_html
    return web.Response(
        text=build_sentiment_html(),
        content_type="text/html",
        headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
    )


async def sentiment_overview_api(channel, request: web.Request) -> web.Response:
    """近 7 天概览：事件总数 + p0/p1 数 + 情感均值 + 活跃订阅数。

    sub_id 为空时返回全局；指定时返回该订阅的子统计 + 订阅元信息（query / 上次跑 /
    下次跑 / feed_items 总数 / 累计推送数），用于 /sentiment 面板的订阅级 banner。
    """
    if not channel._check_auth(request):
        return web.json_response({"error": "Unauthorized"}, status=401)
    irminsul = channel.state.irminsul
    if not irminsul:
        return web.json_response({
            "events_7d": 0, "p0_count": 0, "p1_count": 0,
            "p0_p1_count": 0, "p2_count": 0, "p3_count": 0,
            "avg_sentiment": 0.0, "sub_count": 0,
        })
    sub_id = request.query.get("sub_id", "").strip() or None
    since = time.time() - 7 * 86400

    events_7d = await irminsul.feed_event_count(since=since, sub_id=sub_id)
    sev = await irminsul.feed_event_count_by_severity(
        since=since, sub_id=sub_id,
    )
    avg = await irminsul.feed_event_avg_sentiment(since=since, sub_id=sub_id)

    result: dict[str, Any] = {
        "events_7d": events_7d,
        "p0_count": sev.get("p0", 0),
        "p1_count": sev.get("p1", 0),
        "p2_count": sev.get("p2", 0),
        "p3_count": sev.get("p3", 0),
        "p0_p1_count": sev.get("p0", 0) + sev.get("p1", 0),
        "avg_sentiment": round(avg, 3),
    }

    if sub_id:
        sub = await irminsul.subscription_get(sub_id)
        if sub:
            # feed_items 累计 / 累计推送 / 上次/下次跑
            feed_items_total = await irminsul.feed_items_count(sub_id=sub_id)
            next_run_at = 0.0
            if sub.linked_task_id:
                try:
                    task = await irminsul.schedule_get(sub.linked_task_id)
                    next_run_at = float(task.next_run_at) if task else 0.0
                except Exception:
                    next_run_at = 0.0
            # 累计推送：所有事件 pushed_count 求和
            events_all = await irminsul.feed_event_list(
                sub_id=sub_id, limit=500,
            )
            pushed_total = sum(int(e.pushed_count or 0) for e in events_all)
            result.update({
                "sub_id": sub.id,
                "sub_query": sub.query,
                "sub_cron": sub.schedule_cron,
                "sub_engine": sub.engine,
                "sub_enabled": bool(sub.enabled),
                "last_run_at": float(sub.last_run_at or 0.0),
                "next_run_at": next_run_at,
                "feed_items_total": feed_items_total,
                "pushed_total": pushed_total,
                "last_error": sub.last_error or "",
            })
    else:
        subs = await irminsul.subscription_list(enabled_only=True)
        result["sub_count"] = len(subs)

    return web.json_response(result)


async def sentiment_events_api(channel, request: web.Request) -> web.Response:
    """事件列表，按 last_seen_at 倒序。

    Query: days (1-30, 默认 7), severity (p0..p3), sub_id, limit (默认 50, 上限 200)
    """
    if not channel._check_auth(request):
        return web.json_response({"error": "Unauthorized"}, status=401)
    irminsul = channel.state.irminsul
    if not irminsul:
        return web.json_response({"events": []})
    try:
        days = max(1, min(int(request.query.get("days", "7")), 30))
    except (TypeError, ValueError):
        days = 7
    severity = request.query.get("severity", "").strip() or None
    if severity and severity not in ("p0", "p1", "p2", "p3"):
        return web.json_response(
            {"error": "severity 必须是 p0/p1/p2/p3 之一"}, status=400,
        )
    sub_id = request.query.get("sub_id", "").strip() or None
    try:
        limit = max(1, min(int(request.query.get("limit", "50")), 200))
    except (TypeError, ValueError):
        limit = 50

    since = time.time() - days * 86400
    events = await irminsul.feed_event_list(
        sub_id=sub_id, since=since, severity=severity, limit=limit,
    )
    return web.json_response({
        "events": [
            {
                "id": ev.id,
                "subscription_id": ev.subscription_id,
                "title": ev.title,
                "summary": ev.summary,
                "severity": ev.severity,
                "sentiment_score": ev.sentiment_score,
                "sentiment_label": ev.sentiment_label,
                "entities": ev.entities,
                "sources": ev.sources,
                "item_count": ev.item_count,
                "first_seen_at": ev.first_seen_at,
                "last_seen_at": ev.last_seen_at,
                "last_pushed_at": ev.last_pushed_at,
                "pushed_count": ev.pushed_count,
            }
            for ev in events
        ]
    })


async def sentiment_event_detail_api(channel, request: web.Request,
) -> web.Response:
    """单事件详情 + 关联 feed_items 列表。"""
    if not channel._check_auth(request):
        return web.json_response({"error": "Unauthorized"}, status=401)
    irminsul = channel.state.irminsul
    if not irminsul:
        return web.json_response({"error": "irminsul 未初始化"}, status=500)
    event_id = request.match_info.get("event_id", "").strip()
    if not event_id:
        return web.json_response({"error": "event_id 必填"}, status=400)
    ev = await irminsul.feed_event_get(event_id)
    if ev is None:
        return web.json_response({"error": "事件不存在"}, status=404)
    items = await irminsul.feed_items_list(event_id=event_id, limit=200)
    return web.json_response({
        "event": {
            "id": ev.id,
            "subscription_id": ev.subscription_id,
            "title": ev.title,
            "summary": ev.summary,
            "entities": ev.entities,
            "timeline": ev.timeline,
            "severity": ev.severity,
            "sentiment_score": ev.sentiment_score,
            "sentiment_label": ev.sentiment_label,
            "sources": ev.sources,
            "item_count": ev.item_count,
            "first_seen_at": ev.first_seen_at,
            "last_seen_at": ev.last_seen_at,
            "last_pushed_at": ev.last_pushed_at,
            "last_severity": ev.last_severity,
            "pushed_count": ev.pushed_count,
        },
        "items": [
            {
                "id": it.id,
                "url": it.url,
                "title": it.title,
                "description": it.description,
                "engine": it.engine,
                "captured_at": it.captured_at,
            }
            for it in items
        ],
    })


async def sentiment_timeline_api(channel, request: web.Request,
) -> web.Response:
    """按天聚合：events 数 / avg_sentiment / p0-p3 计数。"""
    if not channel._check_auth(request):
        return web.json_response({"error": "Unauthorized"}, status=401)
    irminsul = channel.state.irminsul
    if not irminsul:
        return web.json_response({"days": []})
    try:
        days = max(1, min(int(request.query.get("days", "14")), 30))
    except (TypeError, ValueError):
        days = 14
    sub_id = request.query.get("sub_id", "").strip() or None
    timeline = await irminsul.feed_event_timeline(days=days, sub_id=sub_id)
    return web.json_response({"days": timeline})


async def sentiment_sources_api(channel, request: web.Request,
) -> web.Response:
    """信源 Top（按 sources_json flatten 后的域名 count 降序）。"""
    if not channel._check_auth(request):
        return web.json_response({"error": "Unauthorized"}, status=401)
    irminsul = channel.state.irminsul
    if not irminsul:
        return web.json_response({"sources": []})
    try:
        days = max(1, min(int(request.query.get("days", "7")), 30))
    except (TypeError, ValueError):
        days = 7
    try:
        limit = max(1, min(int(request.query.get("limit", "10")), 50))
    except (TypeError, ValueError):
        limit = 10
    sub_id = request.query.get("sub_id", "").strip() or None
    sources = await irminsul.feed_event_sources_top(
        days=days, limit=limit, sub_id=sub_id,
    )
    return web.json_response({"sources": sources})


def register_routes(app: web.Application, channel: "WebUIChannel") -> None:
    """注册 sentiment 面板的 6 个路由。"""
    app.router.add_get("/sentiment", lambda r, ch=channel: sentiment_page(ch, r))
    app.router.add_get("/api/sentiment/overview", lambda r, ch=channel: sentiment_overview_api(ch, r))
    app.router.add_get("/api/sentiment/events", lambda r, ch=channel: sentiment_events_api(ch, r))
    app.router.add_get("/api/sentiment/events/{event_id}", lambda r, ch=channel: sentiment_event_detail_api(ch, r))
    app.router.add_get("/api/sentiment/timeline", lambda r, ch=channel: sentiment_timeline_api(ch, r))
    app.router.add_get("/api/sentiment/sources", lambda r, ch=channel: sentiment_sources_api(ch, r))
