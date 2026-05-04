"""主页/认证/对话路由 — 从主 channel.py 抽离的核心 channel HTTP 入口。

包含：GET / (index 主聊天页) / GET /dashboard / POST /api/auth / POST /api/chat (SSE)。
chat 是流式 SSE 端点，与 channel.send_text / ask_user / _handle_message 紧耦合，
但仍可作 module function（self.X → channel.X 透传）。
"""
from __future__ import annotations

import asyncio
import json
import time
import uuid
from typing import TYPE_CHECKING

from aiohttp import web
from loguru import logger

from paimon.channels.base import IncomingMessage

if TYPE_CHECKING:
    from paimon.channels.webui.channel import WebUIChannel




async def index(channel, request: web.Request) -> web.Response:
    if channel.require_auth:
        token = request.cookies.get("paimon_token")
        if not token or token not in channel.valid_tokens:
            return web.Response(text=channel._get_login_html(), content_type="text/html")

    from paimon.channels.webui.static_html import CHAT_HTML
    return web.Response(
        text=CHAT_HTML,
        content_type="text/html",
        headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
    )


async def dashboard(channel, request: web.Request) -> web.Response:
    if channel.require_auth:
        token = request.cookies.get("paimon_token")
        if not token or token not in channel.valid_tokens:
            return web.Response(text=channel._get_login_html(), content_type="text/html")

    from paimon.channels.webui.dashboard_html import build_dashboard_html
    return web.Response(
        text=build_dashboard_html(),
        content_type="text/html",
        headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
    )


async def auth(channel, request: web.Request) -> web.Response:
    data = await request.json()
    code = data.get("code", "").strip()

    if code == channel.access_code:
        import uuid
        token = str(uuid.uuid4())
        channel.valid_tokens.add(token)
        logger.info("[派蒙·WebUI] 访问验证成功")
        response = web.json_response({"success": True})
        response.set_cookie("paimon_token", token, max_age=86400 * 30)
        return response
    else:
        logger.warning("[派蒙·WebUI] 访问验证失败")
        return web.json_response({"success": False}, status=401)


async def chat(channel, request: web.Request) -> web.StreamResponse:
    if channel.require_auth:
        token = request.cookies.get("paimon_token")
        if not token or token not in channel.valid_tokens:
            return web.json_response({"error": "Unauthorized"}, status=401)

    data = await request.json()
    user_message = data.get("message", "").strip()
    session_id = data.get("session_id", "default")

    logger.info("[派蒙·WebUI] 收到消息 session={} message=\"{}\"", session_id[:8], user_message[:50])

    if not user_message:
        return web.json_response({"error": "Empty message"}, status=400)

    chat_id = f"webui-{session_id}"

    response = web.StreamResponse(
        status=200,
        reason="OK",
        headers={
            "Content-Type": "text/event-stream",
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        },
    )
    await response.prepare(request)

    connection_closed = False
    # watchdog：静默超 WATCHDOG_INTERVAL 秒且未达上限，推一条 thinking
    # 上限到 WATCHDOG_MAX 条后静默（避免刷屏）
    WATCHDOG_INTERVAL = 25.0
    WATCHDOG_MAX = 3
    last_activity_ts = time.time()
    thinking_count = 0

    async def reply(text: str, msg_type: str = "message", *, kind: str = "") -> None:
        nonlocal connection_closed, last_activity_ts, thinking_count
        try:
            payload: dict = {"type": msg_type, "content": text}
            if kind:
                payload["kind"] = kind
            sse_data = json.dumps(payload)
            await response.write(f"data: {sse_data}\n\n".encode())
            # 发送成功才更新活动时间戳；非 thinking 的送达表示真有动作，重置计数
            last_activity_ts = time.time()
            if kind != "thinking":
                thinking_count = 0
            # 持久化 milestone / ack —— 切会话再切回来重渲染时还能保留为小字 hint
            # （否则 SSE 临时帧丢失，user 看到的"之前小字 hint"切回来直接消失）
            # tool / thinking 不持久化（动态进度，下次刷新无意义；且 thinking
            # watchdog 每 25s 一条会污染历史）
            if msg_type == "notice" and kind in ("milestone", "ack"):
                _persist_notice_to_session(text, kind)
        except (ConnectionResetError, ConnectionError, asyncio.CancelledError):
            connection_closed = True
            logger.info("[派蒙·WebUI] SSE连接断开 session={}", session_id[:8])
            raise
        except Exception as e:
            logger.error("[派蒙·WebUI] SSE发送失败: {}", e)
            raise

    def _persist_notice_to_session(text: str, kind: str) -> None:
        """把 milestone/ack notice append 到当前 session.messages 仅 in-memory。

        落盘异步触发（不阻塞 reply）；LLM 调 _build_runtime_messages 时 filter 掉
        非标准 role，不会被喂给模型；前端 /api/sessions/{id}/messages 把这些条目
        一起返回，切会话再切回来重渲染时按 .notice div 展示。
        """
        from paimon.state import state as _state
        from paimon.foundation.bg import bg as _bg
        if not _state.session_mgr:
            return
        sess = _state.session_mgr.get_current(f"{channel.name}:{chat_id}")
        if not sess:
            return
        sess.messages.append({
            "role": "notice", "content": text, "kind": kind,
        })
        try:
            _bg(_state.session_mgr.save_session_async(sess),
                label=f"session·notice·{sess.id[:8]}")
        except Exception as e:
            logger.debug("[派蒙·WebUI·notice 持久化] 落盘失败: {}", e)

    async def _watchdog() -> None:
        """每秒扫描，静默超 25s 且未达上限就推一条 thinking。"""
        nonlocal thinking_count
        while True:
            try:
                await asyncio.sleep(1.0)
            except asyncio.CancelledError:
                return
            if connection_closed:
                return
            elapsed = time.time() - last_activity_ts
            if elapsed >= WATCHDOG_INTERVAL and thinking_count < WATCHDOG_MAX:
                try:
                    await reply(
                        f"…派蒙还在忙，已工作 {int(elapsed)}s…",
                        msg_type="notice",
                        kind="thinking",
                    )
                    thinking_count += 1
                except Exception:
                    return

    # 注册活跃回调，供 ask_user 推送询问
    channel._active_replies[chat_id] = reply

    msg = IncomingMessage(
        channel_name=channel.name,
        chat_id=chat_id,
        text=user_message,
        _reply=reply,
    )

    watchdog_task = asyncio.create_task(_watchdog())
    try:
        try:
            await response.write(
                f'data: {json.dumps({"type": "user", "content": user_message})}\n\n'.encode()
            )
        except Exception:
            connection_closed = True

        from paimon.state import state
        backend_session = None
        if state.session_mgr:
            channel_key = f"webui:{chat_id}"
            backend_session = state.session_mgr.get_current(channel_key)

        try:
            await channel._handle_message(msg)

            if not connection_closed:
                await response.write(f'data: {json.dumps({"type": "done"})}\n\n'.encode())
                logger.info("[派蒙·WebUI] 消息处理完成 session={}", session_id[:8])

        except (ConnectionResetError, ConnectionError, asyncio.CancelledError):
            logger.warning("[派蒙·WebUI] 连接断开 session={}", session_id[:8])
            if backend_session:
                from paimon.core.chat import stop_session_task
                await stop_session_task(backend_session.id)
            return response

        except Exception as e:
            logger.error("[派蒙·WebUI] 处理异常 session={}: {}", session_id[:8], e)
            if not connection_closed:
                try:
                    error_data = json.dumps({"type": "error", "content": str(e)})
                    await response.write(f"data: {error_data}\n\n".encode())
                except Exception:
                    pass

        try:
            await response.write_eof()
        except Exception:
            pass

        return response
    finally:
        # 无论上面走哪条分支（含早退 return / 异常），都清理活跃回调 + 停 watchdog
        channel._active_replies.pop(chat_id, None)
        watchdog_task.cancel()
        try:
            await watchdog_task
        except (asyncio.CancelledError, Exception):
            pass


def register_routes(app: web.Application, channel: "WebUIChannel") -> None:
    """注册主路由 4 个：/ / /dashboard / /api/auth / /api/chat。"""
    app.router.add_get("/", lambda r, ch=channel: index(ch, r))
    app.router.add_get("/dashboard", lambda r, ch=channel: dashboard(ch, r))
    app.router.add_post("/api/auth", lambda r, ch=channel: auth(ch, r))
    app.router.add_post("/api/chat", lambda r, ch=channel: chat(ch, r))
