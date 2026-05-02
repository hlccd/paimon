"""权限询问答复 API — 天使路径 ask_user 闭环（不经 /api/chat 流程）。"""
from __future__ import annotations

from typing import TYPE_CHECKING

from aiohttp import web
from loguru import logger

if TYPE_CHECKING:
    from paimon.channels.webui.channel import WebUIChannel


async def authz_answer_api(channel: "WebUIChannel", request: web.Request) -> web.Response:
    """接收用户对挂起权限询问的答复，写入对应 future 唤醒 ask_user 协程。"""
    if channel.require_auth:
        token = request.cookies.get("paimon_token")
        if not token or token not in channel.valid_tokens:
            return web.json_response({"error": "Unauthorized"}, status=401)

    try:
        data = await request.json()
        session_id = data.get("session_id", "").strip()
        answer = data.get("answer", "").strip()
        if not session_id or not answer:
            return web.json_response({"ok": False, "error": "缺少 session_id 或 answer"}, status=400)

        chat_id = f"webui-{session_id}"
        channel_key = f"{channel.name}:{chat_id}"
        fut = channel.state.pending_asks.get(channel_key)
        if fut is None or fut.done():
            return web.json_response({"ok": False, "error": "当前无挂起的权限询问"}, status=404)

        fut.set_result(answer)
        logger.info(
            "[派蒙·WebUI] 权限答复送达 session={} answer='{}'",
            session_id[:8], answer[:40],
        )
        return web.json_response({"ok": True})
    except Exception as e:
        logger.error("[派蒙·WebUI] 权限答复异常: {}", e)
        return web.json_response({"ok": False, "error": str(e)}, status=500)


def register_routes(app: web.Application, channel: "WebUIChannel") -> None:
    """注册 authz 路由（仅 1 个 POST 端点）。"""
    app.router.add_post(
        "/api/authz/answer",
        lambda r, ch=channel: authz_answer_api(ch, r),
    )
