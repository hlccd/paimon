from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import TYPE_CHECKING

from aiohttp import web
from loguru import logger

from paimon.channels.base import Channel, ChannelReply, IncomingMessage

if TYPE_CHECKING:
    from paimon.state import RuntimeState


class WebUIChannelReply(ChannelReply):
    def __init__(self, reply_callback):
        self._reply = reply_callback

    async def send(self, text: str) -> None:
        if self._reply:
            await self._reply(text)


class WebUIChannel(Channel):
    name = "webui"

    def __init__(self, state: RuntimeState):
        self.state = state
        self.app = web.Application()
        self.host = state.cfg.webui_host
        self.port = state.cfg.webui_port
        self.runner = None

        self.access_code = state.cfg.webui_access_code
        self.require_auth = bool(self.access_code)
        self.valid_tokens: set[str] = set()

        self._setup_routes()

    def _setup_routes(self):
        self.app.router.add_get("/", self.index)
        self.app.router.add_get("/dashboard", self.dashboard)
        self.app.router.add_post("/api/auth", self.auth)
        self.app.router.add_post("/api/chat", self.chat)
        self.app.router.add_get("/api/sessions", self.get_sessions)
        self.app.router.add_get("/api/sessions/{session_id}/messages", self.get_session_messages)
        self.app.router.add_post("/api/sessions/new", self.new_session)
        self.app.router.add_post("/api/sessions/{session_id}/delete", self.delete_session)
        self.app.router.add_post("/api/sessions/stop", self.stop_session)
        self.app.router.add_get("/api/token_stats", self.token_stats)
        self.app.router.add_get("/api/token_stats/timeline", self.token_stats_timeline)
        self.app.router.add_get("/tasks", self.tasks_page)
        self.app.router.add_get("/api/tasks", self.tasks_api)

    async def tasks_page(self, request: web.Request) -> web.Response:
        if self.require_auth:
            token = request.cookies.get("paimon_token")
            if not token or token not in self.valid_tokens:
                return web.Response(text=self._get_login_html(), content_type="text/html")

        from paimon.channels.webui.tasks_html import build_tasks_html
        return web.Response(
            text=build_tasks_html(),
            content_type="text/html",
            headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
        )

    async def tasks_api(self, request: web.Request) -> web.Response:
        if self.require_auth:
            token = request.cookies.get("paimon_token")
            if not token or token not in self.valid_tokens:
                return web.json_response({"error": "Unauthorized"}, status=401)

        march = self.state.march
        if not march:
            return web.json_response({"tasks": []})

        tasks = await march.list_tasks()
        return web.json_response({
            "tasks": [
                {
                    "id": t.id,
                    "prompt": t.task_prompt,
                    "trigger_type": t.trigger_type,
                    "trigger_value": t.trigger_value,
                    "enabled": t.enabled,
                    "next_run_at": t.next_run_at,
                    "last_run_at": t.last_run_at,
                    "last_error": t.last_error,
                    "consecutive_failures": t.consecutive_failures,
                    "created_at": t.created_at,
                }
                for t in tasks
            ]
        })

    def _get_login_html(self) -> str:
        from paimon.channels.webui.theme import THEME_COLORS
        return (
            """<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Paimon</title>
    <style>"""
            + THEME_COLORS
            + """
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            background: var(--paimon-bg);
            display: flex;
            justify-content: center;
            align-items: center;
            min-height: 100vh;
            padding: 20px;
        }
        .login-container {
            background: var(--paimon-panel);
            border: 1px solid var(--paimon-border);
            border-radius: 16px;
            box-shadow: 0 10px 40px rgba(0,0,0,0.4);
            padding: 40px;
            width: 100%;
            max-width: 400px;
            text-align: center;
        }
        .logo { font-size: 48px; margin-bottom: 20px; }
        h1 {
            font-size: 24px;
            font-weight: 700;
            margin-bottom: 10px;
            background: linear-gradient(135deg, var(--gold), var(--gold-light));
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }
        p { color: var(--text-muted); margin-bottom: 30px; font-size: 14px; }
        .input-group { margin-bottom: 20px; text-align: left; }
        label { display: block; color: var(--text-secondary); font-size: 14px; margin-bottom: 8px; font-weight: 500; }
        input[type="password"] {
            width: 100%;
            padding: 12px 16px;
            background: var(--paimon-bg);
            border: 1px solid var(--paimon-border);
            border-radius: 8px;
            font-size: 16px;
            color: var(--text-primary);
            transition: border-color 0.2s;
        }
        input[type="password"]:focus { outline: none; border-color: var(--gold); }
        button {
            width: 100%;
            padding: 14px;
            background: linear-gradient(135deg, var(--gold), var(--gold-light));
            color: #000;
            border: none;
            border-radius: 8px;
            font-size: 16px;
            font-weight: 600;
            cursor: pointer;
        }
        .error { color: var(--status-error); font-size: 14px; margin-top: 10px; display: none; }
        .error.show { display: block; }
    </style>
</head>
<body>
    <div class="login-container">
        <div class="logo">P</div>
        <h1>Paimon</h1>
        <p>请输入访问码以继续</p>
        <form id="loginForm">
            <div class="input-group">
                <label for="accessCode">访问码</label>
                <input type="password" id="accessCode" placeholder="输入访问码" autocomplete="off" required>
            </div>
            <button type="submit">验证并进入</button>
            <div class="error" id="error">访问码错误，请重试</div>
        </form>
    </div>
    <script>
        document.getElementById('loginForm').addEventListener('submit', async (e) => {
            e.preventDefault();
            const code = document.getElementById('accessCode').value;
            const errorDiv = document.getElementById('error');
            try {
                const response = await fetch('/api/auth', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ code })
                });
                const data = await response.json();
                if (data.success) {
                    window.location.href = '/';
                } else {
                    errorDiv.classList.add('show');
                }
            } catch (error) {
                errorDiv.textContent = '验证失败，请检查网络连接';
                errorDiv.classList.add('show');
            }
        });
    </script>
</body>
</html>"""
        )

    async def index(self, request: web.Request) -> web.Response:
        if self.require_auth:
            token = request.cookies.get("paimon_token")
            if not token or token not in self.valid_tokens:
                return web.Response(text=self._get_login_html(), content_type="text/html")

        from paimon.channels.webui.static_html import CHAT_HTML
        return web.Response(
            text=CHAT_HTML,
            content_type="text/html",
            headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
        )

    async def dashboard(self, request: web.Request) -> web.Response:
        if self.require_auth:
            token = request.cookies.get("paimon_token")
            if not token or token not in self.valid_tokens:
                return web.Response(text=self._get_login_html(), content_type="text/html")

        from paimon.channels.webui.dashboard_html import build_dashboard_html
        return web.Response(
            text=build_dashboard_html(),
            content_type="text/html",
            headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
        )

    async def token_stats(self, request: web.Request) -> web.Response:
        if self.require_auth:
            token = request.cookies.get("paimon_token")
            if not token or token not in self.valid_tokens:
                return web.json_response({"error": "Unauthorized"}, status=401)

        primogem = self.state.primogem
        if not primogem:
            return web.json_response({"error": "原石模块未启用"}, status=500)

        global_stats = await primogem.get_global_stats()
        detail_stats = await primogem.get_detail_stats()

        return web.json_response({
            "global": global_stats,
            "detail": detail_stats,
        })

    async def token_stats_timeline(self, request: web.Request) -> web.Response:
        if self.require_auth:
            token = request.cookies.get("paimon_token")
            if not token or token not in self.valid_tokens:
                return web.json_response({"error": "Unauthorized"}, status=401)

        primogem = self.state.primogem
        if not primogem:
            return web.json_response({"error": "原石模块未启用"}, status=500)

        period = request.query.get("period", "day")
        count = min(int(request.query.get("count", "7")), 365)

        if period in ("hour", "weekday"):
            data = await primogem.get_distribution_stats(by=period)
        else:
            data = await primogem.get_timeline_stats(period, count)

        return web.json_response({"period": period, "data": data})

    async def auth(self, request: web.Request) -> web.Response:
        data = await request.json()
        code = data.get("code", "").strip()

        if code == self.access_code:
            import uuid
            token = str(uuid.uuid4())
            self.valid_tokens.add(token)
            logger.info("[派蒙·WebUI] 访问验证成功")
            response = web.json_response({"success": True})
            response.set_cookie("paimon_token", token, max_age=86400 * 30)
            return response
        else:
            logger.warning("[派蒙·WebUI] 访问验证失败")
            return web.json_response({"success": False}, status=401)

    async def chat(self, request: web.Request) -> web.StreamResponse:
        if self.require_auth:
            token = request.cookies.get("paimon_token")
            if not token or token not in self.valid_tokens:
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

        async def reply(text: str) -> None:
            nonlocal connection_closed
            try:
                sse_data = json.dumps({"type": "message", "content": text})
                await response.write(f"data: {sse_data}\n\n".encode())
            except (ConnectionResetError, ConnectionError, asyncio.CancelledError):
                connection_closed = True
                logger.info("[派蒙·WebUI] SSE连接断开 session={}", session_id[:8])
                raise
            except Exception as e:
                logger.error("[派蒙·WebUI] SSE发送失败: {}", e)
                raise

        msg = IncomingMessage(
            channel_name=self.name,
            chat_id=chat_id,
            text=user_message,
            _reply=reply,
        )

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
            await self._handle_message(msg)

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

    async def get_sessions(self, request: web.Request) -> web.Response:
        if self.require_auth:
            token = request.cookies.get("paimon_token")
            if not token or token not in self.valid_tokens:
                return web.json_response({"error": "Unauthorized"}, status=401)

        session_list = []
        if self.state.session_mgr:
            for session_id, session in self.state.session_mgr.sessions.items():
                session_list.append({
                    "id": session_id,
                    "name": session.name or f"会话 {session_id[:8]}",
                    "created_at": getattr(session, "created_at", 0),
                })

        return web.json_response({"sessions": session_list})

    async def get_session_messages(self, request: web.Request) -> web.Response:
        if self.require_auth:
            token = request.cookies.get("paimon_token")
            if not token or token not in self.valid_tokens:
                return web.json_response({"error": "Unauthorized"}, status=401)

        session_id = request.match_info["session_id"]
        if not self.state.session_mgr:
            return web.json_response({"error": "会话管理器未初始化"}, status=500)

        session = self.state.session_mgr.sessions.get(session_id)
        if not session:
            return web.json_response({"error": "会话不存在"}, status=404)

        messages = []
        for msg in session.messages:
            role = msg.get("role", "")
            if role in ("user", "assistant"):
                content = msg.get("content", "")
                if content:
                    messages.append({"role": role, "content": content})

        return web.json_response({
            "session_id": session_id,
            "name": session.name,
            "messages": messages,
            "response_status": session.response_status,
        })

    async def new_session(self, request: web.Request) -> web.Response:
        if self.require_auth:
            token = request.cookies.get("paimon_token")
            if not token or token not in self.valid_tokens:
                return web.json_response({"error": "Unauthorized"}, status=401)

        if not self.state.session_mgr:
            return web.json_response({"error": "会话管理器未初始化"}, status=500)

        new_session = self.state.session_mgr.create()
        channel_key = f"webui:webui-{new_session.id}"
        self.state.session_mgr.switch(channel_key, new_session.id)

        return web.json_response({
            "id": new_session.id,
            "name": new_session.name or f"新会话 {new_session.id[:8]}",
        })

    async def delete_session(self, request: web.Request) -> web.Response:
        if self.require_auth:
            token = request.cookies.get("paimon_token")
            if not token or token not in self.valid_tokens:
                return web.json_response({"error": "Unauthorized"}, status=401)

        session_id = request.match_info["session_id"]
        if not self.state.session_mgr:
            return web.json_response({"error": "会话管理器未初始化"}, status=500)

        if session_id not in self.state.session_mgr.sessions:
            return web.json_response({"error": "会话不存在"}, status=404)

        from paimon.core.chat import stop_session_task
        await stop_session_task(session_id)
        self.state.session_mgr.delete(session_id)
        return web.json_response({"ok": True})

    async def stop_session(self, request: web.Request) -> web.Response:
        if self.require_auth:
            token = request.cookies.get("paimon_token")
            if not token or token not in self.valid_tokens:
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

    async def send_text(self, chat_id: str, text: str) -> None:
        pass

    async def send_file(self, chat_id: str, file_path: Path, caption: str = "") -> None:
        pass

    async def make_reply(self, msg: IncomingMessage) -> ChannelReply:
        return WebUIChannelReply(msg._reply)

    async def _handle_message(self, msg: IncomingMessage):
        from paimon.state import state
        from paimon.core.chat import on_channel_message

        session_mgr = state.session_mgr
        if session_mgr and not session_mgr.get_current(msg.channel_key):
            sid = msg.chat_id.removeprefix("webui-")
            session = session_mgr.sessions.get(sid)
            if session:
                session_mgr.switch(msg.channel_key, session.id)

        await on_channel_message(msg, self)

    async def start(self):
        self.runner = web.AppRunner(self.app)
        await self.runner.setup()

        site = web.TCPSite(self.runner, self.host, self.port)
        await site.start()

        access_urls = self._get_access_urls()
        logger.info("[派蒙·WebUI] 服务已启动 http://{}:{}", self.host, self.port)
        for url in access_urls:
            logger.info("[派蒙·WebUI] {}", url)
        if self.require_auth:
            logger.info("[派蒙·WebUI] 访问验证: 已启用")
        else:
            logger.warning("[派蒙·WebUI] 访问验证: 未启用 (建议设置 WEBUI_ACCESS_CODE)")

        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            pass

    def _get_access_urls(self) -> list[str]:
        import socket

        urls = []
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            local_ip = s.getsockname()[0]
            s.close()

            if self.host == "0.0.0.0":
                urls.append(f"可访问地址: http://{local_ip}:{self.port}")
            elif self.host in ("127.0.0.1", "localhost"):
                urls.append(f"仅本机: http://127.0.0.1:{self.port}")
            else:
                urls.append(f"http://{self.host}:{self.port}")
        except Exception:
            urls.append(f"http://localhost:{self.port}")
        return urls

    async def stop(self):
        logger.info("[派蒙·WebUI] 正在停止")
        if hasattr(self, "runner") and self.runner:
            await self.runner.cleanup()
