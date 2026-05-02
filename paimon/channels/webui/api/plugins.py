"""插件面板 API — 冰神 skill 列表 + 永久授权管理（撤销）。"""
from __future__ import annotations

from typing import TYPE_CHECKING

from aiohttp import web
from loguru import logger

if TYPE_CHECKING:
    from paimon.channels.webui.channel import WebUIChannel


async def plugins_page(channel: "WebUIChannel", request: web.Request) -> web.Response:
    """渲染插件面板 HTML（未登录跳登录页）。"""
    if channel.require_auth:
        token = request.cookies.get("paimon_token")
        if not token or token not in channel.valid_tokens:
            return web.Response(text=channel._get_login_html(), content_type="text/html")
    from paimon.channels.webui.plugins_html import build_plugins_html
    return web.Response(
        text=build_plugins_html(),
        content_type="text/html",
        headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
    )


async def plugins_skills_api(channel: "WebUIChannel", request: web.Request) -> web.Response:
    """列出所有已加载 skill + 当前授权决策状态（permanent_allow / permanent_deny / None）。"""
    if channel.require_auth:
        token = request.cookies.get("paimon_token")
        if not token or token not in channel.valid_tokens:
            return web.json_response({"error": "Unauthorized"}, status=401)

    registry = channel.state.skill_registry
    cache = channel.state.authz_cache
    skills = []
    if registry:
        for s in registry.list_all():
            authz_decision = cache.get("skill", s.name) if cache else None
            skills.append({
                "name": s.name,
                "description": s.description,
                "triggers": s.triggers,
                "allowed_tools": s.allowed_tools or [],
                "sensitive_tools": getattr(s, "sensitive_tools", []),
                "sensitivity": getattr(s, "sensitivity", "normal"),
                "authz": authz_decision,
            })
    return web.json_response({"skills": skills})


async def plugins_authz_api(channel: "WebUIChannel", request: web.Request) -> web.Response:
    """列出世界树持久化的所有授权记录（含 permanent_allow / permanent_deny）。"""
    if channel.require_auth:
        token = request.cookies.get("paimon_token")
        if not token or token not in channel.valid_tokens:
            return web.json_response({"error": "Unauthorized"}, status=401)

    irminsul = channel.state.irminsul
    if not irminsul:
        return web.json_response({"records": []})
    records = await irminsul.authz_list()
    return web.json_response({
        "records": [
            {
                "id": r.id,
                "subject_type": r.subject_type,
                "subject_id": r.subject_id,
                "decision": r.decision,
                "reason": r.reason,
                "created_at": r.created_at,
                "updated_at": r.updated_at,
            }
            for r in records
        ]
    })


async def plugins_authz_revoke_api(channel: "WebUIChannel", request: web.Request) -> web.Response:
    """撤销一条授权记录并同步清本地 authz_cache，避免悬空决策被消费。"""
    if channel.require_auth:
        token = request.cookies.get("paimon_token")
        if not token or token not in channel.valid_tokens:
            return web.json_response({"error": "Unauthorized"}, status=401)

    try:
        data = await request.json()
        subject_type = data.get("subject_type", "")
        subject_id = data.get("subject_id", "")
        if not subject_type or not subject_id:
            return web.json_response({"ok": False, "error": "缺少 subject_type 或 subject_id"}, status=400)

        irminsul = channel.state.irminsul
        if not irminsul:
            return web.json_response({"ok": False, "error": "世界树未就绪"}, status=500)

        ok = await irminsul.authz_revoke(
            subject_type, subject_id, actor="冰神面板",
        )
        # 同步撤销本地缓存
        if channel.state.authz_cache:
            channel.state.authz_cache.invalidate(subject_type, subject_id)
        return web.json_response({"ok": ok})
    except Exception as e:
        logger.error("[派蒙·WebUI] 撤销授权异常: {}", e)
        return web.json_response({"ok": False, "error": str(e)}, status=500)


def register_routes(app: web.Application, channel: "WebUIChannel") -> None:
    """注册 plugins 面板的 4 个路由（page + 3 个 API）。"""
    app.router.add_get("/plugins", lambda r, ch=channel: plugins_page(ch, r))
    app.router.add_get("/api/plugins/skills", lambda r, ch=channel: plugins_skills_api(ch, r))
    app.router.add_get("/api/plugins/authz", lambda r, ch=channel: plugins_authz_api(ch, r))
    app.router.add_post("/api/plugins/authz/revoke", lambda r, ch=channel: plugins_authz_revoke_api(ch, r))
