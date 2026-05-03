"""草神知识面板 - 知识库段（kb list/read/write/hygiene）。"""
from __future__ import annotations

from typing import TYPE_CHECKING

from aiohttp import web
from loguru import logger

from paimon.foundation.bg import bg

if TYPE_CHECKING:
    from paimon.channels.webui.channel import WebUIChannel


async def knowledge_kb_list_api(channel, request: web.Request) -> web.Response:
    """列知识库条目（带 body_preview + updated_at），按更新时间降序，可选按 category 过滤。"""
    if channel.require_auth:
        token = request.cookies.get("paimon_token")
        if not token or token not in channel.valid_tokens:
            return web.json_response({"error": "Unauthorized"}, status=401)

    irminsul = channel.state.irminsul
    if not irminsul:
        return web.json_response({"items": []})

    category = request.query.get("category", "").strip()
    try:
        items = await irminsul.knowledge_list_detailed(category)
    except Exception as e:
        logger.error("[草神·知识库] 列出异常: {}", e)
        return web.json_response({"error": str(e)}, status=500)
    return web.json_response({"items": items})


async def knowledge_kb_read_api(channel, request: web.Request) -> web.Response:
    """读知识条目全文。"""
    if channel.require_auth:
        token = request.cookies.get("paimon_token")
        if not token or token not in channel.valid_tokens:
            return web.json_response({"error": "Unauthorized"}, status=401)

    category = request.query.get("category", "").strip()
    topic = request.query.get("topic", "").strip()
    if not category or not topic:
        return web.json_response(
            {"error": "缺少 category / topic"}, status=400,
        )

    irminsul = channel.state.irminsul
    if not irminsul:
        return web.json_response({"error": "世界树未就绪"}, status=500)

    try:
        content = await irminsul.knowledge_read(category, topic)
    except Exception as e:
        logger.error("[草神·知识库] 读异常 {}/{}: {}", category, topic, e)
        return web.json_response({"error": str(e)}, status=500)
    if content is None:
        return web.json_response({"error": "未找到"}, status=404)
    return web.json_response({
        "category": category,
        "topic": topic,
        "body": content,
    })


async def knowledge_kb_remember_api(channel, request: web.Request) -> web.Response:
    """知识库新建：自然语言 → LLM 判 category/topic + 冲突检测 → 落 knowledge 域。

    body: {content}
    resp: {ok, action, category, topic, title, target_topic, reason, error?}
    """
    if channel.require_auth:
        token = request.cookies.get("paimon_token")
        if not token or token not in channel.valid_tokens:
            return web.json_response({"error": "Unauthorized"}, status=401)

    from paimon.core.memory_classifier import MAX_REMEMBER_CHARS, remember_knowledge_with_reconcile
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
            logger.warning("[草神·知识] 新建命中敏感串 pattern={} 已拒绝", hit)
            return web.json_response({
                "ok": False,
                "error": f"检测到疑似敏感信息（{hit}）；请勿存储密钥/密码/身份证/银行卡等隐私",
            }, status=400)

        irminsul = channel.state.irminsul
        model = channel.state.model
        if not irminsul or not model:
            return web.json_response({"ok": False, "error": "世界树 / 模型未就绪"}, status=500)

        out = await remember_knowledge_with_reconcile(content, irminsul, model, actor="草神面板")
        if not out.ok:
            return web.json_response({"ok": False, "error": out.error or "写入失败"}, status=500)
        return web.json_response({
            "ok": True,
            "action": out.action,
            "category": out.category,
            "topic": out.topic,
            "title": out.title,
            "target_topic": out.target_topic,
            "reason": out.reason,
        })
    except Exception as e:
        logger.error("[草神·知识] 新建异常: {}", e)
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def knowledge_kb_write_api(channel, request: web.Request) -> web.Response:
    """已知 category/topic 的编辑入口（详情 modal「编辑」按钮用）。

    body: {category, topic, body}
    """
    if channel.require_auth:
        token = request.cookies.get("paimon_token")
        if not token or token not in channel.valid_tokens:
            return web.json_response({"error": "Unauthorized"}, status=401)

    try:
        data = await request.json()
        category = (data.get("category") or "").strip()
        topic = (data.get("topic") or "").strip()
        body = (data.get("body") or "").strip()
        if not category or not topic:
            return web.json_response(
                {"ok": False, "error": "category / topic 不能为空"}, status=400,
            )
        if not body:
            return web.json_response(
                {"ok": False, "error": "body 不能为空"}, status=400,
            )
        # 路径安全（跟 task_workspace.read_artifact 同策略）：category / topic
        # 里禁止 ..、斜杠、反斜杠、null byte——knowledge_write 底层用它们拼文件路径
        for seg_name, seg in (("category", category), ("topic", topic)):
            if ".." in seg or "/" in seg or "\\" in seg or "\x00" in seg:
                return web.json_response(
                    {"ok": False, "error": f"{seg_name} 含非法字符（路径穿越）"},
                    status=400,
                )

        irminsul = channel.state.irminsul
        if not irminsul:
            return web.json_response({"ok": False, "error": "世界树未就绪"}, status=500)

        await irminsul.knowledge_write(category, topic, body, actor="草神面板")
        return web.json_response({"ok": True})
    except Exception as e:
        logger.error("[草神·世界树] 写入知识异常: {}", e)
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def knowledge_kb_delete_api(channel, request: web.Request) -> web.Response:
    if channel.require_auth:
        token = request.cookies.get("paimon_token")
        if not token or token not in channel.valid_tokens:
            return web.json_response({"error": "Unauthorized"}, status=401)
    # USB-007 破坏性操作 server-side 确认
    from paimon.channels.webui.api import check_confirm, confirm_required_response
    if not check_confirm(request):
        return confirm_required_response()

    try:
        data = await request.json()
        category = (data.get("category") or "").strip()
        topic = (data.get("topic") or "").strip()
        if not category or not topic:
            return web.json_response(
                {"ok": False, "error": "缺少 category / topic"}, status=400,
            )
        irminsul = channel.state.irminsul
        if not irminsul:
            return web.json_response({"ok": False, "error": "世界树未就绪"}, status=500)
        ok = await irminsul.knowledge_delete(category, topic, actor="草神面板")
        return web.json_response({"ok": ok})
    except Exception as e:
        logger.error("[草神·知识库] 删除异常: {}", e)
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def knowledge_kb_hygiene_api(channel, request: web.Request) -> web.Response:
    """手动触发知识库整理。后台跑，立即返回；前端轮询 hygiene/status 拿结果。"""
    if channel.require_auth:
        token = request.cookies.get("paimon_token")
        if not token or token not in channel.valid_tokens:
            return web.json_response({"error": "Unauthorized"}, status=401)
    from paimon.core.memory_classifier import run_kb_hygiene, is_kb_hygiene_running
    if is_kb_hygiene_running():
        return web.json_response({"ok": True, "already_running": True})
    irminsul = channel.state.irminsul
    model = channel.state.model
    if not irminsul or not model:
        return web.json_response({"ok": False, "error": "世界树 / 模型未就绪"}, status=500)
    bg(run_kb_hygiene(irminsul, model, trigger="manual"), label="草神·知识库整理·手动")
    return web.json_response({"ok": True, "started": True})


async def knowledge_kb_hygiene_status_api(channel, request: web.Request) -> web.Response:
    """知识库整理：是否在跑 + 最近一次报告。"""
    if channel.require_auth:
        token = request.cookies.get("paimon_token")
        if not token or token not in channel.valid_tokens:
            return web.json_response({"error": "Unauthorized"}, status=401)
    from paimon.core.memory_classifier import is_kb_hygiene_running
    irminsul = channel.state.irminsul
    running = is_kb_hygiene_running()
    last_report = None
    if irminsul:
        try:
            recs = await irminsul.push_archive_list(actor="草神", limit=20)
            for r in recs:
                if (r.source or "").startswith("草神·知识整理"):
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
            logger.debug("[草神·知识整理] 查最近报告失败: {}", e)
    return web.json_response({"running": running, "last_report": last_report})


def register_routes(app: web.Application, channel: "WebUIChannel") -> None:
    """注册 knowledge_kb 面板的 7 个路由。"""
    app.router.add_get("/api/knowledge/kb/list", lambda r, ch=channel: knowledge_kb_list_api(ch, r))
    app.router.add_get("/api/knowledge/kb/read", lambda r, ch=channel: knowledge_kb_read_api(ch, r))
    app.router.add_post("/api/knowledge/kb/remember", lambda r, ch=channel: knowledge_kb_remember_api(ch, r))
    app.router.add_post("/api/knowledge/kb/write", lambda r, ch=channel: knowledge_kb_write_api(ch, r))
    app.router.add_post("/api/knowledge/kb/delete", lambda r, ch=channel: knowledge_kb_delete_api(ch, r))
    app.router.add_post("/api/knowledge/kb/hygiene", lambda r, ch=channel: knowledge_kb_hygiene_api(ch, r))
    app.router.add_get("/api/knowledge/kb/hygiene/status", lambda r, ch=channel: knowledge_kb_hygiene_status_api(ch, r))
