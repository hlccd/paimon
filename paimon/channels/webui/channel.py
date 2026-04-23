from __future__ import annotations

import asyncio
import json
import time
import uuid
import shutil
from pathlib import Path
from typing import TYPE_CHECKING

from aiohttp import web
from loguru import logger

from paimon.channels.base import Channel, ChannelReply, IncomingMessage

if TYPE_CHECKING:
    from paimon.state import RuntimeState


# 推送会话（固定收件箱）—— 所有由派蒙推送来的消息都落在这里
# docs/aimon.md §2.6：推送不干扰正常会话，用户可随时切换过去看历史
PUSH_SESSION_ID = "push"
PUSH_SESSION_NAME = "📨 推送"
PUSH_CHAT_ID = f"webui-{PUSH_SESSION_ID}"  # "webui-push"


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

        # chat_id -> 当前活跃 SSE reply 回调（供 ask_user 推送询问用）
        self._active_replies: dict[str, object] = {}

        # 推送静态文件根目录（send_file 落在这里）
        self._pushes_root: Path = state.cfg.paimon_home / "webui_pushes"
        self._pushes_root.mkdir(parents=True, exist_ok=True)

        # PushHub 挂到 state（供 send_text / send_file 与 /api/push 共享）
        if state.push_hub is None:
            from paimon.channels.webui.push_hub import PushHub
            state.push_hub = PushHub()

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
        self.app.router.add_get("/plugins", self.plugins_page)
        self.app.router.add_get("/api/plugins/skills", self.plugins_skills_api)
        self.app.router.add_get("/api/plugins/authz", self.plugins_authz_api)
        self.app.router.add_post("/api/plugins/authz/revoke", self.plugins_authz_revoke_api)
        self.app.router.add_post("/api/authz/answer", self.authz_answer_api)
        # 推送长连接
        self.app.router.add_get("/api/push", self.push_stream)
        # 推送文件静态目录
        self.app.router.add_static(
            "/static/pushes/", path=str(self._pushes_root), show_index=False,
        )

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

    async def plugins_page(self, request: web.Request) -> web.Response:
        if self.require_auth:
            token = request.cookies.get("paimon_token")
            if not token or token not in self.valid_tokens:
                return web.Response(text=self._get_login_html(), content_type="text/html")

        from paimon.channels.webui.plugins_html import build_plugins_html
        return web.Response(
            text=build_plugins_html(),
            content_type="text/html",
            headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
        )

    async def plugins_skills_api(self, request: web.Request) -> web.Response:
        if self.require_auth:
            token = request.cookies.get("paimon_token")
            if not token or token not in self.valid_tokens:
                return web.json_response({"error": "Unauthorized"}, status=401)

        registry = self.state.skill_registry
        cache = self.state.authz_cache
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

    async def plugins_authz_api(self, request: web.Request) -> web.Response:
        if self.require_auth:
            token = request.cookies.get("paimon_token")
            if not token or token not in self.valid_tokens:
                return web.json_response({"error": "Unauthorized"}, status=401)

        irminsul = self.state.irminsul
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

    async def authz_answer_api(self, request: web.Request) -> web.Response:
        """权限询问专用答复端点。

        不经 /api/chat 流程，直接把答复文本塞给挂起的 Future。
        这样原 SSE 流不会被并发 chat 流程干扰。
        """
        if self.require_auth:
            token = request.cookies.get("paimon_token")
            if not token or token not in self.valid_tokens:
                return web.json_response({"error": "Unauthorized"}, status=401)

        try:
            data = await request.json()
            session_id = data.get("session_id", "").strip()
            answer = data.get("answer", "").strip()
            if not session_id or not answer:
                return web.json_response({"ok": False, "error": "缺少 session_id 或 answer"}, status=400)

            chat_id = f"webui-{session_id}"
            channel_key = f"{self.name}:{chat_id}"
            fut = self.state.pending_asks.get(channel_key)
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

    async def plugins_authz_revoke_api(self, request: web.Request) -> web.Response:
        if self.require_auth:
            token = request.cookies.get("paimon_token")
            if not token or token not in self.valid_tokens:
                return web.json_response({"error": "Unauthorized"}, status=401)

        try:
            data = await request.json()
            subject_type = data.get("subject_type", "")
            subject_id = data.get("subject_id", "")
            if not subject_type or not subject_id:
                return web.json_response({"ok": False, "error": "缺少 subject_type 或 subject_id"}, status=400)

            irminsul = self.state.irminsul
            if not irminsul:
                return web.json_response({"ok": False, "error": "世界树未就绪"}, status=500)

            ok = await irminsul.authz_revoke(
                subject_type, subject_id, actor="冰神面板",
            )
            # 同步撤销本地缓存
            if self.state.authz_cache:
                self.state.authz_cache.invalidate(subject_type, subject_id)
            return web.json_response({"ok": ok})
        except Exception as e:
            logger.error("[派蒙·WebUI] 撤销授权异常: {}", e)
            return web.json_response({"ok": False, "error": str(e)}, status=500)

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

        # 推送会话是只读收件箱，不允许在里面发消息污染历史
        if session_id == PUSH_SESSION_ID:
            return web.json_response(
                {"error": "推送收件箱是只读的，请在其他会话中对话"}, status=400,
            )

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

        async def reply(text: str, msg_type: str = "message") -> None:
            nonlocal connection_closed
            try:
                sse_data = json.dumps({"type": msg_type, "content": text})
                await response.write(f"data: {sse_data}\n\n".encode())
            except (ConnectionResetError, ConnectionError, asyncio.CancelledError):
                connection_closed = True
                logger.info("[派蒙·WebUI] SSE连接断开 session={}", session_id[:8])
                raise
            except Exception as e:
                logger.error("[派蒙·WebUI] SSE发送失败: {}", e)
                raise

        # 注册活跃回调，供 ask_user 推送询问
        self._active_replies[chat_id] = reply

        msg = IncomingMessage(
            channel_name=self.name,
            chat_id=chat_id,
            text=user_message,
            _reply=reply,
        )

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
        finally:
            # 无论上面走哪条分支（含早退 return / 异常），都清理活跃回调
            self._active_replies.pop(chat_id, None)

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

        # 前端占位符 'default' → 解析到当前 channel 绑定的真实 session
        # （否则 UI 显示空但后端仍沿用旧 session，造成上下文污染错觉）
        if session_id == "default":
            channel_key = f"{self.name}:webui-default"
            bound_id = self.state.session_mgr.bindings.get(channel_key)
            session = self.state.session_mgr.sessions.get(bound_id) if bound_id else None
            if not session:
                # 没绑定 → 返回空，前端按新会话展示
                return web.json_response({
                    "session_id": "default",
                    "name": "",
                    "messages": [],
                    "response_status": "idle",
                })
        else:
            session = self.state.session_mgr.sessions.get(session_id)
            if not session:
                return web.json_response({"error": "会话不存在"}, status=404)

        # 过滤 session.messages 为 UI 可展示条目：
        # - 保留 user / assistant 且 content 非空白的
        # - 对 assistant 只有 tool_calls（中间工具调用产物）显示占位气泡，让用户知道派蒙调了工具
        # - tool 消息隐藏（是内部机制，不展示给用户）
        messages = []
        for msg in session.messages:
            role = msg.get("role", "")
            if role not in ("user", "assistant"):
                continue
            content = msg.get("content") or ""   # None / 缺失都归一化为空字符串
            if content.strip():
                messages.append({"role": role, "content": content})
                continue
            # assistant 只有 tool_calls 时给个占位气泡
            if role == "assistant" and msg.get("tool_calls"):
                tool_names = []
                for tc in msg["tool_calls"]:
                    fn = tc.get("function") or {}
                    n = fn.get("name") or "(未知工具)"
                    tool_names.append(n)
                placeholder = f"_🔧 调用工具：{', '.join(tool_names)}_"
                messages.append({"role": role, "content": placeholder})

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
        # 推送收件箱不允许删除（docs/aimon.md §2.6：派蒙独占出口的固定接收点）
        if session_id == PUSH_SESSION_ID:
            return web.json_response(
                {"error": "推送收件箱不可删除"}, status=400,
            )
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
        """派蒙侧推送入口。忽略外部 chat_id，统一落到固定"📨 推送"会话。

        行为：
          1) 在推送会话历史里追加一条 assistant 消息（落世界树）
          2) 通过 PushHub 扇出到所有在线的 /api/push 客户端
        规则对齐 docs/aimon.md §2.6：推送不干扰正常会话。
        """
        if not text or not text.strip():
            return

        session_mgr = self.state.session_mgr
        if not session_mgr:
            logger.warning("[派蒙·WebUI·推送] 会话管理器未就绪，丢弃推送")
            return

        # 保底确保推送会话存在（启动时已建，这里幂等兜底）
        await self._ensure_push_session()

        push_session = session_mgr.sessions.get(PUSH_SESSION_ID)
        if push_session is not None:
            # 追加为 assistant 消息，持久化到世界树
            ts = time.time()
            push_session.messages.append({
                "role": "assistant",
                "content": text,
                "_push_ts": ts,
                "_push_source": chat_id,  # 溯源：原计划投递的 chat_id
            })
            push_session.updated_at = ts
            try:
                await session_mgr.save_session_async(push_session)
            except Exception as e:
                logger.warning("[派蒙·WebUI·推送] 会话落盘失败: {}", e)

        # 扇出到在线客户端
        payload = {
            "type": "push",
            "content": text,
            "ts": time.time(),
            "source": chat_id,
        }
        delivered = 0
        if self.state.push_hub:
            delivered = await self.state.push_hub.publish(PUSH_CHAT_ID, payload)

        if delivered == 0:
            logger.info(
                "[派蒙·WebUI·推送] 无在线监听者，已写入推送会话 (chat_id={} len={})",
                chat_id, len(text),
            )
        else:
            logger.info(
                "[派蒙·WebUI·推送] 已扇出 {} 路 (源 chat_id={} len={})",
                delivered, chat_id, len(text),
            )

    async def send_file(self, chat_id: str, file_path: Path, caption: str = "") -> None:
        """推送文件：拷贝到静态目录 + 推送带下载链接的消息。"""
        if not file_path.exists() or not file_path.is_file():
            logger.warning("[派蒙·WebUI·推送] 文件不存在: {}", file_path)
            return

        token = uuid.uuid4().hex[:8]
        dest_dir = self._pushes_root / token
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest_file = dest_dir / file_path.name

        try:
            shutil.copy2(str(file_path), str(dest_file))
        except Exception as e:
            logger.error("[派蒙·WebUI·推送] 文件拷贝失败: {}", e)
            return

        url = f"/static/pushes/{token}/{file_path.name}"
        size_kb = dest_file.stat().st_size / 1024
        header = caption.strip() or f"📎 {file_path.name}"
        text = (
            f"{header}\n\n"
            f"[⬇️ 下载 {file_path.name}]({url})  · {size_kb:.1f} KB"
        )
        await self.send_text(chat_id, text)

    async def make_reply(self, msg: IncomingMessage) -> ChannelReply:
        return WebUIChannelReply(msg._reply)

    async def _ensure_push_session(self) -> None:
        """幂等保障 "📨 推送" 会话存在（ID 固定，首次启动时创建）。"""
        session_mgr = self.state.session_mgr
        if not session_mgr:
            return
        if PUSH_SESSION_ID in session_mgr.sessions:
            return

        from paimon.session import Session
        now = time.time()
        push_session = Session(
            id=PUSH_SESSION_ID,
            name=PUSH_SESSION_NAME,
            created_at=now,
            updated_at=now,
        )
        session_mgr.sessions[PUSH_SESSION_ID] = push_session
        try:
            await session_mgr.save_session_async(push_session)
            logger.info("[派蒙·WebUI·推送] 推送会话已创建 id={}", PUSH_SESSION_ID)
        except Exception as e:
            logger.warning("[派蒙·WebUI·推送] 推送会话落盘失败: {}", e)

    async def push_stream(self, request: web.Request) -> web.StreamResponse:
        """前端长连接 SSE：订阅所有推送消息。每个连接一个独占 queue。"""
        if self.require_auth:
            token = request.cookies.get("paimon_token")
            if not token or token not in self.valid_tokens:
                return web.json_response({"error": "Unauthorized"}, status=401)

        hub = self.state.push_hub
        if hub is None:
            return web.json_response({"error": "PushHub 未初始化"}, status=500)

        response = web.StreamResponse(
            status=200, reason="OK",
            headers={
                "Content-Type": "text/event-stream",
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",  # 禁用 nginx 代理缓冲
            },
        )
        await response.prepare(request)

        queue = await hub.register(PUSH_CHAT_ID)
        # 首帧：告诉前端连接已建立
        try:
            await response.write(b': connected\n\n')
        except Exception:
            await hub.unregister(PUSH_CHAT_ID, queue)
            return response

        try:
            while True:
                try:
                    payload = await asyncio.wait_for(queue.get(), timeout=25.0)
                except asyncio.TimeoutError:
                    # 心跳：防止中间代理断连
                    try:
                        await response.write(b': ping\n\n')
                    except (ConnectionResetError, ConnectionError):
                        break
                    continue

                try:
                    data = json.dumps(payload, ensure_ascii=False)
                    await response.write(f"data: {data}\n\n".encode())
                except (ConnectionResetError, ConnectionError, asyncio.CancelledError):
                    break
                except Exception as e:
                    logger.warning("[派蒙·WebUI·推送] SSE 写入异常: {}", e)
                    break
        finally:
            await hub.unregister(PUSH_CHAT_ID, queue)
            try:
                await response.write_eof()
            except Exception:
                pass

        return response

    async def ask_user(self, chat_id: str, prompt: str, *, timeout: float = 30.0) -> str:
        """权限询问：通过当前活跃 SSE 推问题，挂起等下一条用户消息作答。

        约束：调用方必须在 on_channel_message → chat() 的请求处理链路内触发，
        这样才有活跃 SSE 可以推。无活跃连接则抛 NotImplementedError。
        答复由 /api/authz/answer 直投 Future，避免与另一条 /api/chat 并发。
        """
        send = self._active_replies.get(chat_id)
        if not send:
            raise NotImplementedError(
                f"chat_id={chat_id} 无活跃 SSE 连接，无法询问"
            )

        channel_key = f"{self.name}:{chat_id}"

        # 已有挂起询问（并发重入）直接拒绝
        if channel_key in self.state.pending_asks:
            raise NotImplementedError("已有挂起的权限询问，拒绝并发")

        # 推问题到前端（type=question 供前端渲染成特殊气泡 + 解锁输入）
        try:
            await send(prompt, msg_type="question")
        except TypeError:
            # reply 回调不支持关键字参数（非 WebUI 频道的自定义实现）→ 退化为普通文本
            await send(prompt)

        loop = asyncio.get_running_loop()
        fut: asyncio.Future[str] = loop.create_future()
        self.state.pending_asks[channel_key] = fut
        try:
            return await asyncio.wait_for(fut, timeout=timeout)
        finally:
            # 无论 Future 怎样结束（成功/取消/超时），都清理
            self.state.pending_asks.pop(channel_key, None)

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
        # 确保推送会话（📨 收件箱）存在
        await self._ensure_push_session()

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
