"""水神游戏面板 API — 米哈游账号管理 + 签到/便笺/深渊/抽卡/订阅。"""
from __future__ import annotations

from typing import TYPE_CHECKING

from aiohttp import web
from loguru import logger

from paimon.foundation.bg import bg

from paimon.channels.webui.channel import PUSH_CHAT_ID

if TYPE_CHECKING:
    from paimon.channels.webui.channel import WebUIChannel


async def game_page(channel, request: web.Request) -> web.Response:
    if not channel._check_auth(request):
        return web.Response(text=channel._get_login_html(), content_type="text/html")
    from paimon.channels.webui.render import render_warm_page
    return web.Response(
        text=render_warm_page(
            title="游戏",
            content_template="game",
            active="game",
            extra_css=(
                '<link rel="stylesheet" href="/static/css/game.css">\n'
                '<script src="https://cdn.jsdelivr.net/npm/marked/marked.min.js"></script>'
            ),
            extra_js='<script src="/static/js/game.js"></script>',
        ),
        content_type="text/html",
        headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
    )


async def game_overview_api(channel, request: web.Request) -> web.Response:
    if not channel._check_auth(request):
        return web.json_response({"error": "Unauthorized"}, status=401)
    if not channel.state.furina_game:
        return web.json_response({"accounts": []})
    return web.json_response(await channel.state.furina_game.overview())


async def game_qr_create_api(channel, request: web.Request) -> web.Response:
    if not channel._check_auth(request):
        return web.json_response({"error": "Unauthorized"}, status=401)
    if not channel.state.furina_game:
        return web.json_response({"ok": False, "error": "水神未就绪"}, status=500)
    try:
        r = await channel.state.furina_game.qr_create()
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)
    return web.json_response({"ok": True, **r})


async def game_qr_poll_api(channel, request: web.Request) -> web.Response:
    if not channel._check_auth(request):
        return web.json_response({"error": "Unauthorized"}, status=401)
    if not channel.state.furina_game:
        return web.json_response({"stat": "Error", "msg": "水神未就绪"})
    try:
        r = await channel.state.furina_game.qr_poll(
            request.query.get("app_id", "2"),
            request.query.get("ticket", ""),
            request.query.get("device", ""),
        )
    except Exception as e:
        return web.json_response({"stat": "Error", "msg": str(e)})
    # 扫码 confirm 成功后给每个绑定的 (game, uid) ensure 游戏资讯订阅
    # 业务层（channel）持有 chat_id/channel_name，下沉到 furina_game 辅助函数
    if r.get("stat") == "Confirmed" and r.get("bound"):
        from paimon.archons.furina_game import ensure_mihoyo_subscriptions
        for b in r["bound"]:
            try:
                await ensure_mihoyo_subscriptions(
                    channel.state.irminsul, channel.state.march,
                    uid=b["uid"], game=b["game"],
                    chat_id=PUSH_CHAT_ID, channel_name=channel.name,
                )
            except Exception as e:
                logger.warning(
                    "[水神·游戏订阅] ensure 失败 game={} uid={}: {}",
                    b.get("game"), b.get("uid"), e,
                )
    return web.json_response(r)


async def game_unbind_api(channel, request: web.Request) -> web.Response:
    if not channel._check_auth(request):
        return web.json_response({"error": "Unauthorized"}, status=401)
    irminsul = channel.state.irminsul
    if not irminsul:
        return web.json_response({"ok": False, "error": "世界树未就绪"})
    try:
        data = await request.json()
    except Exception:
        return web.json_response({"ok": False, "error": "JSON 无效"}, status=400)
    game = (data.get("game") or "").strip()
    uid = (data.get("uid") or "").strip()
    if game not in ("gs", "sr", "zzz") or not uid:
        return web.json_response({"ok": False, "error": "game/uid 无效"}, status=400)
    # 先清水神游戏订阅（订阅+ScheduledTask），再删账号——避免孤儿订阅
    try:
        from paimon.archons.furina_game import clear_mihoyo_subscriptions
        await clear_mihoyo_subscriptions(
            irminsul, channel.state.march, uid=uid, game=game,
        )
    except Exception as e:
        logger.warning(
            "[水神·游戏订阅] 解绑前 clear 失败 game={} uid={}: {}", game, uid, e,
        )
    ok = await irminsul.mihoyo_account_remove(game, uid, actor="WebUI")
    return web.json_response({"ok": ok})


async def game_sign_api(channel, request: web.Request) -> web.Response:
    if not channel._check_auth(request):
        return web.json_response({"error": "Unauthorized"}, status=401)
    if not channel.state.furina_game:
        return web.json_response({"ok": False, "msg": "水神未就绪"})
    try:
        data = await request.json()
    except Exception:
        return web.json_response({"ok": False, "msg": "JSON 无效"}, status=400)
    r = await channel.state.furina_game.sign_in(data["game"], data["uid"])
    return web.json_response(r)


async def game_sign_all_api(channel, request: web.Request) -> web.Response:
    if not channel._check_auth(request):
        return web.json_response({"error": "Unauthorized"}, status=401)
    if not channel.state.furina_game:
        return web.json_response({"ok": False, "msg": "水神未就绪"})
    results = await channel.state.furina_game.sign_all()
    return web.json_response({"ok": True, "results": results})


async def game_collect_all_api(channel, request: web.Request) -> web.Response:
    if not channel._check_auth(request):
        return web.json_response({"error": "Unauthorized"}, status=401)
    if not channel.state.furina_game:
        return web.json_response({"ok": False, "msg": "水神未就绪"})
    # 异步跑（通常 10~30s，不等它）
    bg(channel.state.furina_game.collect_all(
        march=channel.state.march,
        chat_id=PUSH_CHAT_ID, channel_name=channel.name,
    ), label="furina·游戏全量采集·webui")
    return web.json_response({"ok": True})


async def game_collect_one_api(channel, request: web.Request) -> web.Response:
    """启动 background 采集任务，立即返回。前端拿 status 路由轮询完成。"""
    if not channel._check_auth(request):
        return web.json_response({"error": "Unauthorized"}, status=401)
    if not channel.state.furina_game:
        return web.json_response({"ok": False, "msg": "水神未就绪"})
    try:
        data = await request.json()
    except Exception:
        return web.json_response({"ok": False, "msg": "JSON 无效"}, status=400)
    game = (data.get("game") or "").strip()
    uid = (data.get("uid") or "").strip()
    if game not in ("gs", "sr", "zzz") or not uid:
        return web.json_response({"ok": False, "msg": "game/uid 无效"}, status=400)
    logger.info("[WebUI] /api/game/collect_one POST  game={} uid={}", game, uid)
    r = await channel.state.furina_game.start_collect_one(game, uid)
    return web.json_response(r)


async def game_collect_one_status_api(channel, request: web.Request) -> web.Response:
    """轮询采集任务状态。state ∈ idle/running/done/failed。"""
    if not channel._check_auth(request):
        return web.json_response({"error": "Unauthorized"}, status=401)
    if not channel.state.furina_game:
        return web.json_response({"state": "idle"})
    game = request.query.get("game", "")
    uid = request.query.get("uid", "")
    if not game or not uid:
        return web.json_response({"state": "idle"})
    return web.json_response(channel.state.furina_game.get_collect_state(game, uid))


async def game_abyss_latest_api(channel, request: web.Request) -> web.Response:
    if not channel._check_auth(request):
        return web.json_response({"error": "Unauthorized"}, status=401)
    irminsul = channel.state.irminsul
    if not irminsul:
        return web.json_response({"abyss": None})
    game = request.query.get("game", "gs")
    uid = request.query.get("uid", "")
    abyss_type = request.query.get("type", "spiral")
    # spiral/poetry/stygian=原神三副本；forgotten_hall/pure_fiction/apocalyptic=崩铁三；shiyu/mem=绝区零
    if abyss_type not in ("spiral", "poetry", "stygian",
                          "forgotten_hall", "pure_fiction", "apocalyptic", "peak",
                          "shiyu", "mem", "void"):
        return web.json_response({"error": "type invalid"}, status=400)
    a = await irminsul.mihoyo_abyss_latest(game, uid, abyss_type)
    if not a:
        return web.json_response({"abyss": None})
    return web.json_response({"abyss": {
        "schedule_id": a.schedule_id, "scan_ts": a.scan_ts,
        "max_floor": a.max_floor, "total_star": a.total_star,
        "total_battle": a.total_battle, "total_win": a.total_win,
        "start_time": a.start_time, "end_time": a.end_time,
        # 米游社原 JSON：前端展开看阵容（floors[i].levels[j].battles[k].avatars）
        "raw": a.raw,
    }})


async def game_gacha_sync_api(channel, request: web.Request) -> web.Response:
    """启动后台同步任务，立即返回。前端拿 status 路由轮询进度。"""
    if not channel._check_auth(request):
        return web.json_response({"error": "Unauthorized"}, status=401)
    if not channel.state.furina_game:
        return web.json_response({"ok": False, "msg": "水神未就绪"})
    try:
        data = await request.json()
    except Exception:
        return web.json_response({"ok": False, "msg": "JSON 无效"}, status=400)
    uid = (data.get("uid") or "").strip()
    game = (data.get("game") or "gs").strip()
    if not uid:
        return web.json_response({"ok": False, "msg": "uid 必填"}, status=400)
    logger.info("[WebUI] /api/game/gacha/sync POST  game={} uid={}", game, uid)
    r = await channel.state.furina_game.start_gacha_sync(uid, game=game)
    logger.info("[WebUI] /api/game/gacha/sync 响应  game={} uid={} → {}", game, uid, r)
    return web.json_response(r)


async def game_gacha_import_url_api(channel, request: web.Request) -> web.Response:
    """从用户提供的 URL 导入抽卡（SR 必走，GS/ZZZ 也可作 fallback）。"""
    if not channel._check_auth(request):
        return web.json_response({"error": "Unauthorized"}, status=401)
    if not channel.state.furina_game:
        return web.json_response({"ok": False, "msg": "水神未就绪"})
    try:
        data = await request.json()
    except Exception:
        return web.json_response({"ok": False, "msg": "JSON 无效"}, status=400)
    uid = (data.get("uid") or "").strip()
    game = (data.get("game") or "gs").strip()
    url = (data.get("url") or "").strip()
    if not uid or not url:
        return web.json_response({"ok": False, "msg": "uid 和 url 都必填"}, status=400)
    logger.info(
        "[WebUI] /api/game/gacha/import_url POST  game={} uid={} url_len={}",
        game, uid, len(url),
    )
    r = await channel.state.furina_game.start_gacha_sync_from_url(uid, game, url)
    logger.info(
        "[WebUI] /api/game/gacha/import_url 响应  game={} uid={} → {}",
        game, uid, r,
    )
    return web.json_response(r)


async def game_gacha_sync_status_api(channel, request: web.Request) -> web.Response:
    """轮询同步任务状态。state ∈ idle/running/done/failed。"""
    if not channel._check_auth(request):
        return web.json_response({"error": "Unauthorized"}, status=401)
    if not channel.state.furina_game:
        return web.json_response({"state": "idle"})
    game = request.query.get("game", "gs")
    uid = request.query.get("uid", "")
    if not uid:
        return web.json_response({"state": "idle"})
    return web.json_response(channel.state.furina_game.get_gacha_sync_state(uid, game))


async def game_gacha_stats_api(channel, request: web.Request) -> web.Response:
    if not channel._check_auth(request):
        return web.json_response({"error": "Unauthorized"}, status=401)
    if not channel.state.furina_game:
        return web.json_response({"stats": None})
    game = request.query.get("game", "gs")
    uid = request.query.get("uid", "")
    gacha_type = request.query.get("gacha_type", "301")
    if not uid:
        return web.json_response({"stats": None})
    stats = await channel.state.furina_game.gacha_stats(game, uid, gacha_type)
    return web.json_response({"stats": stats})


async def game_characters_api(channel, request: web.Request) -> web.Response:
    if not channel._check_auth(request):
        return web.json_response({"error": "Unauthorized"}, status=401)
    irminsul = channel.state.irminsul
    if not irminsul:
        return web.json_response({"characters": []})
    game = request.query.get("game", "gs")
    uid = request.query.get("uid", "")
    if not uid:
        return web.json_response({"characters": []})
    chars = await irminsul.mihoyo_character_list(game, uid)
    return web.json_response({"characters": [
        {
            "avatar_id": c.avatar_id, "name": c.name, "element": c.element,
            "rarity": c.rarity, "level": c.level,
            "constellation": c.constellation, "fetter": c.fetter,
            "weapon": c.weapon, "relics": c.relics,
            "icon_url": c.icon_url,
        }
        for c in chars
    ]})


async def game_subscriptions_list_api(channel, request: web.Request) -> web.Response:
    """列水神游戏资讯订阅（binding_kind='mihoyo_game'）。"""
    if not channel._check_auth(request):
        return web.json_response({"error": "Unauthorized"}, status=401)
    irminsul = channel.state.irminsul
    if not irminsul:
        return web.json_response({"subs": []})
    subs = await irminsul.subscription_list_by_binding("mihoyo_game")
    venti = channel.state.venti  # is_running 用于"采集中..."状态
    out = []
    for s in subs:
        game, _, uid = (s.binding_id or "").partition(":")
        item_count = await irminsul.feed_items_count(sub_id=s.id)
        out.append({
            "id": s.id,
            "game": game,
            "uid": uid,
            "query": s.query,
            "schedule_cron": s.schedule_cron,
            "enabled": s.enabled,
            "last_run_at": s.last_run_at,
            "last_error": s.last_error,
            "item_count": item_count,
            "running": bool(venti and venti.is_running(s.id)),
        })
    return web.json_response({"subs": out})


async def game_subscriptions_toggle_api(channel, request: web.Request,
) -> web.Response:
    """启停水神游戏订阅。"""
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
    # 校验是水神订阅，避免越权改 manual
    sub = await irminsul.subscription_get(sub_id)
    if not sub or sub.binding_kind != "mihoyo_game":
        return web.json_response(
            {"ok": False, "error": "非水神游戏订阅"}, status=400,
        )
    await irminsul.subscription_update(
        sub_id, actor="WebUI·游戏面板", enabled=enabled,
    )
    # 同步 march task 的启停（pause/resume）
    if sub.linked_task_id and channel.state.march:
        try:
            if enabled:
                await channel.state.march.resume_task(sub.linked_task_id)
            else:
                await channel.state.march.pause_task(sub.linked_task_id)
        except Exception as e:
            logger.warning(
                "[水神·游戏订阅] 同步 task 启停失败 sub={}: {}", sub_id, e,
            )
    return web.json_response({"ok": True})


async def game_subscriptions_run_api(channel, request: web.Request,
) -> web.Response:
    """立即触发一次水神游戏订阅采集（dispatch 到 venti.collect_subscription）。"""
    if not channel._check_auth(request):
        return web.json_response({"error": "Unauthorized"}, status=401)
    irminsul = channel.state.irminsul
    venti = channel.state.venti
    if not irminsul or not venti:
        return web.json_response({"ok": False, "error": "依赖未就绪"})
    sub_id = request.match_info["sub_id"]
    sub = await irminsul.subscription_get(sub_id)
    if not sub or sub.binding_kind != "mihoyo_game":
        return web.json_response(
            {"ok": False, "error": "非水神游戏订阅"}, status=400,
        )
    # 后台跑（fire-and-forget）；面板轮询 last_run_at 看进度
    # bg() 会在异常时自动 logger.exception，但保留内层 try 保持原日志标签
    async def _run():
        try:
            await venti.collect_subscription(
                sub_id, irminsul=irminsul,
                model=channel.state.model, march=channel.state.march,
            )
        except Exception as e:
            logger.exception(
                "[水神·游戏订阅] 手动触发采集异常 sub={}: {}", sub_id, e,
            )
    bg(_run(), label=f"venti·游戏订阅采集·{sub_id[:8]}·webui")
    return web.json_response({"ok": True, "message": "已触发，稍候刷新"})


# ─── 水神·游戏资讯 + 角色搜索 ─────────────────────────────────

# 走 character skill 跑 LLM 综合，30~60s 慢路径；前端 loading state 即可
_CHAR_RESEARCH_TIMEOUT_S = 180

# game 代号 → 中文名（搜索时拼前缀）
_GAME_DISPLAY = {"gs": "原神", "sr": "崩坏:星穹铁道", "zzz": "绝区零"}


async def game_news_latest_api(channel, request: web.Request) -> web.Response:
    """拉指定 game 的最新一条资讯（覆盖式 mihoyo_game_news 表，每 game 一条）。"""
    if not channel._check_auth(request):
        return web.json_response({"error": "Unauthorized"}, status=401)
    game = (request.query.get("game") or "").strip()
    if not game:
        return web.json_response({"error": "missing game"}, status=400)
    if not channel.state.irminsul:
        return web.json_response({"news": None})
    rec = await channel.state.irminsul.mihoyo_game_news_get(game)
    return web.json_response({"news": rec})


async def game_character_research_api(channel, request: web.Request) -> web.Response:
    """跑 character skill 综合返 markdown。

    body: {"game": "gs", "query": "尼可"}  →  后端拼成 "原神 尼可" 再调 character。
    同步等待 LLM 跑完（30~60s + 主进程 LLM 综合，一般 60~120s 内）。
    """
    if not channel._check_auth(request):
        return web.json_response({"error": "Unauthorized"}, status=401)
    if not channel.state.model:
        return web.json_response({"error": "model 未就绪"}, status=503)
    try:
        data = await request.json()
    except Exception:
        return web.json_response({"error": "invalid JSON"}, status=400)
    game = (data.get("game") or "").strip()
    raw_query = (data.get("query") or "").strip()[:50]
    if not raw_query:
        return web.json_response({"error": "query 必填"}, status=400)

    # 后端自动拼游戏前缀（输入框里用户只输角色名）
    game_name = _GAME_DISPLAY.get(game, "")
    full_query = f"{game_name} {raw_query}".strip() if game_name else raw_query

    logger.info(
        "[水神·角色调研] 开始 game={} raw_query={!r} full_query={!r}",
        game, raw_query, full_query,
    )
    import time as _time
    t0 = _time.time()
    try:
        from paimon.shades._helpers.runner_helpers import invoke_skill_workflow
        markdown = await invoke_skill_workflow(
            skill_name="character",
            user_message=full_query,
            model=channel.state.model,
            session_name=f"game-research-{int(t0)}",
            component="character",
            purpose="character",
            allowed_tools={"exec"},
        )
    except Exception as e:
        logger.error("[水神·角色调研] 调用失败 game={} query={!r} err={}", game, full_query, e)
        return web.json_response({"error": str(e)[:300]}, status=500)
    duration_s = int(_time.time() - t0)
    logger.info(
        "[水神·角色调研] 完成 game={} query={!r} duration={}s len={}",
        game, full_query, duration_s, len(markdown or ""),
    )
    # 覆盖式落库（每 game 一条最新），刷新页面后还能看
    # query 存 raw（不含游戏前缀），方便回填到输入框
    if channel.state.irminsul and game and (markdown or "").strip():
        try:
            await channel.state.irminsul.mihoyo_character_research_upsert(
                game, query=raw_query, markdown=markdown or "", duration_s=duration_s,
            )
        except Exception as e:
            logger.warning("[水神·角色调研] 落库失败 game={} err={}", game, e)
    # 返给前端的 query 用 raw（与缓存读回路径一致；前端只展示用户输入的角色名）
    return web.json_response({
        "markdown": markdown or "",
        "query": raw_query,
        "duration_s": duration_s,
    })


async def game_character_research_latest_api(channel, request: web.Request) -> web.Response:
    """读取最近一次缓存（每 game 一条）。前端进 tab 时拉一次。"""
    if not channel._check_auth(request):
        return web.json_response({"error": "Unauthorized"}, status=401)
    game = (request.query.get("game") or "").strip()
    if not game:
        return web.json_response({"error": "game 必填"}, status=400)
    if not channel.state.irminsul:
        return web.json_response({"research": None})
    rec = await channel.state.irminsul.mihoyo_character_research_get(game)
    return web.json_response({"research": rec})


def register_routes(app: web.Application, channel: "WebUIChannel") -> None:
    """注册 game 面板的 19 个路由。"""
    app.router.add_get("/game", lambda r, ch=channel: game_page(ch, r))
    app.router.add_get("/api/game/overview", lambda r, ch=channel: game_overview_api(ch, r))
    app.router.add_post("/api/game/qr_create", lambda r, ch=channel: game_qr_create_api(ch, r))
    app.router.add_get("/api/game/qr_poll", lambda r, ch=channel: game_qr_poll_api(ch, r))
    app.router.add_post("/api/game/unbind", lambda r, ch=channel: game_unbind_api(ch, r))
    app.router.add_post("/api/game/sign", lambda r, ch=channel: game_sign_api(ch, r))
    app.router.add_post("/api/game/sign_all", lambda r, ch=channel: game_sign_all_api(ch, r))
    app.router.add_post("/api/game/collect_all", lambda r, ch=channel: game_collect_all_api(ch, r))
    app.router.add_post("/api/game/collect_one", lambda r, ch=channel: game_collect_one_api(ch, r))
    app.router.add_get("/api/game/collect_one/status", lambda r, ch=channel: game_collect_one_status_api(ch, r))
    app.router.add_get("/api/game/abyss_latest", lambda r, ch=channel: game_abyss_latest_api(ch, r))
    app.router.add_post("/api/game/gacha/sync", lambda r, ch=channel: game_gacha_sync_api(ch, r))
    app.router.add_post("/api/game/gacha/import_url", lambda r, ch=channel: game_gacha_import_url_api(ch, r))
    app.router.add_get("/api/game/gacha/sync/status", lambda r, ch=channel: game_gacha_sync_status_api(ch, r))
    app.router.add_get("/api/game/gacha/stats", lambda r, ch=channel: game_gacha_stats_api(ch, r))
    app.router.add_get("/api/game/characters", lambda r, ch=channel: game_characters_api(ch, r))
    app.router.add_get("/api/game/subscriptions", lambda r, ch=channel: game_subscriptions_list_api(ch, r))
    app.router.add_post("/api/game/subscriptions/{sub_id}/toggle", lambda r, ch=channel: game_subscriptions_toggle_api(ch, r))
    app.router.add_post("/api/game/subscriptions/{sub_id}/run", lambda r, ch=channel: game_subscriptions_run_api(ch, r))
    app.router.add_get("/api/game/news/latest", lambda r, ch=channel: game_news_latest_api(ch, r))
    app.router.add_post("/api/game/character_research", lambda r, ch=channel: game_character_research_api(ch, r))
    app.router.add_get("/api/game/character_research/latest", lambda r, ch=channel: game_character_research_latest_api(ch, r))
