"""岩神理财面板 - 关注股段（list/add/remove/update/refresh）+ 股票码归一化 helper。"""
from __future__ import annotations

from datetime import date

from typing import TYPE_CHECKING

from aiohttp import web
from loguru import logger

from paimon.foundation.bg import bg

from paimon.channels.webui.channel import PUSH_CHAT_ID

if TYPE_CHECKING:
    from paimon.channels.webui.channel import WebUIChannel


async def wealth_user_watch_list_api(channel, request: web.Request) -> web.Response:
    if not channel._check_auth(request):
        return web.json_response({"error": "Unauthorized"}, status=401)
    irminsul = channel.state.irminsul
    if not irminsul:
        return web.json_response({"items": []})
    entries = await irminsul.user_watch_list()
    items = [await _compute_watch_row(irminsul, e) for e in entries]
    return web.json_response({"items": items})


async def wealth_user_watch_add_api(channel, request: web.Request) -> web.Response:
    if not channel._check_auth(request):
        return web.json_response({"error": "Unauthorized"}, status=401)
    irminsul = channel.state.irminsul
    if not irminsul:
        return web.json_response({"ok": False, "error": "世界树未就绪"}, status=500)
    try:
        data = await request.json()
    except Exception:
        return web.json_response({"ok": False, "error": "JSON 无效"}, status=400)

    code = _normalize_stock_code(data.get("code", ""))
    if not code:
        return web.json_response(
            {"ok": False, "error": "股票代码无效（需 6 位数字，可前缀 sh/sz）"},
            status=400,
        )
    note = (data.get("note") or "").strip()[:200]
    try:
        alert_pct = float(data.get("alert_pct", 3.0))
    except (TypeError, ValueError):
        alert_pct = 3.0
    alert_pct = max(0.1, min(alert_pct, 50.0))

    from paimon.foundation.irminsul import UserWatchEntry
    entry = UserWatchEntry(
        stock_code=code, stock_name="",  # 名称由 zhongli 扫描后补齐
        note=note, added_date=date.today().isoformat(),
        alert_pct=alert_pct,
    )
    added = await irminsul.user_watch_add(entry, actor="WebUI")
    if not added:
        return web.json_response({"ok": False, "error": "股票已在关注列表中"}, status=409)

    # 首次添加后异步补抓 3 年历史 + 最新快照（不阻塞请求）
    if channel.state.zhongli:
        bg(
            channel.state.zhongli.collect_user_watchlist(irminsul),
            label=f"zhongli·关注股·补抓·{code}",
        )

    # ensure 关注股资讯订阅 + task（异步，不阻塞 add 响应）
    from paimon.archons.zhongli.zhongli import ensure_stock_subscriptions
    bg(ensure_stock_subscriptions(
        irminsul, channel.state.march,
        stock_code=code, stock_name="",  # 后续 collect_user_watchlist 补 stock_name 后下次 ensure 会更新 query
        chat_id=PUSH_CHAT_ID, channel_name=channel.name,
    ), label=f"zhongli·股票订阅·ensure·{code}")

    return web.json_response({"ok": True, "code": code})


async def wealth_user_watch_remove_api(channel, request: web.Request) -> web.Response:
    if not channel._check_auth(request):
        return web.json_response({"error": "Unauthorized"}, status=401)
    # USB-007 破坏性操作 server-side 确认（防 CSRF + 误删）
    from paimon.channels.webui.api import check_confirm, confirm_required_response
    if not check_confirm(request):
        return confirm_required_response()
    irminsul = channel.state.irminsul
    if not irminsul:
        return web.json_response({"ok": False, "error": "世界树未就绪"}, status=500)
    try:
        data = await request.json()
    except Exception:
        return web.json_response({"ok": False, "error": "JSON 无效"}, status=400)
    code = _normalize_stock_code(data.get("code", ""))
    if not code:
        return web.json_response({"ok": False, "error": "股票代码无效"}, status=400)
    # 先清关注股资讯订阅（订阅+task），再删 watchlist——避免孤儿订阅
    try:
        from paimon.archons.zhongli.zhongli import clear_stock_subscriptions
        await clear_stock_subscriptions(
            irminsul, channel.state.march, stock_code=code,
        )
    except Exception as e:
        logger.warning(
            "[岩神·关注股订阅] 解绑前 clear 失败 stock={}: {}", code, e,
        )
    ok = await irminsul.user_watch_remove(code, actor="WebUI")
    return web.json_response({"ok": ok})


async def wealth_user_watch_update_api(channel, request: web.Request) -> web.Response:
    if not channel._check_auth(request):
        return web.json_response({"error": "Unauthorized"}, status=401)
    irminsul = channel.state.irminsul
    if not irminsul:
        return web.json_response({"ok": False, "error": "世界树未就绪"}, status=500)
    try:
        data = await request.json()
    except Exception:
        return web.json_response({"ok": False, "error": "JSON 无效"}, status=400)
    code = _normalize_stock_code(data.get("code", ""))
    if not code:
        return web.json_response({"ok": False, "error": "股票代码无效"}, status=400)

    note = data.get("note")
    if note is not None:
        note = str(note).strip()[:200]
    alert_pct = data.get("alert_pct")
    if alert_pct is not None:
        try:
            alert_pct = max(0.1, min(float(alert_pct), 50.0))
        except (TypeError, ValueError):
            alert_pct = None

    ok = await irminsul.user_watch_update(
        code, note=note, alert_pct=alert_pct, actor="WebUI",
    )
    return web.json_response({"ok": ok})


async def wealth_user_watch_refresh_api(channel, request: web.Request) -> web.Response:
    """手动触发关注股抓取（不等晚上 cron）。"""
    if not channel._check_auth(request):
        return web.json_response({"error": "Unauthorized"}, status=401)
    if not channel.state.zhongli or not channel.state.irminsul:
        return web.json_response({"ok": False, "error": "岩神/世界树未就绪"}, status=500)
    bg(
        channel.state.zhongli.collect_user_watchlist(channel.state.irminsul),
        label="zhongli·关注股·手动刷新",
    )
    return web.json_response({"ok": True})


def _normalize_stock_code(raw: str) -> str | None:
    """用户输入 → baostock 格式 'sh.xxxxxx' / 'sz.xxxxxx'。非法返回 None。

    支持：'600519' / 'sh.600519' / 'SH600519' / 'sh600519'。
    6 开头 → sh，其他 → sz（与 provider_baostock._to_bscode 一致）。
    """
    import re as _re
    if not raw:
        return None
    s = raw.strip().lower().replace(".", "").replace(" ", "")
    m = _re.match(r"^(sh|sz)?(\d{6})$", s)
    if not m:
        return None
    prefix, digits = m.group(1), m.group(2)
    if prefix:
        return f"{prefix}.{digits}"
    # 沪市：6/5/9 开头；深市：0/3 开头
    if digits[0] in "659":
        return f"sh.{digits}"
    return f"sz.{digits}"


async def _compute_watch_row(irminsul, entry) -> dict:
    """把 UserWatchEntry 组装成前端展示用 dict（含最新价、sparkline、PE/PB 分位）。"""
    latest = await irminsul.user_watch_price_latest(entry.stock_code)
    recent = await irminsul.user_watch_price_recent(entry.stock_code, 30)
    pe_series = await irminsul.user_watch_price_series(entry.stock_code, "pe")
    pb_series = await irminsul.user_watch_price_series(entry.stock_code, "pb")

    def percentile(series: list[float], cur: float) -> float | None:
        """当前值在序列中的百分位（0~1）。序列空或当前值 ≤0 时返回 None。"""
        if not series or cur <= 0:
            return None
        below = sum(1 for v in series if v < cur)
        return round(below / len(series), 4)

    # 无数据时用 None 让前端渲染 '-'，0 会被前端当成"涨跌 0%"显示成 '0.00%'
    has_data = bool(latest and latest.close > 0)
    return {
        "stock_code": entry.stock_code,
        "stock_name": entry.stock_name,
        "note": entry.note,
        "added_date": entry.added_date,
        "alert_pct": entry.alert_pct,
        "price": latest.close if has_data else None,
        "change_pct": latest.change_pct if has_data else None,
        "pe": latest.pe if has_data else None,
        "pb": latest.pb if has_data else None,
        "pe_percentile": percentile(pe_series, latest.pe if has_data else 0),
        "pb_percentile": percentile(pb_series, latest.pb if has_data else 0),
        "last_date": latest.date if latest else "",
        "sparkline": [p.close for p in recent],
        "history_count": len(pe_series) or 0,
    }


def register_routes(app: web.Application, channel: "WebUIChannel") -> None:
    """注册 wealth_user_watch 面板的 5 个路由。"""
    app.router.add_get("/api/wealth/user_watch", lambda r, ch=channel: wealth_user_watch_list_api(ch, r))
    app.router.add_post("/api/wealth/user_watch/add", lambda r, ch=channel: wealth_user_watch_add_api(ch, r))
    app.router.add_post("/api/wealth/user_watch/remove", lambda r, ch=channel: wealth_user_watch_remove_api(ch, r))
    app.router.add_post("/api/wealth/user_watch/update", lambda r, ch=channel: wealth_user_watch_update_api(ch, r))
    app.router.add_post("/api/wealth/user_watch/refresh", lambda r, ch=channel: wealth_user_watch_refresh_api(ch, r))
