from __future__ import annotations

import asyncio
import shutil
import uuid
from pathlib import Path
from typing import TYPE_CHECKING

from aiohttp import web
from loguru import logger

from paimon.channels.base import Channel, IncomingMessage
from paimon.channels.webui._reply import WebUIChannelReply

if TYPE_CHECKING:
    from paimon.state import RuntimeState


# 推送占位 chat_id：webui 推送统一落 push_archive 表（顶部红点抽屉消费），
# 不再有"📨 推送"会话实体。chat_id 字段保留作为元信息标识来源，但内容
# 不投递到任何会话。docs/foundation/march.md §推送归档（2026-04-25 转型；
# 2026-05 补完最后路径：删除 PUSH_SESSION/_pushes_session_messages/PushHub）。
PUSH_CHAT_ID = "webui-push"


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

        # 推送文件下载根目录（send_file 拷贝到这里，push_archive 嵌 markdown 下载链接）
        self._pushes_root: Path = state.cfg.paimon_home / "webui_pushes"
        self._pushes_root.mkdir(parents=True, exist_ok=True)

        self._setup_routes()

    def _setup_routes(self):
        # 推送文件静态目录（send_file 产出的下载链接由此响应）
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
        """派蒙侧推送入口：静默归档到 push_archive 表 + 通过 leyline 通知前端红点。

        架构：webui 不像 QQ/TG 能主动推 IM 消息，所有"派蒙→用户"的推送统一落
        push_archive 表，WebUI 顶部红点抽屉消费。chat_id 仅作元信息标识来源。
        与 march.ring_event 的差异：本路径**不限流**（webui 自身路径调用，已可信），
        ring_event 是给 archon 主动推送用的需要限流防刷屏。
        """
        if not text or not text.strip():
            return
        if not self.state.irminsul:
            logger.warning("[派蒙·WebUI·推送] irminsul 未就绪，丢弃推送")
            return

        try:
            rec_id = await self.state.irminsul.push_archive_create(
                source="派蒙",
                actor="派蒙",
                message_md=text,
                channel_name=self.name,
                chat_id=chat_id,
                level="silent",
                extra={},
            )
        except Exception as e:
            logger.error("[派蒙·WebUI·推送] 归档失败: {}", e)
            return

        # 通知前端红点更新（前端 SSE 订阅 push.archived 或轮询）
        if self.state.leyline:
            try:
                await self.state.leyline.publish(
                    "push.archived",
                    {"id": rec_id, "actor": "派蒙", "source": "派蒙", "level": "silent"},
                    source="WebUI·send_text",
                )
            except Exception as e:
                logger.debug("[派蒙·WebUI·推送] leyline publish 失败（不影响归档）: {}", e)

        logger.info(
            "[派蒙·WebUI·推送] 已归档 push_archive id={} (chat_id={} 长度={})",
            rec_id, chat_id, len(text),
        )

    async def send_file(self, chat_id: str, file_path: Path, caption: str = "") -> None:
        """推送文件：拷贝到静态目录 + 通过 send_text 推 markdown 下载链接。"""
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
