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


# ─────────────────────────────────────────────────────────────────────────────
# Skill 自进化提案（域 16）
# ─────────────────────────────────────────────────────────────────────────────

def _proposal_to_dict(p) -> dict:
    return {
        "id": p.id,
        "name": p.name,
        "kind": p.kind,
        "target_skill": p.target_skill,
        "description": p.description,
        "triggers": p.triggers,
        "system_prompt": p.system_prompt,
        "allowed_tools": p.allowed_tools or [],
        "rationale": p.rationale,
        "proposed_by_session": p.proposed_by_session,
        "proposed_by_task": p.proposed_by_task,
        "review_verdict": p.review_verdict,
        "review_notes": p.review_notes,
        "status": p.status,
        "decided_by": p.decided_by,
        "decision_notes": p.decision_notes,
        "decided_at": p.decided_at,
        "applied_at": p.applied_at,
        "created_at": p.created_at,
        "updated_at": p.updated_at,
    }


async def plugins_proposals_list_api(channel: "WebUIChannel", request: web.Request) -> web.Response:
    """列出 skill 提案。?status=pending|approved|rejected|applied 过滤。默认全部。"""
    if channel.require_auth:
        token = request.cookies.get("paimon_token")
        if not token or token not in channel.valid_tokens:
            return web.json_response({"error": "Unauthorized"}, status=401)
    irminsul = channel.state.irminsul
    if not irminsul:
        return web.json_response({"proposals": [], "counts": {}})
    status = request.query.get("status") or None
    rows = await irminsul.skill_proposal_list(status=status, limit=200)
    # SQL COUNT GROUP BY 一次拿全 status 计数（角标用，不会随 limit 截断）
    counts = await irminsul.skill_proposal_count_by_status()
    return web.json_response({
        "proposals": [_proposal_to_dict(p) for p in rows],
        "counts": counts,
    })


async def plugins_proposal_get_api(channel: "WebUIChannel", request: web.Request) -> web.Response:
    """单条提案详情（含 system_prompt 全文）。"""
    if channel.require_auth:
        token = request.cookies.get("paimon_token")
        if not token or token not in channel.valid_tokens:
            return web.json_response({"error": "Unauthorized"}, status=401)
    prop_id = request.match_info.get("prop_id", "")
    irminsul = channel.state.irminsul
    if not irminsul or not prop_id:
        return web.json_response({"error": "Not Found"}, status=404)
    p = await irminsul.skill_proposal_get(prop_id)
    if not p:
        return web.json_response({"error": "Not Found"}, status=404)
    return web.json_response({"proposal": _proposal_to_dict(p)})


async def plugins_proposal_approve_api(channel: "WebUIChannel", request: web.Request) -> web.Response:
    """用户同意提案 → status=approved（等冰神 apply 落盘）。

    死执 review_verdict='needs_revise' 时 Repo 层会拒绝，前端会收到 ok=False。
    """
    if channel.require_auth:
        token = request.cookies.get("paimon_token")
        if not token or token not in channel.valid_tokens:
            return web.json_response({"error": "Unauthorized"}, status=401)
    prop_id = request.match_info.get("prop_id", "")
    irminsul = channel.state.irminsul
    if not irminsul or not prop_id:
        return web.json_response({"ok": False, "error": "Not Found"}, status=404)
    try:
        ok = await irminsul.skill_proposal_approve(prop_id, actor="冰神面板")
        if not ok:
            return web.json_response({
                "ok": False,
                "error": "提案非 pending 或死执质量审建议修订，无法直接 approve",
            })
        return web.json_response({"ok": True})
    except Exception as e:
        logger.error("[派蒙·WebUI] approve 提案异常: {}", e)
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def plugins_proposal_reject_api(channel: "WebUIChannel", request: web.Request) -> web.Response:
    """用户拒绝提案。可选 notes 字段记原因。"""
    if channel.require_auth:
        token = request.cookies.get("paimon_token")
        if not token or token not in channel.valid_tokens:
            return web.json_response({"error": "Unauthorized"}, status=401)
    prop_id = request.match_info.get("prop_id", "")
    irminsul = channel.state.irminsul
    if not irminsul or not prop_id:
        return web.json_response({"ok": False, "error": "Not Found"}, status=404)
    try:
        data = await request.json() if request.body_exists else {}
        notes = (data.get("notes") or "").strip()
    except Exception:
        notes = ""
    try:
        ok = await irminsul.skill_proposal_reject(prop_id, notes, actor="冰神面板")
        if not ok:
            return web.json_response({
                "ok": False,
                "error": "提案非 pending，无法 reject",
            })
        return web.json_response({"ok": True})
    except Exception as e:
        logger.error("[派蒙·WebUI] reject 提案异常: {}", e)
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def plugins_proposal_delete_api(channel: "WebUIChannel", request: web.Request) -> web.Response:
    """彻底删除提案（仅允许 rejected；applied 是已落盘 skill 的依据，禁删）。"""
    if channel.require_auth:
        token = request.cookies.get("paimon_token")
        if not token or token not in channel.valid_tokens:
            return web.json_response({"error": "Unauthorized"}, status=401)
    prop_id = request.match_info.get("prop_id", "")
    irminsul = channel.state.irminsul
    if not irminsul or not prop_id:
        return web.json_response({"ok": False, "error": "Not Found"}, status=404)
    try:
        ok = await irminsul.skill_proposal_delete(prop_id, actor="冰神面板")
        return web.json_response({"ok": ok})
    except Exception as e:
        logger.error("[派蒙·WebUI] delete 提案异常: {}", e)
        return web.json_response({"ok": False, "error": str(e)}, status=500)


def register_routes(app: web.Application, channel: "WebUIChannel") -> None:
    """注册 plugins 面板路由（page + skills/authz API + proposals API）。"""
    app.router.add_get("/plugins", lambda r, ch=channel: plugins_page(ch, r))
    app.router.add_get("/api/plugins/skills", lambda r, ch=channel: plugins_skills_api(ch, r))
    app.router.add_get("/api/plugins/authz", lambda r, ch=channel: plugins_authz_api(ch, r))
    app.router.add_post("/api/plugins/authz/revoke", lambda r, ch=channel: plugins_authz_revoke_api(ch, r))
    # 自进化提案
    app.router.add_get("/api/plugins/proposals", lambda r, ch=channel: plugins_proposals_list_api(ch, r))
    app.router.add_get("/api/plugins/proposals/{prop_id}", lambda r, ch=channel: plugins_proposal_get_api(ch, r))
    app.router.add_post("/api/plugins/proposals/{prop_id}/approve", lambda r, ch=channel: plugins_proposal_approve_api(ch, r))
    app.router.add_post("/api/plugins/proposals/{prop_id}/reject", lambda r, ch=channel: plugins_proposal_reject_api(ch, r))
    app.router.add_post("/api/plugins/proposals/{prop_id}/delete", lambda r, ch=channel: plugins_proposal_delete_api(ch, r))
