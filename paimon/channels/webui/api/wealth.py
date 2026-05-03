"""岩神理财面板 - 主数据段（page + 推荐/排行/变化/触发扫描）+ snapshot 序列化 helper。"""
from __future__ import annotations

from typing import TYPE_CHECKING

from aiohttp import web
from loguru import logger

from paimon.foundation.bg import bg

from paimon.channels.webui.channel import PUSH_CHAT_ID

if TYPE_CHECKING:
    from paimon.channels.webui.channel import WebUIChannel


async def wealth_page(channel, request: web.Request) -> web.Response:
    if not channel._check_auth(request):
        return web.Response(text=channel._get_login_html(), content_type="text/html")
    from paimon.channels.webui.wealth_html import build_wealth_html
    return web.Response(
        text=build_wealth_html(),
        content_type="text/html",
        headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
    )


async def wealth_stats_api(channel, request: web.Request) -> web.Response:
    if not channel._check_auth(request):
        return web.json_response({"error": "Unauthorized"}, status=401)
    irminsul = channel.state.irminsul
    march = channel.state.march
    if not irminsul:
        return web.json_response({
            "watchlist_count": 0, "latest_scan_date": None,
            "changes_7d": 0, "p0_count_7d": 0, "p1_count_7d": 0,
            "cron_enabled": False,
        })
    wl = await irminsul.watchlist_get()
    latest = await irminsul.snapshot_latest_date()
    changes = await irminsul.change_recent(7)
    cron_on = False
    if march:
        tasks = await march.list_tasks()
        # 方案 D：按 task_type 分类（原 task_prompt.startswith("[DIVIDEND_SCAN] ") 2026-04-29 废弃）
        cron_on = any(
            t.task_type == "dividend_scan" and t.enabled
            for t in tasks
        )
    # 近 7 天 P0 / P1 事件累计：从 push_archive(actor="岩神") 的 extra 读 p0/p1_count
    import time as _time
    p0_total = 0
    p1_total = 0
    try:
        recent = await irminsul.push_archive_list(
            actor="岩神",
            since=_time.time() - 7 * 86400,
            limit=50,
        )
        for rec in recent:
            p0_total += int((rec.extra or {}).get("p0_count", 0) or 0)
            p1_total += int((rec.extra or {}).get("p1_count", 0) or 0)
    except Exception as e:
        logger.debug("[WebUI·wealth_stats] 查 P0/P1 失败: {}", e)
    return web.json_response({
        "watchlist_count": len(wl),
        "latest_scan_date": latest,
        "changes_7d": len(changes),
        "p0_count_7d": p0_total,
        "p1_count_7d": p1_total,
        "cron_enabled": cron_on,
    })


async def wealth_recommended_api(channel, request: web.Request) -> web.Response:
    if not channel._check_auth(request):
        return web.json_response({"error": "Unauthorized"}, status=401)
    irminsul = channel.state.irminsul
    if not irminsul:
        return web.json_response({"stocks": []})
    rows = await irminsul.snapshot_latest_for_watchlist()
    return web.json_response({"stocks": [_snap_to_dict(r) for r in rows]})


async def wealth_ranking_api(channel, request: web.Request) -> web.Response:
    if not channel._check_auth(request):
        return web.json_response({"error": "Unauthorized"}, status=401)
    irminsul = channel.state.irminsul
    if not irminsul:
        return web.json_response({"stocks": []})
    try:
        n = max(1, min(int(request.query.get("n", "100")), 200))
    except (TypeError, ValueError):
        n = 100
    rows = await irminsul.snapshot_latest_top(n)
    return web.json_response({"stocks": [_snap_to_dict(r) for r in rows]})


async def wealth_changes_api(channel, request: web.Request) -> web.Response:
    if not channel._check_auth(request):
        return web.json_response({"error": "Unauthorized"}, status=401)
    irminsul = channel.state.irminsul
    if not irminsul:
        return web.json_response({"changes": []})
    try:
        days = max(1, min(int(request.query.get("days", "30")), 180))
    except (TypeError, ValueError):
        days = 30
    chs = await irminsul.change_recent(days)
    return web.json_response({
        "changes": [
            {
                "id": c.id,
                "event_date": c.event_date,
                "stock_code": c.stock_code,
                "stock_name": c.stock_name,
                "event_type": c.event_type,
                "old_value": c.old_value,
                "new_value": c.new_value,
                "description": c.description,
            }
            for c in chs
        ]
    })


async def wealth_stock_api(channel, request: web.Request) -> web.Response:
    if not channel._check_auth(request):
        return web.json_response({"error": "Unauthorized"}, status=401)
    irminsul = channel.state.irminsul
    if not irminsul:
        return web.json_response({"history": [], "current": None})
    code = request.match_info["code"]
    import re as _re
    if not _re.fullmatch(r"\d{6}", code):
        return web.json_response({"error": "股票代码必须是 6 位数字"}, status=400)
    try:
        days = max(1, min(int(request.query.get("days", "90")), 365))
    except (TypeError, ValueError):
        days = 90
    history = await irminsul.snapshot_history(code, days)
    current = history[-1] if history else None
    return web.json_response({
        "history": [_snap_to_dict(h) for h in history],
        "current": _snap_to_dict(current) if current else None,
    })


async def wealth_trigger_api(channel, request: web.Request) -> web.Response:
    if not channel._check_auth(request):
        return web.json_response({"error": "Unauthorized"}, status=401)
    # USB-001：拆分 "三个未就绪" 让 user 知道具体哪个有问题怎么修
    missing = []
    if not channel.state.zhongli:
        missing.append("岩神（理财服务，启动时配置 LLM 后才会就绪）")
    if not channel.state.irminsul:
        missing.append("世界树（持久化层，检查 .paimon/irminsul.db 写权限）")
    if not channel.state.march:
        missing.append("三月（调度器，启动失败请看 paimon 日志）")
    if missing:
        return web.json_response(
            {"ok": False, "error": "未就绪：" + " / ".join(missing)},
            status=500,
        )
    try:
        data = await request.json()
        mode = (data.get("mode") or "").strip()
    except Exception:
        return web.json_response({"ok": False, "error": "JSON 无效"}, status=400)
    if mode not in ("full", "daily", "rescore"):
        return web.json_response({"ok": False, "error": "mode 必须是 full/daily/rescore"}, status=400)

    # 防并发：正在跑时拒绝，避免 full_scan 15 分钟内被多次触发排队
    if channel.state.zhongli.is_scanning():
        return web.json_response(
            {"ok": False, "error": "已有扫描在进行中，请等待完成后再触发"},
            status=409,
        )

    bg(channel.state.zhongli.collect_dividend(
        mode=mode,
        irminsul=channel.state.irminsul,
        march=channel.state.march,
        chat_id=PUSH_CHAT_ID,   # 同文件顶部的常量
        channel_name=channel.name,
    ), label=f"zhongli·红利股·{mode}·webui")
    return web.json_response({"ok": True, "mode": mode})


async def wealth_running_api(channel, request: web.Request) -> web.Response:
    """岩神采集是否在跑（供 /wealth 公告区"采集中"状态条 + 轮询）。

    progress 字段（仅在 running=true 时有意义）：
    ``{stage, cur, total, started_at, updated_at, ...stage特有字段}``
    - stage ∈ init / board / board_codes / dividend / financial /
      scoring_dividend / scoring_financial / scoring_rescore
    - 前端按 stage 拼"行情扫描 X/Y"等文案

    last_error 字段（10 分钟内的最近一次失败，超出窗口为 null）：
    ``{ts, mode, message, age_seconds}`` —— 前端红色横幅显示
    """
    if not channel._check_auth(request):
        return web.json_response({"error": "Unauthorized"}, status=401)
    zhongli = channel.state.zhongli
    running = bool(zhongli and zhongli.is_scanning())
    progress = zhongli.get_progress() if (zhongli and running) else None
    last_error = zhongli.get_last_error() if zhongli else None
    return web.json_response({
        "running": running,
        "progress": progress,
        "last_error": last_error,
    })


async def wealth_scan_scope_api(channel, request: web.Request) -> web.Response:
    """各扫描模式的实际范围数量（给前端按钮下方文案用）。

    candidates_size: 候选池股票数（最近一次全扫描产出，日更扫描的范围）
    watchlist_size:  推荐池股票数（行业均衡选出，公告聚焦对象）
    full_market_size: 全市场参考数（A 股 ~5500，写死方便前端展示）
    """
    if not channel._check_auth(request):
        return web.json_response({"error": "Unauthorized"}, status=401)
    irminsul = channel.state.irminsul
    if not irminsul:
        return web.json_response({
            "candidates_size": 0, "watchlist_size": 0,
            "full_market_size": 5500,
        })
    # 候选池 = 最近一次全扫描产出的 codes（用 watchlist.last_refresh 当基准）
    last_full_date = await irminsul.watchlist_last_refresh()
    candidates = (
        await irminsul.snapshot_codes_at_date(last_full_date)
        if last_full_date else []
    )
    watchlist = await irminsul.watchlist_get()
    return web.json_response({
        "candidates_size": len(candidates),
        "watchlist_size": len(watchlist),
        "full_market_size": 5500,
    })


def _snap_to_dict(s) -> dict:
    """ScoreSnapshot → JSON 可序列化 dict。"""
    return {
        "id": s.id,
        "scan_date": s.scan_date,
        "stock_code": s.stock_code,
        "stock_name": s.stock_name,
        "industry": s.industry,
        "total_score": s.total_score,
        "sustainability_score": s.sustainability_score,
        "fortress_score": s.fortress_score,
        "valuation_score": s.valuation_score,
        "track_record_score": s.track_record_score,
        "momentum_score": s.momentum_score,
        "penalty": s.penalty,
        "dividend_yield": s.dividend_yield,
        "pe": s.pe,
        "pb": s.pb,
        "roe": s.roe,
        "market_cap": s.market_cap,
        "reasons": s.reasons,
        "advice": s.advice,
    }


def register_routes(app: web.Application, channel: "WebUIChannel") -> None:
    """注册 wealth 面板的 9 个路由。"""
    app.router.add_get("/wealth", lambda r, ch=channel: wealth_page(ch, r))
    app.router.add_get("/api/wealth/stats", lambda r, ch=channel: wealth_stats_api(ch, r))
    app.router.add_get("/api/wealth/recommended", lambda r, ch=channel: wealth_recommended_api(ch, r))
    app.router.add_get("/api/wealth/ranking", lambda r, ch=channel: wealth_ranking_api(ch, r))
    app.router.add_get("/api/wealth/changes", lambda r, ch=channel: wealth_changes_api(ch, r))
    app.router.add_get("/api/wealth/stock/{code}", lambda r, ch=channel: wealth_stock_api(ch, r))
    app.router.add_post("/api/wealth/trigger", lambda r, ch=channel: wealth_trigger_api(ch, r))
    app.router.add_get("/api/wealth/running", lambda r, ch=channel: wealth_running_api(ch, r))
    app.router.add_get("/api/wealth/scan_scope", lambda r, ch=channel: wealth_scan_scope_api(ch, r))
