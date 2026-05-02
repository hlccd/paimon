"""草神知识面板 - 记忆段（记忆 list/remember/delete/hygiene）。"""
from __future__ import annotations

from typing import TYPE_CHECKING

from aiohttp import web
from loguru import logger

from paimon.foundation.bg import bg

if TYPE_CHECKING:
    from paimon.channels.webui.channel import WebUIChannel


async def knowledge_page(channel, request: web.Request) -> web.Response:
    if channel.require_auth:
        token = request.cookies.get("paimon_token")
        if not token or token not in channel.valid_tokens:
            return web.Response(text=channel._get_login_html(), content_type="text/html")

    from paimon.channels.webui.knowledge_html import build_knowledge_html
    return web.Response(
        text=build_knowledge_html(),
        content_type="text/html",
        headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
    )


async def knowledge_memory_list_api(channel, request: web.Request) -> web.Response:
    """列 L1 记忆（user / feedback / project / reference 四类），含完整 body 和 preview。"""
    if channel.require_auth:
        token = request.cookies.get("paimon_token")
        if not token or token not in channel.valid_tokens:
            return web.json_response({"error": "Unauthorized"}, status=401)

    mem_type = request.query.get("mem_type", "").strip()
    if mem_type not in ("user", "feedback", "project", "reference"):
        return web.json_response(
            {"error": "mem_type 必须是 user / feedback / project / reference"},
            status=400,
        )

    irminsul = channel.state.irminsul
    if not irminsul:
        return web.json_response({"items": []})

    try:
        metas = await irminsul.memory_list(mem_type=mem_type, limit=200)
    except Exception as e:
        logger.error("[草神·智识] 列记忆异常 type={}: {}", mem_type, e)
        return web.json_response({"error": str(e)}, status=500)

    items = []
    for meta in metas:
        try:
            mem = await irminsul.memory_get(meta.id)
        except Exception:
            continue
        if mem is None:
            continue
        body = mem.body or ""
        preview = body if len(body) <= 200 else body[:200].rstrip() + "..."
        items.append({
            "id": mem.id,
            "mem_type": mem.mem_type,
            "subject": mem.subject,
            "title": mem.title,
            "body": body,
            "body_preview": preview,
            "source": mem.source,
            "tags": mem.tags,
            "created_at": mem.created_at,
            "updated_at": mem.updated_at,
        })
    return web.json_response({"items": items})


async def knowledge_memory_remember_api(channel, request: web.Request) -> web.Response:
    """记忆新建：自然语言 → LLM 分类 → 冲突检测 → 落 memory 域。

    body: {content}
    resp: {ok, action, mem_type, subject, title, id, target_id, target_title, reason, error?}
    """
    if channel.require_auth:
        token = request.cookies.get("paimon_token")
        if not token or token not in channel.valid_tokens:
            return web.json_response({"error": "Unauthorized"}, status=401)

    from paimon.core.memory_classifier import MAX_REMEMBER_CHARS, remember_with_reconcile
    from paimon.core.safety import detect_sensitive

    try:
        data = await request.json()
        content = (data.get("content") or "").strip()
        if not content:
            return web.json_response({"ok": False, "error": "内容不能为空"}, status=400)
        if len(content) > MAX_REMEMBER_CHARS:
            return web.json_response(
                {"ok": False, "error": f"内容过长（{len(content)} 字），上限 {MAX_REMEMBER_CHARS} 字"},
                status=400,
            )
        hit = detect_sensitive(content)
        if hit:
            logger.warning("[草神·记忆] 新建命中敏感串 pattern={} 已拒绝", hit)
            return web.json_response({
                "ok": False,
                "error": f"检测到疑似敏感信息（{hit}）；请勿存储密钥/密码/身份证/银行卡等隐私",
            }, status=400)

        irminsul = channel.state.irminsul
        model = channel.state.model
        if not irminsul or not model:
            return web.json_response({"ok": False, "error": "世界树 / 模型未就绪"}, status=500)

        out = await remember_with_reconcile(content, irminsul, model, source="草神面板·手动", actor="草神面板")
        if not out.ok:
            return web.json_response({"ok": False, "error": out.error or "写入失败"}, status=500)
        return web.json_response({
            "ok": True,
            "action": out.action,
            "mem_type": out.mem_type,
            "subject": out.subject,
            "title": out.title,
            "id": out.mem_id,
            "target_id": out.target_id,
            "target_title": out.target_title,
            "reason": out.reason,
        })
    except Exception as e:
        logger.error("[草神·记忆] 新建异常: {}", e)
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def knowledge_memory_delete_api(channel, request: web.Request) -> web.Response:
    if channel.require_auth:
        token = request.cookies.get("paimon_token")
        if not token or token not in channel.valid_tokens:
            return web.json_response({"error": "Unauthorized"}, status=401)

    try:
        data = await request.json()
        mem_id = (data.get("id") or "").strip()
        if not mem_id:
            return web.json_response({"ok": False, "error": "缺少 id"}, status=400)

        irminsul = channel.state.irminsul
        if not irminsul:
            return web.json_response({"ok": False, "error": "世界树未就绪"}, status=500)

        ok = await irminsul.memory_delete(mem_id, actor="草神面板")
        return web.json_response({"ok": ok})
    except Exception as e:
        logger.error("[草神·世界树] 删除记忆异常: {}", e)
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def knowledge_memory_hygiene_api(channel, request: web.Request) -> web.Response:
    """手动触发记忆整理。后台跑，立即返回 {ok, already_running?}。
    结果经 push_archive 归档，前端轮询 hygiene/status 拿状态。
    """
    if channel.require_auth:
        token = request.cookies.get("paimon_token")
        if not token or token not in channel.valid_tokens:
            return web.json_response({"error": "Unauthorized"}, status=401)

    from paimon.core.memory_classifier import run_hygiene, is_hygiene_running

    if is_hygiene_running():
        return web.json_response({"ok": True, "already_running": True})

    irminsul = channel.state.irminsul
    model = channel.state.model
    if not irminsul or not model:
        return web.json_response({"ok": False, "error": "世界树 / 模型未就绪"}, status=500)

    # fire-and-forget 后台跑；前端用 status 轮询
    bg(run_hygiene(irminsul, model, trigger="manual"), label="草神·记忆整理·手动")
    return web.json_response({"ok": True, "started": True})


async def knowledge_memory_hygiene_status_api(channel, request: web.Request) -> web.Response:
    """前端用：是否在跑 + 最近一次报告（从 push_archive 拉）。"""
    if channel.require_auth:
        token = request.cookies.get("paimon_token")
        if not token or token not in channel.valid_tokens:
            return web.json_response({"error": "Unauthorized"}, status=401)

    from paimon.core.memory_classifier import is_hygiene_running

    irminsul = channel.state.irminsul
    running = is_hygiene_running()
    last_report = None
    if irminsul:
        try:
            recs = await irminsul.push_archive_list(actor="草神", limit=10)
            # 找出 source 以"草神·记忆整理"开头的最新一条
            for r in recs:
                if (r.source or "").startswith("草神·记忆整理"):
                    last_report = {
                        "id": r.id,
                        "created_at": r.created_at,
                        "source": r.source,
                        "message": r.message_md,
                        "merged": (r.extra or {}).get("merged", 0),
                        "deleted": (r.extra or {}).get("deleted", 0),
                    }
                    break
        except Exception as e:
            logger.debug("[草神·整理] 查最近报告失败: {}", e)
    return web.json_response({"running": running, "last_report": last_report})


def register_routes(app: web.Application, channel: "WebUIChannel") -> None:
    """注册 knowledge 面板的 6 个路由。"""
    app.router.add_get("/knowledge", lambda r, ch=channel: knowledge_page(ch, r))
    app.router.add_get("/api/knowledge/memory/list", lambda r, ch=channel: knowledge_memory_list_api(ch, r))
    app.router.add_post("/api/knowledge/memory/remember", lambda r, ch=channel: knowledge_memory_remember_api(ch, r))
    app.router.add_post("/api/knowledge/memory/delete", lambda r, ch=channel: knowledge_memory_delete_api(ch, r))
    app.router.add_post("/api/knowledge/memory/hygiene", lambda r, ch=channel: knowledge_memory_hygiene_api(ch, r))
    app.router.add_get("/api/knowledge/memory/hygiene/status", lambda r, ch=channel: knowledge_memory_hygiene_status_api(ch, r))
