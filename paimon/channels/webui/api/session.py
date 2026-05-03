"""会话管理 API — 列表/切换/新建/删除/停止流式输出。"""
from __future__ import annotations

from typing import TYPE_CHECKING

from aiohttp import web
from loguru import logger

from paimon.channels.webui.channel import PUSH_SESSION_ID

if TYPE_CHECKING:
    from paimon.channels.webui.channel import WebUIChannel


async def get_sessions(channel, request: web.Request) -> web.Response:
    if channel.require_auth:
        token = request.cookies.get("paimon_token")
        if not token or token not in channel.valid_tokens:
            return web.json_response({"error": "Unauthorized"}, status=401)

    session_list = []
    if channel.state.session_mgr:
        for session_id, session in channel.state.session_mgr.sessions.items():
            session_list.append({
                "id": session_id,
                "name": session.name or f"会话 {session_id[:8]}",
                "created_at": getattr(session, "created_at", 0),
            })

    return web.json_response({"sessions": session_list})


async def get_session_messages(channel, request: web.Request) -> web.Response:
    if channel.require_auth:
        token = request.cookies.get("paimon_token")
        if not token or token not in channel.valid_tokens:
            return web.json_response({"error": "Unauthorized"}, status=401)

    session_id = request.match_info["session_id"]
    if not channel.state.session_mgr:
        return web.json_response({"error": "会话管理器未初始化"}, status=500)

    # 前端占位符 'default' → 解析到当前 channel 绑定的真实 session
    # （否则 UI 显示空但后端仍沿用旧 session，造成上下文污染错觉）
    if session_id == "default":
        channel_key = f"{channel.name}:webui-default"
        bound_id = channel.state.session_mgr.bindings.get(channel_key)
        session = channel.state.session_mgr.sessions.get(bound_id) if bound_id else None
        if not session:
            # 没绑定 → 返回空，前端按新会话展示
            return web.json_response({
                "session_id": "default",
                "name": "",
                "messages": [],
                "response_status": "idle",
            })
    else:
        session = channel.state.session_mgr.sessions.get(session_id)
        if not session:
            return web.json_response({"error": "会话不存在"}, status=404)

    # 过滤 session.messages 为 UI 可展示条目：
    # - user 消息：content 非空就展示
    # - assistant 消息：
    #     * 有 tool_calls（不论有无 content）→ 统一显示"调用工具"占位气泡，
    #       忽略 pre-tool narration；避免刷新页面时看到 "pre-tool 文字 + post-tool 文字"
    #       两条 assistant 气泡（LLM 在 tool-loop 里边做边说导致的视觉重复）
    #     * 只有 content → 正常文字气泡
    # - tool 消息隐藏（内部机制）
    messages = []
    for msg in session.messages:
        role = msg.get("role", "")
        if role not in ("user", "assistant"):
            continue
        content = msg.get("content") or ""   # None / 缺失都归一化为空字符串
        if role == "assistant" and msg.get("tool_calls"):
            tool_names = []
            for tc in msg["tool_calls"]:
                fn = tc.get("function") or {}
                n = fn.get("name") or "(未知工具)"
                tool_names.append(n)
            placeholder = f"_🔧 调用工具：{', '.join(tool_names)}_"
            messages.append({"role": role, "content": placeholder})
            continue
        if content.strip():
            messages.append({"role": role, "content": content})

    return web.json_response({
        "session_id": session_id,
        "name": session.name,
        "messages": messages,
        "response_status": session.response_status,
    })


async def new_session(channel, request: web.Request) -> web.Response:
    if channel.require_auth:
        token = request.cookies.get("paimon_token")
        if not token or token not in channel.valid_tokens:
            return web.json_response({"error": "Unauthorized"}, status=401)

    if not channel.state.session_mgr:
        return web.json_response({"error": "会话管理器未初始化"}, status=500)

    new_session = channel.state.session_mgr.create()
    channel_key = f"webui:webui-{new_session.id}"
    channel.state.session_mgr.switch(channel_key, new_session.id)

    return web.json_response({
        "id": new_session.id,
        "name": new_session.name or f"新会话 {new_session.id[:8]}",
    })


async def delete_session(channel, request: web.Request) -> web.Response:
    if channel.require_auth:
        token = request.cookies.get("paimon_token")
        if not token or token not in channel.valid_tokens:
            return web.json_response({"error": "Unauthorized"}, status=401)

    # USB-007 破坏性操作 server-side 确认（防 CSRF）
    from paimon.channels.webui.api import check_confirm, confirm_required_response
    if not check_confirm(request):
        return confirm_required_response()

    session_id = request.match_info["session_id"]
    # 推送收件箱不允许删除（docs/aimon.md §2.6：派蒙独占出口的固定接收点）
    if session_id == PUSH_SESSION_ID:
        return web.json_response(
            {"error": "推送收件箱不可删除"}, status=400,
        )
    if not channel.state.session_mgr:
        return web.json_response({"error": "会话管理器未初始化"}, status=500)

    if session_id not in channel.state.session_mgr.sessions:
        return web.json_response({"error": "会话不存在"}, status=404)

    from paimon.core.chat import stop_session_task
    await stop_session_task(session_id)
    channel.state.session_mgr.delete(session_id)
    return web.json_response({"ok": True})


async def stop_session(channel, request: web.Request) -> web.Response:
    if channel.require_auth:
        token = request.cookies.get("paimon_token")
        if not token or token not in channel.valid_tokens:
            return web.json_response({"error": "Unauthorized"}, status=401)

    try:
        data = await request.json()
        session_id = data.get("session_id")
        if not session_id:
            return web.json_response({"error": "缺少 session_id"}, status=400)

        from paimon.state import state
        if not state.session_mgr:
            return web.json_response({"error": "会话管理器未初始化"}, status=500)

        chat_id = f"webui-{session_id}"
        channel_key = f"webui:{chat_id}"
        backend_session = state.session_mgr.get_current(channel_key)

        if backend_session:
            from paimon.core.chat import stop_session_task
            stopped = await stop_session_task(backend_session.id)
            return web.json_response({"stopped": stopped})
        return web.json_response({"stopped": False})
    except Exception as e:
        logger.error("[派蒙·WebUI] 停止会话异常: {}", e)
        return web.json_response({"error": str(e)}, status=500)


def register_routes(app: web.Application, channel: "WebUIChannel") -> None:
    """注册 session 面板的 5 个路由。"""
    app.router.add_get("/api/sessions", lambda r, ch=channel: get_sessions(ch, r))
    app.router.add_get("/api/sessions/{session_id}/messages", lambda r, ch=channel: get_session_messages(ch, r))
    app.router.add_post("/api/sessions/new", lambda r, ch=channel: new_session(ch, r))
    app.router.add_post("/api/sessions/{session_id}/delete", lambda r, ch=channel: delete_session(ch, r))
    app.router.add_post("/api/sessions/stop", lambda r, ch=channel: stop_session(ch, r))
