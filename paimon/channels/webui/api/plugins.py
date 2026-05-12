"""插件面板 API — 空执（skill 生态 + 自进化提案审批）+ 永久授权管理。"""
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
    from paimon.channels.webui.render import render_warm_page
    return web.Response(
        text=render_warm_page(
            title="插件",
            content_template="plugins",
            active="plugins",
            extra_css='<link rel="stylesheet" href="/static/css/plugins.css">',
            extra_js='<script src="/static/js/plugins.js"></script>',
        ),
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
            subject_type, subject_id, actor="空执面板",
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
        "user_feedback": p.user_feedback,
        "revision_count": p.revision_count,
        "revising_at": p.revising_at,
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
    """用户同意提案 → status=approved → 立即调空执 apply 落盘。

    死执 review_verdict='needs_revise' 时 Repo 层会拒绝 approve，返 ok=False。
    apply 失败时 status 仍是 approved（人工介入决定 retry / reject）。
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
        # 先查状态给出准确原因（approve 内部联合三个条件，错误难定位）
        existing = await irminsul.skill_proposal_get(prop_id)
        if existing and existing.revising_at:
            return web.json_response({
                "ok": False,
                "error": "提案正在重写中，请等重写完成再 approve",
            })
        ok = await irminsul.skill_proposal_approve(prop_id, actor="空执面板")
        if not ok:
            return web.json_response({
                "ok": False,
                "error": "提案非 pending 或死执质量审建议修订，无法直接 approve",
            })

        # 同步调空执 apply（用户期望"点同意 = 立刻生效"）
        from paimon.shades.asmoday.apply_proposal import apply_proposal
        skill_registry = channel.state.skill_registry
        if not skill_registry:
            return web.json_response({"ok": False, "error": "skill_registry 未就绪"}, status=500)
        result = await apply_proposal(
            prop_id, irminsul=irminsul, model=channel.state.model,
            skills_dir=skill_registry.skills_dir, actor="空执面板",
        )
        return web.json_response({
            "ok": True,
            "applied": result.ok,
            "skill_name": result.skill_name,
            "apply_error": result.error if not result.ok else "",
        })
    except Exception as e:
        logger.error("[派蒙·WebUI] approve 提案异常: {}", e)
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def plugins_proposal_apply_api(channel: "WebUIChannel", request: web.Request) -> web.Response:
    """重试 apply（status=approved 但落盘失败的提案）。"""
    if channel.require_auth:
        token = request.cookies.get("paimon_token")
        if not token or token not in channel.valid_tokens:
            return web.json_response({"error": "Unauthorized"}, status=401)
    prop_id = request.match_info.get("prop_id", "")
    irminsul = channel.state.irminsul
    if not irminsul or not prop_id:
        return web.json_response({"ok": False, "error": "Not Found"}, status=404)
    try:
        from paimon.shades.asmoday.apply_proposal import apply_proposal
        skill_registry = channel.state.skill_registry
        if not skill_registry:
            return web.json_response({"ok": False, "error": "skill_registry 未就绪"}, status=500)
        result = await apply_proposal(
            prop_id, irminsul=irminsul, model=channel.state.model,
            skills_dir=skill_registry.skills_dir, actor="空执面板",
        )
        return web.json_response({
            "ok": result.ok,
            "skill_name": result.skill_name,
            "error": result.error,
            "skill_dir": result.skill_dir,
        })
    except Exception as e:
        logger.error("[派蒙·WebUI] apply 提案异常: {}", e)
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
        ok = await irminsul.skill_proposal_reject(prop_id, notes, actor="空执面板")
        if not ok:
            return web.json_response({
                "ok": False,
                "error": "提案非 pending，无法 reject",
            })
        return web.json_response({"ok": True})
    except Exception as e:
        logger.error("[派蒙·WebUI] reject 提案异常: {}", e)
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def plugins_proposal_revise_api(channel: "WebUIChannel", request: web.Request) -> web.Response:
    """用户提建议改写提案：写 user_feedback + 后台调生执 revise → 死执重审。

    body: {"feedback": "建议文本（可空）"}
    feedback 为空时退化为「按原内容重审」（用于挽救 verdict 不准的旧提案）。

    返回立刻：ok 表示「已接收并安排后台重写」；用户面板 poll 列表看新版即可。
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
        data = await request.json() if request.body_exists else {}
        feedback = (data.get("feedback") or "").strip()
    except Exception:
        feedback = ""

    # 1. 入库 user_feedback + reset verdict
    try:
        ok = await irminsul.skill_proposal_submit_user_feedback(
            prop_id, feedback, actor="空执面板",
        )
        if not ok:
            return web.json_response({
                "ok": False,
                "error": "提案非 pending（已 approved / rejected / applied），无法 revise",
            })
    except Exception as e:
        logger.error("[派蒙·WebUI] revise 入库异常 prop_id={}: {}", prop_id, e)
        return web.json_response({"ok": False, "error": str(e)}, status=500)

    # 2. 后台调生执 revise + 死执 re-review（fire-and-forget，不阻塞响应）
    model = channel.state.model
    if model:
        import asyncio as _asyncio
        from paimon.shades.naberius.revise import run_revise_and_review_chain
        _asyncio.create_task(
            run_revise_and_review_chain(prop_id, irminsul, model),
            name=f"revise-{prop_id[:8]}",
        )
    else:
        logger.warning("[派蒙·WebUI] revise 已入库但 model 未就绪，无法触发后台重写")

    return web.json_response({
        "ok": True,
        "message": "建议已接收，后台正在重写。刷新列表可看到新版本。",
    })


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
        ok = await irminsul.skill_proposal_delete(prop_id, actor="空执面板")
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
    app.router.add_post("/api/plugins/proposals/{prop_id}/apply", lambda r, ch=channel: plugins_proposal_apply_api(ch, r))
    app.router.add_post("/api/plugins/proposals/{prop_id}/reject", lambda r, ch=channel: plugins_proposal_reject_api(ch, r))
    app.router.add_post("/api/plugins/proposals/{prop_id}/revise", lambda r, ch=channel: plugins_proposal_revise_api(ch, r))
    app.router.add_post("/api/plugins/proposals/{prop_id}/delete", lambda r, ch=channel: plugins_proposal_delete_api(ch, r))
