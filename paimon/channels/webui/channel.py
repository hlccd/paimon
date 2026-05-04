from __future__ import annotations

import asyncio
import json
import time
import uuid
import shutil
from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING

from aiohttp import web
from loguru import logger

from paimon.channels.base import Channel, IncomingMessage
from paimon.channels.webui._reply import WebUIChannelReply
from paimon.foundation.bg import bg

if TYPE_CHECKING:
    from paimon.state import RuntimeState


# 推送会话（固定收件箱）—— 所有由派蒙推送来的消息都落在这里
# docs/aimon.md §2.6：推送不干扰正常会话，用户可随时切换过去看历史
PUSH_SESSION_ID = "push"
PUSH_SESSION_NAME = "📨 推送"
PUSH_CHAT_ID = f"webui-{PUSH_SESSION_ID}"  # "webui-push"


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
        # 推送文件静态目录
        self.app.router.add_static(
            "/static/pushes/", path=str(self._pushes_root), show_index=False,
        )

        # 业务面板路由（草神/神之心/风神/岩神/水神/三月各面板及 / · /dashboard ·
        # /api/auth · /api/chat 等核心路由都委托给 api/ 子包统一注册）
        from paimon.channels.webui.api import register_all_routes
        register_all_routes(self.app, self)

    def _get_login_html(self) -> str:
        """委托到 _login_html 模块（保留 wrapper 让 api/ 子模块调用不变）。"""
        from paimon.channels.webui._login_html import get_login_html
        return get_login_html()

    def _check_auth(self, request: web.Request) -> bool:
        """统一 auth 闸：True=已登录 / False=未登录。仅内部使用。"""
        if not self.require_auth:
            return True
        token = request.cookies.get("paimon_token")
        return bool(token and token in self.valid_tokens)

    async def send_text(self, chat_id: str, text: str) -> None:
        """派蒙侧推送入口。忽略外部 chat_id，统一落到固定"📨 推送"会话。

        行为：
          1) 用 smart_chunk 按 1500 字 + markdown 友好边界拆分（避免单气泡过长）
          2) 每个 chunk 作为独立 assistant 消息追加到推送会话（落世界树）
          3) 每个 chunk 独立扇出到所有在线的 /api/push 客户端（前端渲染成多气泡）
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

        from paimon.channels._chunk import smart_chunk
        chunks = smart_chunk(text, max_len=1500)
        if not chunks:
            return

        push_session = session_mgr.sessions.get(PUSH_SESSION_ID)
        total_delivered = 0
        for chunk in chunks:
            if push_session is not None:
                ts = time.time()
                push_session.messages.append({
                    "role": "assistant",
                    "content": chunk,
                    "_push_ts": ts,
                    "_push_source": chat_id,
                })
                push_session.updated_at = ts

            payload = {
                "type": "push",
                "content": chunk,
                "ts": time.time(),
                "source": chat_id,
            }
            if self.state.push_hub:
                total_delivered += await self.state.push_hub.publish(
                    PUSH_CHAT_ID, payload,
                )

        # 整批 chunk 写完后落一次盘（减少 IO）
        if push_session is not None:
            try:
                await session_mgr.save_session_async(push_session)
            except Exception as e:
                logger.warning("[派蒙·WebUI·推送] 会话落盘失败: {}", e)

        if total_delivered == 0:
            logger.info(
                "[派蒙·WebUI·推送] 无在线监听者，已写入推送会话 (chat_id={} 拆分={}段 总长={})",
                chat_id, len(chunks), len(text),
            )
        else:
            logger.info(
                "[派蒙·WebUI·推送] 已扇出 {} 路 (源 chat_id={} 拆分={}段 总长={})",
                total_delivered, chat_id, len(chunks), len(text),
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
