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

from paimon.channels.base import Channel, ChannelReply, IncomingMessage

if TYPE_CHECKING:
    from paimon.state import RuntimeState


# 推送会话（固定收件箱）—— 所有由派蒙推送来的消息都落在这里
# docs/aimon.md §2.6：推送不干扰正常会话，用户可随时切换过去看历史
PUSH_SESSION_ID = "push"
PUSH_SESSION_NAME = "📨 推送"
PUSH_CHAT_ID = f"webui-{PUSH_SESSION_ID}"  # "webui-push"


class WebUIChannelReply(ChannelReply):
    streaming = True

    def __init__(self, reply_callback):
        self._reply = reply_callback

    async def send(self, text: str) -> None:
        if self._reply:
            await self._reply(text)

    async def notice(self, text: str, *, kind: str = "milestone") -> None:
        """推一条中间状态 SSE 事件（前端渲染为浅灰小字）。

        连接已关（SSE 断 / bg 任务晚于 SSE 生命周期）时静默丢弃——
        这正是 docs/interaction.md §1.1 说的 "送不了就丢" 的 degrade 语义。
        """
        if not self._reply or not text:
            return
        try:
            await self._reply(text, msg_type="notice", kind=kind)
        except (ConnectionResetError, ConnectionError):
            # SSE 已关（常见于 execute 后台阶段），按设计静默
            pass
        except TypeError:
            # reply 闭包不支持 kind（旧测试/mock 兜底），忽略
            pass
        except Exception as e:
            logger.debug("[派蒙·WebUI·notice] 发送失败 kind={}: {}", kind, e)
        # CancelledError 故意不捕获：让上游正常的 task cancel 语义能传播


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
        # 四影任务可见性（docs/interaction.md §四 WebUI tab）
        self.app.router.add_get("/api/tasks/complex", self.tasks_complex_list_api)
        self.app.router.add_get("/api/tasks/complex/{task_id}", self.tasks_complex_detail_api)
        self.app.router.add_get("/plugins", self.plugins_page)
        self.app.router.add_get("/api/plugins/skills", self.plugins_skills_api)
        self.app.router.add_get("/api/plugins/authz", self.plugins_authz_api)
        self.app.router.add_post("/api/plugins/authz/revoke", self.plugins_authz_revoke_api)
        # 草神·世界树面板（3 tab：记忆 / 知识库 / 文书归档）
        self.app.router.add_get("/knowledge", self.knowledge_page)
        self.app.router.add_get("/api/knowledge/memory/list", self.knowledge_memory_list_api)
        self.app.router.add_post("/api/knowledge/memory/remember", self.knowledge_memory_remember_api)
        self.app.router.add_post("/api/knowledge/memory/delete", self.knowledge_memory_delete_api)
        self.app.router.add_post("/api/knowledge/memory/hygiene", self.knowledge_memory_hygiene_api)
        self.app.router.add_get("/api/knowledge/memory/hygiene/status", self.knowledge_memory_hygiene_status_api)
        self.app.router.add_get("/api/knowledge/kb/list", self.knowledge_kb_list_api)
        self.app.router.add_get("/api/knowledge/kb/read", self.knowledge_kb_read_api)
        self.app.router.add_post("/api/knowledge/kb/remember", self.knowledge_kb_remember_api)
        self.app.router.add_post("/api/knowledge/kb/write", self.knowledge_kb_write_api)
        self.app.router.add_post("/api/knowledge/kb/delete", self.knowledge_kb_delete_api)
        self.app.router.add_post("/api/knowledge/kb/hygiene", self.knowledge_kb_hygiene_api)
        self.app.router.add_get("/api/knowledge/kb/hygiene/status", self.knowledge_kb_hygiene_status_api)
        self.app.router.add_get("/api/knowledge/archives/list", self.knowledge_archives_list_api)
        self.app.router.add_get("/api/knowledge/archives/read", self.knowledge_archives_read_api)
        # 神之心·LLM Profile 管理（M1：只做存储 + 面板，不接路由）
        self.app.router.add_get("/llm", self.llm_page)
        self.app.router.add_get("/api/llm/list", self.llm_list_api)
        self.app.router.add_post("/api/llm/create", self.llm_create_api)
        self.app.router.add_post("/api/llm/test", self.llm_test_api)
        self.app.router.add_post("/api/llm/{profile_id}/update", self.llm_update_api)
        self.app.router.add_post("/api/llm/{profile_id}/delete", self.llm_delete_api)
        self.app.router.add_post("/api/llm/{profile_id}/set-default", self.llm_set_default_api)
        self.app.router.add_post("/api/llm/{profile_id}/test", self.llm_test_existing_api)
        # M2：路由表
        self.app.router.add_get("/api/llm/routes", self.llm_routes_list_api)
        self.app.router.add_post("/api/llm/routes/set", self.llm_route_set_api)
        self.app.router.add_post("/api/llm/routes/delete", self.llm_route_delete_api)
        # 风神·信息流面板
        self.app.router.add_get("/feed", self.feed_page)
        self.app.router.add_get("/api/feed/stats", self.feed_stats_api)
        self.app.router.add_get("/api/feed/subs", self.feed_subs_list_api)
        self.app.router.add_post("/api/feed/subs", self.feed_subs_create_api)
        self.app.router.add_patch("/api/feed/subs/{sub_id}", self.feed_subs_patch_api)
        self.app.router.add_delete("/api/feed/subs/{sub_id}", self.feed_subs_delete_api)
        self.app.router.add_post("/api/feed/subs/{sub_id}/run", self.feed_subs_run_api)
        self.app.router.add_get("/api/feed/items", self.feed_items_api)
        # 风神·舆情看板（L1 事件级，docs/archons/venti.md §L1）
        self.app.router.add_get("/sentiment", self.sentiment_page)
        self.app.router.add_get("/api/sentiment/overview", self.sentiment_overview_api)
        self.app.router.add_get("/api/sentiment/events", self.sentiment_events_api)
        self.app.router.add_get("/api/sentiment/events/{event_id}", self.sentiment_event_detail_api)
        self.app.router.add_get("/api/sentiment/timeline", self.sentiment_timeline_api)
        self.app.router.add_get("/api/sentiment/sources", self.sentiment_sources_api)
        # 岩神·理财面板
        self.app.router.add_get("/wealth", self.wealth_page)
        self.app.router.add_get("/api/wealth/stats", self.wealth_stats_api)
        self.app.router.add_get("/api/wealth/recommended", self.wealth_recommended_api)
        self.app.router.add_get("/api/wealth/ranking", self.wealth_ranking_api)
        self.app.router.add_get("/api/wealth/changes", self.wealth_changes_api)
        self.app.router.add_get("/api/wealth/stock/{code}", self.wealth_stock_api)
        self.app.router.add_post("/api/wealth/trigger", self.wealth_trigger_api)
        self.app.router.add_get("/api/wealth/running", self.wealth_running_api)
        self.app.router.add_get("/api/wealth/scan_scope", self.wealth_scan_scope_api)
        self.app.router.add_get("/api/wealth/user_watch", self.wealth_user_watch_list_api)
        self.app.router.add_post("/api/wealth/user_watch/add", self.wealth_user_watch_add_api)
        self.app.router.add_post("/api/wealth/user_watch/remove", self.wealth_user_watch_remove_api)
        self.app.router.add_post("/api/wealth/user_watch/update", self.wealth_user_watch_update_api)
        self.app.router.add_post("/api/wealth/user_watch/refresh", self.wealth_user_watch_refresh_api)
        # 水神·游戏
        self.app.router.add_get("/game", self.game_page)
        self.app.router.add_get("/api/game/overview", self.game_overview_api)
        self.app.router.add_post("/api/game/qr_create", self.game_qr_create_api)
        self.app.router.add_get("/api/game/qr_poll", self.game_qr_poll_api)
        self.app.router.add_post("/api/game/unbind", self.game_unbind_api)
        self.app.router.add_post("/api/game/sign", self.game_sign_api)
        self.app.router.add_post("/api/game/sign_all", self.game_sign_all_api)
        self.app.router.add_post("/api/game/collect_all", self.game_collect_all_api)
        self.app.router.add_post("/api/game/collect_one", self.game_collect_one_api)
        self.app.router.add_get("/api/game/abyss_latest", self.game_abyss_latest_api)
        self.app.router.add_post("/api/game/gacha/import", self.game_gacha_import_api)
        self.app.router.add_get("/api/game/gacha/stats", self.game_gacha_stats_api)
        self.app.router.add_get("/api/game/characters", self.game_characters_api)
        self.app.router.add_post("/api/authz/answer", self.authz_answer_api)
        # 三月·自检面板
        self.app.router.add_get("/selfcheck", self.selfcheck_page)
        self.app.router.add_get("/api/selfcheck/quick/latest", self.selfcheck_quick_latest_api)
        self.app.router.add_post("/api/selfcheck/quick/run", self.selfcheck_quick_run_api)
        self.app.router.add_get("/api/selfcheck/runs", self.selfcheck_runs_list_api)
        self.app.router.add_get("/api/selfcheck/runs/{run_id}", self.selfcheck_run_detail_api)
        self.app.router.add_get("/api/selfcheck/runs/{run_id}/report", self.selfcheck_run_report_api)
        self.app.router.add_get("/api/selfcheck/runs/{run_id}/findings", self.selfcheck_run_findings_api)
        self.app.router.add_get("/api/selfcheck/runs/{run_id}/quick", self.selfcheck_run_quick_api)
        self.app.router.add_delete("/api/selfcheck/runs/{run_id}", self.selfcheck_run_delete_api)
        self.app.router.add_post("/api/selfcheck/deep/run", self.selfcheck_deep_run_api)
        # 推送归档（替代主动聊天推送 / 全局红点抽屉数据源）
        self.app.router.add_get("/api/push_archive/unread_count", self.push_archive_unread_api)
        self.app.router.add_get("/api/push_archive/list", self.push_archive_list_api)
        self.app.router.add_get("/api/push_archive/{rec_id}", self.push_archive_detail_api)
        self.app.router.add_post("/api/push_archive/{rec_id}/read", self.push_archive_mark_read_api)
        self.app.router.add_post("/api/push_archive/read_all", self.push_archive_mark_read_all_api)
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

    async def knowledge_page(self, request: web.Request) -> web.Response:
        if self.require_auth:
            token = request.cookies.get("paimon_token")
            if not token or token not in self.valid_tokens:
                return web.Response(text=self._get_login_html(), content_type="text/html")

        from paimon.channels.webui.knowledge_html import build_knowledge_html
        return web.Response(
            text=build_knowledge_html(),
            content_type="text/html",
            headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
        )

    async def knowledge_memory_list_api(self, request: web.Request) -> web.Response:
        """列 L1 记忆（user / feedback / project / reference 四类），含完整 body 和 preview。"""
        if self.require_auth:
            token = request.cookies.get("paimon_token")
            if not token or token not in self.valid_tokens:
                return web.json_response({"error": "Unauthorized"}, status=401)

        mem_type = request.query.get("mem_type", "").strip()
        if mem_type not in ("user", "feedback", "project", "reference"):
            return web.json_response(
                {"error": "mem_type 必须是 user / feedback / project / reference"},
                status=400,
            )

        irminsul = self.state.irminsul
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

    async def knowledge_memory_remember_api(self, request: web.Request) -> web.Response:
        """记忆新建：自然语言 → LLM 分类 → 冲突检测 → 落 memory 域。

        body: {content}
        resp: {ok, action, mem_type, subject, title, id, target_id, target_title, reason, error?}
        """
        if self.require_auth:
            token = request.cookies.get("paimon_token")
            if not token or token not in self.valid_tokens:
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

            irminsul = self.state.irminsul
            model = self.state.model
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

    async def knowledge_memory_delete_api(self, request: web.Request) -> web.Response:
        if self.require_auth:
            token = request.cookies.get("paimon_token")
            if not token or token not in self.valid_tokens:
                return web.json_response({"error": "Unauthorized"}, status=401)

        try:
            data = await request.json()
            mem_id = (data.get("id") or "").strip()
            if not mem_id:
                return web.json_response({"ok": False, "error": "缺少 id"}, status=400)

            irminsul = self.state.irminsul
            if not irminsul:
                return web.json_response({"ok": False, "error": "世界树未就绪"}, status=500)

            ok = await irminsul.memory_delete(mem_id, actor="草神面板")
            return web.json_response({"ok": ok})
        except Exception as e:
            logger.error("[草神·世界树] 删除记忆异常: {}", e)
            return web.json_response({"ok": False, "error": str(e)}, status=500)

    async def knowledge_memory_hygiene_api(self, request: web.Request) -> web.Response:
        """手动触发记忆整理。后台跑，立即返回 {ok, already_running?}。
        结果经 push_archive 归档，前端轮询 hygiene/status 拿状态。
        """
        if self.require_auth:
            token = request.cookies.get("paimon_token")
            if not token or token not in self.valid_tokens:
                return web.json_response({"error": "Unauthorized"}, status=401)

        from paimon.core.memory_classifier import run_hygiene, is_hygiene_running

        if is_hygiene_running():
            return web.json_response({"ok": True, "already_running": True})

        irminsul = self.state.irminsul
        model = self.state.model
        if not irminsul or not model:
            return web.json_response({"ok": False, "error": "世界树 / 模型未就绪"}, status=500)

        # fire-and-forget 后台跑；前端用 status 轮询
        import asyncio as _asyncio
        _asyncio.create_task(run_hygiene(irminsul, model, trigger="manual"))
        return web.json_response({"ok": True, "started": True})

    async def knowledge_memory_hygiene_status_api(self, request: web.Request) -> web.Response:
        """前端用：是否在跑 + 最近一次报告（从 push_archive 拉）。"""
        if self.require_auth:
            token = request.cookies.get("paimon_token")
            if not token or token not in self.valid_tokens:
                return web.json_response({"error": "Unauthorized"}, status=401)

        from paimon.core.memory_classifier import is_hygiene_running

        irminsul = self.state.irminsul
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

    # ---------- 草神·知识库（world tree knowledge 域）----------

    async def knowledge_kb_list_api(self, request: web.Request) -> web.Response:
        """列知识库条目（带 body_preview + updated_at），按更新时间降序，可选按 category 过滤。"""
        if self.require_auth:
            token = request.cookies.get("paimon_token")
            if not token or token not in self.valid_tokens:
                return web.json_response({"error": "Unauthorized"}, status=401)

        irminsul = self.state.irminsul
        if not irminsul:
            return web.json_response({"items": []})

        category = request.query.get("category", "").strip()
        try:
            items = await irminsul.knowledge_list_detailed(category)
        except Exception as e:
            logger.error("[草神·知识库] 列出异常: {}", e)
            return web.json_response({"error": str(e)}, status=500)
        return web.json_response({"items": items})

    async def knowledge_kb_read_api(self, request: web.Request) -> web.Response:
        """读知识条目全文。"""
        if self.require_auth:
            token = request.cookies.get("paimon_token")
            if not token or token not in self.valid_tokens:
                return web.json_response({"error": "Unauthorized"}, status=401)

        category = request.query.get("category", "").strip()
        topic = request.query.get("topic", "").strip()
        if not category or not topic:
            return web.json_response(
                {"error": "缺少 category / topic"}, status=400,
            )

        irminsul = self.state.irminsul
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

    async def knowledge_kb_remember_api(self, request: web.Request) -> web.Response:
        """知识库新建：自然语言 → LLM 判 category/topic + 冲突检测 → 落 knowledge 域。

        body: {content}
        resp: {ok, action, category, topic, title, target_topic, reason, error?}
        """
        if self.require_auth:
            token = request.cookies.get("paimon_token")
            if not token or token not in self.valid_tokens:
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

            irminsul = self.state.irminsul
            model = self.state.model
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

    async def knowledge_kb_write_api(self, request: web.Request) -> web.Response:
        """已知 category/topic 的编辑入口（详情 modal「编辑」按钮用）。

        body: {category, topic, body}
        """
        if self.require_auth:
            token = request.cookies.get("paimon_token")
            if not token or token not in self.valid_tokens:
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

            irminsul = self.state.irminsul
            if not irminsul:
                return web.json_response({"ok": False, "error": "世界树未就绪"}, status=500)

            await irminsul.knowledge_write(category, topic, body, actor="草神面板")
            return web.json_response({"ok": True})
        except Exception as e:
            logger.error("[草神·世界树] 写入知识异常: {}", e)
            return web.json_response({"ok": False, "error": str(e)}, status=500)

    async def knowledge_kb_delete_api(self, request: web.Request) -> web.Response:
        if self.require_auth:
            token = request.cookies.get("paimon_token")
            if not token or token not in self.valid_tokens:
                return web.json_response({"error": "Unauthorized"}, status=401)

        try:
            data = await request.json()
            category = (data.get("category") or "").strip()
            topic = (data.get("topic") or "").strip()
            if not category or not topic:
                return web.json_response(
                    {"ok": False, "error": "缺少 category / topic"}, status=400,
                )
            irminsul = self.state.irminsul
            if not irminsul:
                return web.json_response({"ok": False, "error": "世界树未就绪"}, status=500)
            ok = await irminsul.knowledge_delete(category, topic, actor="草神面板")
            return web.json_response({"ok": ok})
        except Exception as e:
            logger.error("[草神·知识库] 删除异常: {}", e)
            return web.json_response({"ok": False, "error": str(e)}, status=500)

    # ---------- 草神·文书归档（读 .paimon/workspace/<task_id>/ 产物）----------

    async def knowledge_kb_hygiene_api(self, request: web.Request) -> web.Response:
        """手动触发知识库整理。后台跑，立即返回；前端轮询 hygiene/status 拿结果。"""
        if self.require_auth:
            token = request.cookies.get("paimon_token")
            if not token or token not in self.valid_tokens:
                return web.json_response({"error": "Unauthorized"}, status=401)
        from paimon.core.memory_classifier import run_kb_hygiene, is_kb_hygiene_running
        if is_kb_hygiene_running():
            return web.json_response({"ok": True, "already_running": True})
        irminsul = self.state.irminsul
        model = self.state.model
        if not irminsul or not model:
            return web.json_response({"ok": False, "error": "世界树 / 模型未就绪"}, status=500)
        import asyncio as _asyncio
        _asyncio.create_task(run_kb_hygiene(irminsul, model, trigger="manual"))
        return web.json_response({"ok": True, "started": True})

    async def knowledge_kb_hygiene_status_api(self, request: web.Request) -> web.Response:
        """知识库整理：是否在跑 + 最近一次报告。"""
        if self.require_auth:
            token = request.cookies.get("paimon_token")
            if not token or token not in self.valid_tokens:
                return web.json_response({"error": "Unauthorized"}, status=401)
        from paimon.core.memory_classifier import is_kb_hygiene_running
        irminsul = self.state.irminsul
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

    async def knowledge_archives_list_api(self, request: web.Request) -> web.Response:
        """列所有任务 workspace 的产物汇总：task_id + 标题 + 创建时间 + 产物清单。"""
        if self.require_auth:
            token = request.cookies.get("paimon_token")
            if not token or token not in self.valid_tokens:
                return web.json_response({"error": "Unauthorized"}, status=401)

        from paimon.foundation.task_workspace import list_workspaces
        irminsul = self.state.irminsul

        try:
            entries = list_workspaces()
        except Exception as e:
            logger.error("[草神·文书] list_workspaces 异常: {}", e)
            return web.json_response({"error": str(e)}, status=500)

        # 每个 entry 关联 task 拉 title（如果能找到）
        items = []
        for e in entries:
            title = ""
            if irminsul:
                try:
                    task = await irminsul.task_get(e["task_id"])
                    if task:
                        title = task.title or task.description[:60]
                except Exception:
                    pass
            items.append({
                "task_id": e["task_id"],
                "title": title,
                "created_at": e["created_at"],
                "artifacts": e["artifacts"],
            })
        # 按时间倒序
        items.sort(key=lambda x: x["created_at"], reverse=True)
        return web.json_response({"items": items})

    async def knowledge_archives_read_api(self, request: web.Request) -> web.Response:
        """读单个任务的单份产物全文（markdown / code）。"""
        if self.require_auth:
            token = request.cookies.get("paimon_token")
            if not token or token not in self.valid_tokens:
                return web.json_response({"error": "Unauthorized"}, status=401)

        task_id = request.query.get("task_id", "").strip()
        artifact = request.query.get("artifact", "").strip()
        if not task_id or not artifact:
            return web.json_response(
                {"error": "缺少 task_id / artifact"}, status=400,
            )

        from paimon.foundation.task_workspace import read_artifact
        try:
            content = read_artifact(task_id, artifact)
        except Exception as e:
            logger.error("[草神·文书] 读产物异常 {}/{}: {}", task_id, artifact, e)
            return web.json_response({"error": str(e)}, status=500)
        if content is None:
            return web.json_response({"error": "未找到"}, status=404)
        return web.json_response({
            "task_id": task_id,
            "artifact": artifact,
            "body": content,
        })

    # ---------- 神之心 · LLM Profile 管理 ----------

    async def llm_page(self, request: web.Request) -> web.Response:
        if not self._check_auth(request):
            return web.Response(text=self._get_login_html(), content_type="text/html")
        from paimon.channels.webui.llm_html import build_llm_html
        return web.Response(
            text=build_llm_html(),
            content_type="text/html",
            headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
        )

    async def llm_list_api(self, request: web.Request) -> web.Response:
        if not self._check_auth(request):
            return web.json_response({"error": "Unauthorized"}, status=401)
        irminsul = self.state.irminsul
        if not irminsul:
            return web.json_response({"profiles": []})
        profiles = await irminsul.llm_profile_list(include_keys=False)
        return web.json_response({
            "profiles": [self._llm_profile_to_json(p) for p in profiles],
        })

    async def llm_create_api(self, request: web.Request) -> web.Response:
        if not self._check_auth(request):
            return web.json_response({"ok": False, "error": "Unauthorized"}, status=401)
        irminsul = self.state.irminsul
        if not irminsul:
            return web.json_response({"ok": False, "error": "世界树未就绪"}, status=500)
        try:
            data = await request.json()
            profile = self._llm_json_to_profile(data)
            if not profile.name or not profile.model or not profile.base_url:
                return web.json_response(
                    {"ok": False, "error": "name / model / base_url 必填"}, status=400,
                )
            profile_id = await irminsul.llm_profile_create(profile, actor="WebUI")
            await self._llm_publish_profile_event(profile_id, "create")
            return web.json_response({"ok": True, "id": profile_id})
        except Exception as e:
            logger.error("[神之心·LLM 面板] 创建 profile 异常: {}", e)
            return web.json_response({"ok": False, "error": str(e)}, status=500)

    async def llm_update_api(self, request: web.Request) -> web.Response:
        if not self._check_auth(request):
            return web.json_response({"ok": False, "error": "Unauthorized"}, status=401)
        irminsul = self.state.irminsul
        if not irminsul:
            return web.json_response({"ok": False, "error": "世界树未就绪"}, status=500)
        profile_id = request.match_info["profile_id"]
        try:
            data = await request.json()
            fields = self._llm_json_to_update_fields(data)
            ok = await irminsul.llm_profile_update(profile_id, actor="WebUI", **fields)
            if ok:
                await self._llm_publish_profile_event(profile_id, "update")
            return web.json_response({"ok": ok})
        except Exception as e:
            logger.error("[神之心·LLM 面板] 更新 {} 异常: {}", profile_id, e)
            return web.json_response({"ok": False, "error": str(e)}, status=500)

    async def llm_delete_api(self, request: web.Request) -> web.Response:
        if not self._check_auth(request):
            return web.json_response({"ok": False, "error": "Unauthorized"}, status=401)
        irminsul = self.state.irminsul
        if not irminsul:
            return web.json_response({"ok": False, "error": "世界树未就绪"}, status=500)
        profile_id = request.match_info["profile_id"]
        try:
            ok = await irminsul.llm_profile_delete(profile_id, actor="WebUI")
            if ok:
                await self._llm_publish_profile_event(profile_id, "delete")
            return web.json_response({"ok": ok})
        except ValueError as e:
            return web.json_response({"ok": False, "error": str(e)}, status=400)
        except Exception as e:
            logger.error("[神之心·LLM 面板] 删除 {} 异常: {}", profile_id, e)
            return web.json_response({"ok": False, "error": str(e)}, status=500)

    async def llm_set_default_api(self, request: web.Request) -> web.Response:
        if not self._check_auth(request):
            return web.json_response({"ok": False, "error": "Unauthorized"}, status=401)
        irminsul = self.state.irminsul
        if not irminsul:
            return web.json_response({"ok": False, "error": "世界树未就绪"}, status=500)
        profile_id = request.match_info["profile_id"]
        try:
            ok = await irminsul.llm_profile_set_default(profile_id, actor="WebUI")
            if ok:
                await self._llm_publish_profile_event(profile_id, "set_default")
            return web.json_response({"ok": ok})
        except Exception as e:
            logger.error("[神之心·LLM 面板] 设默认 {} 异常: {}", profile_id, e)
            return web.json_response({"ok": False, "error": str(e)}, status=500)

    async def llm_test_api(self, request: web.Request) -> web.Response:
        """编辑/新增表单里的「测试连接」：用前端提交的字段临时构造 client 冒烟。"""
        if not self._check_auth(request):
            return web.json_response({"ok": False, "error": "Unauthorized"}, status=401)
        try:
            data = await request.json()
            # 如果 api_key 是掩码占位，回退到已存的那条 profile
            if data.get("api_key") == "***" and data.get("id"):
                stored = await self.state.irminsul.llm_profile_get(
                    data["id"], include_key=True,
                )
                if stored:
                    data["api_key"] = stored.api_key
            return await self._llm_probe_ping(data)
        except Exception as e:
            logger.error("[神之心·LLM 面板] 测试连接异常: {}", e)
            return web.json_response({"ok": False, "error": str(e)})

    async def llm_test_existing_api(self, request: web.Request) -> web.Response:
        """列表里已有 profile 的「测连接」：从世界树取完整 profile（含 key）冒烟。"""
        if not self._check_auth(request):
            return web.json_response({"ok": False, "error": "Unauthorized"}, status=401)
        irminsul = self.state.irminsul
        if not irminsul:
            return web.json_response({"ok": False, "error": "世界树未就绪"}, status=500)
        profile_id = request.match_info["profile_id"]
        profile = await irminsul.llm_profile_get(profile_id, include_key=True)
        if not profile:
            return web.json_response({"ok": False, "error": "profile 不存在"}, status=404)
        return await self._llm_probe_ping({
            "provider_kind": profile.provider_kind,
            "api_key": profile.api_key,
            "base_url": profile.base_url,
            "model": profile.model,
            "max_tokens": profile.max_tokens,
            "reasoning_effort": profile.reasoning_effort,
            "extra_body": profile.extra_body or {},
        })

    async def _llm_probe_ping(self, data: dict) -> web.Response:
        """按 provider_kind 临时构造 client 发一条 ping，10s 超时。"""
        import asyncio
        import time as _time
        kind = (data.get("provider_kind") or "openai").strip().lower()
        api_key = (data.get("api_key") or "").strip()
        base_url = (data.get("base_url") or "").strip()
        model = (data.get("model") or "").strip()
        if not api_key or not base_url or not model:
            return web.json_response(
                {"ok": False, "error": "api_key / base_url / model 必填"},
            )
        t0 = _time.time()
        try:
            if kind == "anthropic":
                from anthropic import AsyncAnthropic
                client = AsyncAnthropic(api_key=api_key, base_url=base_url)
                resp = await asyncio.wait_for(
                    client.messages.create(
                        model=model, max_tokens=10,
                        messages=[{"role": "user", "content": "ping"}],
                    ),
                    timeout=10.0,
                )
                # Anthropic 返回 resp.content[0].text
                sample = ""
                if resp.content:
                    block = resp.content[0]
                    sample = getattr(block, "text", "") or ""
            else:
                from openai import AsyncOpenAI
                client = AsyncOpenAI(api_key=api_key, base_url=base_url)
                kwargs: dict = {
                    "model": model,
                    "messages": [{"role": "user", "content": "ping"}],
                    "max_tokens": 10,
                }
                eff = (data.get("reasoning_effort") or "").strip()
                if eff:
                    kwargs["reasoning_effort"] = eff
                eb = data.get("extra_body") or {}
                if eb:
                    kwargs["extra_body"] = eb
                resp = await asyncio.wait_for(
                    client.chat.completions.create(**kwargs),
                    timeout=10.0,
                )
                sample = resp.choices[0].message.content or ""
            latency_ms = int((_time.time() - t0) * 1000)
            return web.json_response({
                "ok": True,
                "latency_ms": latency_ms,
                "sample": (sample or "")[:120],
            })
        except asyncio.TimeoutError:
            return web.json_response({"ok": False, "error": "请求超时（>10s）"})
        except Exception as e:
            return web.json_response({"ok": False, "error": str(e)[:500]})

    @staticmethod
    def _llm_profile_to_json(p) -> dict:
        return {
            "id": p.id,
            "name": p.name,
            "provider_kind": p.provider_kind,
            "api_key": p.api_key,   # 已在 repo 层做掩码
            "base_url": p.base_url,
            "model": p.model,
            "max_tokens": p.max_tokens,
            "reasoning_effort": p.reasoning_effort,
            "extra_body": p.extra_body or {},
            "is_default": p.is_default,
            "notes": p.notes,
            "created_at": p.created_at,
            "updated_at": p.updated_at,
        }

    @staticmethod
    def _llm_json_to_profile(data: dict):
        """前端 JSON → LLMProfile（用于 create）。"""
        from paimon.foundation.irminsul.llm_profile import LLMProfile
        eb = data.get("extra_body") or {}
        if not isinstance(eb, dict):
            eb = {}
        return LLMProfile(
            name=(data.get("name") or "").strip(),
            provider_kind=(data.get("provider_kind") or "openai").strip(),
            api_key=(data.get("api_key") or "").strip(),
            base_url=(data.get("base_url") or "").strip(),
            model=(data.get("model") or "").strip(),
            max_tokens=int(data.get("max_tokens") or 64000),
            reasoning_effort=(data.get("reasoning_effort") or "").strip(),
            extra_body=eb,
            notes=(data.get("notes") or "").strip(),
        )

    @staticmethod
    def _llm_json_to_update_fields(data: dict) -> dict:
        """前端 JSON → update fields。api_key='***' 表示保留不动。"""
        fields: dict = {}
        for key in ("name", "provider_kind", "base_url", "model",
                    "reasoning_effort", "notes"):
            if key in data:
                fields[key] = (data.get(key) or "").strip()
        if "api_key" in data:
            fields["api_key"] = data.get("api_key") or ""  # "***" 由 repo 层识别
        if "max_tokens" in data:
            fields["max_tokens"] = int(data.get("max_tokens") or 64000)
        if "extra_body" in data:
            eb = data.get("extra_body") or {}
            fields["extra_body"] = eb if isinstance(eb, dict) else {}
        return fields

    async def _llm_publish_profile_event(
        self, profile_id: str, action: str,
    ) -> None:
        """Profile 写入后 publish leyline，供 Gnosis 失效缓存。"""
        if not self.state.leyline:
            return
        try:
            await self.state.leyline.publish(
                "llm.profile.updated",
                {"profile_id": profile_id, "action": action},
                source="WebUI·LLM面板",
            )
        except Exception as e:
            logger.debug("[神之心·LLM 面板] publish profile event 失败: {}", e)

    async def _llm_publish_route_event(self, route_key: str) -> None:
        if not self.state.leyline:
            return
        try:
            await self.state.leyline.publish(
                "llm.route.updated",
                {"route_key": route_key},
                source="WebUI·LLM面板",
            )
        except Exception as e:
            logger.debug("[神之心·LLM 面板] publish route event 失败: {}", e)

    async def llm_routes_list_api(self, request: web.Request) -> web.Response:
        """列路由表 + 已知调用点 + 默认 profile 名 + 最近命中快照（面板用）。"""
        if not self._check_auth(request):
            return web.json_response({"error": "Unauthorized"}, status=401)
        irminsul = self.state.irminsul
        router = self.state.model_router
        if not irminsul or not router:
            return web.json_response({
                "routes": {}, "callsites": [], "default": None, "hits": {},
            })
        # 已配路由快照（用 router 内存版，免打 DB）
        routes = router.snapshot()
        hits = router.get_hits()  # {route_key: {profile_id, model_name, provider_source, timestamp}}
        from paimon.foundation.model_router import KNOWN_CALLSITES
        default = await irminsul.llm_profile_get_default()
        return web.json_response({
            "routes": routes,
            "callsites": [
                {"component": c, "purpose": p} for c, p in KNOWN_CALLSITES
            ],
            "default": (
                {"id": default.id, "name": default.name} if default else None
            ),
            "hits": hits,
        })

    async def llm_route_set_api(self, request: web.Request) -> web.Response:
        if not self._check_auth(request):
            return web.json_response({"ok": False, "error": "Unauthorized"}, status=401)
        if not self.state.model_router or not self.state.irminsul:
            return web.json_response(
                {"ok": False, "error": "路由器/世界树未就绪"}, status=500,
            )
        try:
            data = await request.json()
            route_key = (data.get("route_key") or "").strip()
            profile_id = (data.get("profile_id") or "").strip()
            if not route_key or not profile_id:
                return web.json_response(
                    {"ok": False, "error": "route_key / profile_id 必填"},
                    status=400,
                )
            # 校验 profile_id 存在，避免写入悬挂引用
            profile = await self.state.irminsul.llm_profile_get(
                profile_id, include_key=False,
            )
            if profile is None:
                return web.json_response(
                    {"ok": False, "error": f"profile 不存在: {profile_id}"},
                    status=400,
                )
            await self.state.model_router.set_route(
                route_key, profile_id, actor="WebUI",
            )
            await self._llm_publish_route_event(route_key)
            return web.json_response({"ok": True})
        except Exception as e:
            logger.error("[神之心·LLM 面板] 设路由异常: {}", e)
            return web.json_response({"ok": False, "error": str(e)}, status=500)

    async def llm_route_delete_api(self, request: web.Request) -> web.Response:
        if not self._check_auth(request):
            return web.json_response({"ok": False, "error": "Unauthorized"}, status=401)
        if not self.state.model_router:
            return web.json_response(
                {"ok": False, "error": "路由器未就绪"}, status=500,
            )
        try:
            data = await request.json()
            route_key = (data.get("route_key") or "").strip()
            if not route_key:
                return web.json_response(
                    {"ok": False, "error": "route_key 必填"}, status=400,
                )
            ok = await self.state.model_router.delete_route(
                route_key, actor="WebUI",
            )
            if ok:
                await self._llm_publish_route_event(route_key)
            return web.json_response({"ok": ok})
        except Exception as e:
            logger.error("[神之心·LLM 面板] 删路由异常: {}", e)
            return web.json_response({"ok": False, "error": str(e)}, status=500)

    # ---------- 风神 · 信息流面板 ----------

    def _check_auth(self, request: web.Request) -> bool:
        """统一 auth 闸：True=已登录 / False=未登录。仅内部使用。"""
        if not self.require_auth:
            return True
        token = request.cookies.get("paimon_token")
        return bool(token and token in self.valid_tokens)

    async def feed_page(self, request: web.Request) -> web.Response:
        if not self._check_auth(request):
            return web.Response(text=self._get_login_html(), content_type="text/html")

        from paimon.channels.webui.feed_html import build_feed_html
        return web.Response(
            text=build_feed_html(),
            content_type="text/html",
            headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
        )

    async def feed_stats_api(self, request: web.Request) -> web.Response:
        if not self._check_auth(request):
            return web.json_response({"error": "Unauthorized"}, status=401)
        irminsul = self.state.irminsul
        if not irminsul:
            return web.json_response({"sub_count": 0, "items_today": 0, "items_week": 0})
        now = time.time()
        subs = await irminsul.subscription_list()
        today = await irminsul.feed_items_count(since=now - 86400)
        week = await irminsul.feed_items_count(since=now - 7 * 86400)
        return web.json_response({
            "sub_count": len(subs),
            "items_today": today,
            "items_week": week,
        })

    async def feed_subs_list_api(self, request: web.Request) -> web.Response:
        if not self._check_auth(request):
            return web.json_response({"error": "Unauthorized"}, status=401)
        irminsul = self.state.irminsul
        if not irminsul:
            return web.json_response({"subs": []})
        subs = await irminsul.subscription_list()
        venti = self.state.venti
        out = []
        for s in subs:
            item_count = await irminsul.feed_items_count(sub_id=s.id)
            event_count = await irminsul.feed_event_count(sub_id=s.id)
            out.append({
                "id": s.id,
                "query": s.query,
                "channel_name": s.channel_name,
                "chat_id": s.chat_id,
                "schedule_cron": s.schedule_cron,
                "engine": s.engine,
                "enabled": s.enabled,
                "max_items": s.max_items,
                "last_run_at": s.last_run_at,
                "last_error": s.last_error,
                "created_at": s.created_at,
                "item_count": item_count,
                "event_count": event_count,
                "running": bool(venti and venti.is_running(s.id)),
            })
        return web.json_response({"subs": out})

    async def feed_subs_create_api(self, request: web.Request) -> web.Response:
        """WebUI 新增订阅入口，直接调 core.commands.create_subscription helper。"""
        if not self._check_auth(request):
            return web.json_response({"error": "Unauthorized"}, status=401)
        try:
            data = await request.json()
            query = (data.get("query") or "").strip()
            cron = (data.get("cron") or "").strip()
            engine = (data.get("engine") or "").strip()
        except Exception:
            return web.json_response({"ok": False, "error": "请求体 JSON 无效"}, status=400)

        from paimon.core.commands import create_subscription

        try:
            ok, message = await create_subscription(
                query=query, cron=cron, engine=engine,
                channel_name=self.name,
                chat_id=PUSH_CHAT_ID,
                supports_push=getattr(self, "supports_push", True),
            )
        except Exception as e:
            logger.error("[派蒙·WebUI·订阅] 创建异常: {}", e)
            return web.json_response({"ok": False, "error": str(e)}, status=500)

        if ok:
            return web.json_response({"ok": True, "message": message})
        return web.json_response({"ok": False, "error": message})

    async def feed_subs_patch_api(self, request: web.Request) -> web.Response:
        if not self._check_auth(request):
            return web.json_response({"error": "Unauthorized"}, status=401)
        sub_id = request.match_info["sub_id"]
        try:
            data = await request.json()
        except Exception:
            return web.json_response({"ok": False, "error": "JSON 无效"}, status=400)

        irminsul = self.state.irminsul
        march = self.state.march
        if not irminsul:
            return web.json_response({"ok": False, "error": "世界树未就绪"}, status=500)

        sub = await irminsul.subscription_get(sub_id)
        if not sub:
            return web.json_response({"ok": False, "error": "订阅不存在"}, status=404)

        if "enabled" in data:
            enable = bool(data["enabled"])
            await irminsul.subscription_update(sub_id, actor="WebUI", enabled=enable)
            if sub.linked_task_id and march:
                try:
                    if enable:
                        await march.resume_task(sub.linked_task_id)
                    else:
                        await march.pause_task(sub.linked_task_id)
                except Exception as e:
                    logger.warning("[WebUI·订阅] 同步定时任务启停失败: {}", e)
        return web.json_response({"ok": True})

    async def feed_subs_delete_api(self, request: web.Request) -> web.Response:
        if not self._check_auth(request):
            return web.json_response({"error": "Unauthorized"}, status=401)
        sub_id = request.match_info["sub_id"]
        irminsul = self.state.irminsul
        march = self.state.march
        if not irminsul:
            return web.json_response({"ok": False, "error": "世界树未就绪"}, status=500)

        sub = await irminsul.subscription_get(sub_id)
        if not sub:
            return web.json_response({"ok": False, "error": "订阅不存在"}, status=404)
        if sub.linked_task_id and march:
            try:
                await march.delete_task(sub.linked_task_id)
            except Exception as e:
                logger.warning("[WebUI·订阅] 删定时任务失败: {}", e)
        await irminsul.subscription_delete(sub_id, actor="WebUI")
        return web.json_response({"ok": True})

    async def feed_subs_run_api(self, request: web.Request) -> web.Response:
        if not self._check_auth(request):
            return web.json_response({"error": "Unauthorized"}, status=401)
        sub_id = request.match_info["sub_id"]
        if not self.state.venti or not self.state.irminsul:
            return web.json_response({"ok": False, "error": "风神未就绪"}, status=500)
        sub = await self.state.irminsul.subscription_get(sub_id)
        if not sub:
            return web.json_response({"ok": False, "error": "订阅不存在"}, status=404)
        asyncio.create_task(self.state.venti.collect_subscription(
            sub_id,
            irminsul=self.state.irminsul,
            model=self.state.model,
            march=self.state.march,
        ))
        return web.json_response({"ok": True})

    async def feed_items_api(self, request: web.Request) -> web.Response:
        if not self._check_auth(request):
            return web.json_response({"error": "Unauthorized"}, status=401)
        irminsul = self.state.irminsul
        if not irminsul:
            return web.json_response({"items": []})

        sub_id = request.query.get("sub_id", "").strip() or None
        since_sec = 0
        try:
            since_sec = int(request.query.get("since", "0"))
        except (TypeError, ValueError):
            since_sec = 0
        since_ts = time.time() - since_sec if since_sec > 0 else None

        limit = min(int(request.query.get("limit", "200")), 500)
        items = await irminsul.feed_items_list(
            sub_id=sub_id, since=since_ts, limit=limit,
        )
        return web.json_response({
            "items": [
                {
                    "id": it.id,
                    "subscription_id": it.subscription_id,
                    "url": it.url,
                    "title": it.title,
                    "description": it.description,
                    "engine": it.engine,
                    "captured_at": it.captured_at,
                    "pushed_at": it.pushed_at,
                    "digest_id": it.digest_id,
                }
                for it in items
            ]
        })

    # ---------- 风神 · 舆情看板（L1 事件级） ----------

    async def sentiment_page(self, request: web.Request) -> web.Response:
        if not self._check_auth(request):
            return web.Response(
                text=self._get_login_html(), content_type="text/html",
            )
        from paimon.channels.webui.sentiment_html import build_sentiment_html
        return web.Response(
            text=build_sentiment_html(),
            content_type="text/html",
            headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
        )

    async def sentiment_overview_api(self, request: web.Request) -> web.Response:
        """近 7 天概览：事件总数 + p0/p1 数 + 情感均值 + 活跃订阅数。

        sub_id 为空时返回全局；指定时返回该订阅的子统计 + 订阅元信息（query / 上次跑 /
        下次跑 / feed_items 总数 / 累计推送数），用于 /sentiment 面板的订阅级 banner。
        """
        if not self._check_auth(request):
            return web.json_response({"error": "Unauthorized"}, status=401)
        irminsul = self.state.irminsul
        if not irminsul:
            return web.json_response({
                "events_7d": 0, "p0_count": 0, "p1_count": 0,
                "p0_p1_count": 0, "p2_count": 0, "p3_count": 0,
                "avg_sentiment": 0.0, "sub_count": 0,
            })
        sub_id = request.query.get("sub_id", "").strip() or None
        since = time.time() - 7 * 86400

        events_7d = await irminsul.feed_event_count(since=since, sub_id=sub_id)
        sev = await irminsul.feed_event_count_by_severity(
            since=since, sub_id=sub_id,
        )
        avg = await irminsul.feed_event_avg_sentiment(since=since, sub_id=sub_id)

        result: dict[str, Any] = {
            "events_7d": events_7d,
            "p0_count": sev.get("p0", 0),
            "p1_count": sev.get("p1", 0),
            "p2_count": sev.get("p2", 0),
            "p3_count": sev.get("p3", 0),
            "p0_p1_count": sev.get("p0", 0) + sev.get("p1", 0),
            "avg_sentiment": round(avg, 3),
        }

        if sub_id:
            sub = await irminsul.subscription_get(sub_id)
            if sub:
                # feed_items 累计 / 累计推送 / 上次/下次跑
                feed_items_total = await irminsul.feed_items_count(sub_id=sub_id)
                next_run_at = 0.0
                if sub.linked_task_id:
                    try:
                        task = await irminsul.schedule_get(sub.linked_task_id)
                        next_run_at = float(task.next_run_at) if task else 0.0
                    except Exception:
                        next_run_at = 0.0
                # 累计推送：所有事件 pushed_count 求和
                events_all = await irminsul.feed_event_list(
                    sub_id=sub_id, limit=500,
                )
                pushed_total = sum(int(e.pushed_count or 0) for e in events_all)
                result.update({
                    "sub_id": sub.id,
                    "sub_query": sub.query,
                    "sub_cron": sub.schedule_cron,
                    "sub_engine": sub.engine,
                    "sub_enabled": bool(sub.enabled),
                    "last_run_at": float(sub.last_run_at or 0.0),
                    "next_run_at": next_run_at,
                    "feed_items_total": feed_items_total,
                    "pushed_total": pushed_total,
                    "last_error": sub.last_error or "",
                })
        else:
            subs = await irminsul.subscription_list(enabled_only=True)
            result["sub_count"] = len(subs)

        return web.json_response(result)

    async def sentiment_events_api(self, request: web.Request) -> web.Response:
        """事件列表，按 last_seen_at 倒序。

        Query: days (1-30, 默认 7), severity (p0..p3), sub_id, limit (默认 50, 上限 200)
        """
        if not self._check_auth(request):
            return web.json_response({"error": "Unauthorized"}, status=401)
        irminsul = self.state.irminsul
        if not irminsul:
            return web.json_response({"events": []})
        try:
            days = max(1, min(int(request.query.get("days", "7")), 30))
        except (TypeError, ValueError):
            days = 7
        severity = request.query.get("severity", "").strip() or None
        if severity and severity not in ("p0", "p1", "p2", "p3"):
            return web.json_response(
                {"error": "severity 必须是 p0/p1/p2/p3 之一"}, status=400,
            )
        sub_id = request.query.get("sub_id", "").strip() or None
        try:
            limit = max(1, min(int(request.query.get("limit", "50")), 200))
        except (TypeError, ValueError):
            limit = 50

        since = time.time() - days * 86400
        events = await irminsul.feed_event_list(
            sub_id=sub_id, since=since, severity=severity, limit=limit,
        )
        return web.json_response({
            "events": [
                {
                    "id": ev.id,
                    "subscription_id": ev.subscription_id,
                    "title": ev.title,
                    "summary": ev.summary,
                    "severity": ev.severity,
                    "sentiment_score": ev.sentiment_score,
                    "sentiment_label": ev.sentiment_label,
                    "entities": ev.entities,
                    "sources": ev.sources,
                    "item_count": ev.item_count,
                    "first_seen_at": ev.first_seen_at,
                    "last_seen_at": ev.last_seen_at,
                    "last_pushed_at": ev.last_pushed_at,
                    "pushed_count": ev.pushed_count,
                }
                for ev in events
            ]
        })

    async def sentiment_event_detail_api(
        self, request: web.Request,
    ) -> web.Response:
        """单事件详情 + 关联 feed_items 列表。"""
        if not self._check_auth(request):
            return web.json_response({"error": "Unauthorized"}, status=401)
        irminsul = self.state.irminsul
        if not irminsul:
            return web.json_response({"error": "irminsul 未初始化"}, status=500)
        event_id = request.match_info.get("event_id", "").strip()
        if not event_id:
            return web.json_response({"error": "event_id 必填"}, status=400)
        ev = await irminsul.feed_event_get(event_id)
        if ev is None:
            return web.json_response({"error": "事件不存在"}, status=404)
        items = await irminsul.feed_items_list(event_id=event_id, limit=200)
        return web.json_response({
            "event": {
                "id": ev.id,
                "subscription_id": ev.subscription_id,
                "title": ev.title,
                "summary": ev.summary,
                "entities": ev.entities,
                "timeline": ev.timeline,
                "severity": ev.severity,
                "sentiment_score": ev.sentiment_score,
                "sentiment_label": ev.sentiment_label,
                "sources": ev.sources,
                "item_count": ev.item_count,
                "first_seen_at": ev.first_seen_at,
                "last_seen_at": ev.last_seen_at,
                "last_pushed_at": ev.last_pushed_at,
                "last_severity": ev.last_severity,
                "pushed_count": ev.pushed_count,
            },
            "items": [
                {
                    "id": it.id,
                    "url": it.url,
                    "title": it.title,
                    "description": it.description,
                    "engine": it.engine,
                    "captured_at": it.captured_at,
                }
                for it in items
            ],
        })

    async def sentiment_timeline_api(
        self, request: web.Request,
    ) -> web.Response:
        """按天聚合：events 数 / avg_sentiment / p0-p3 计数。"""
        if not self._check_auth(request):
            return web.json_response({"error": "Unauthorized"}, status=401)
        irminsul = self.state.irminsul
        if not irminsul:
            return web.json_response({"days": []})
        try:
            days = max(1, min(int(request.query.get("days", "14")), 30))
        except (TypeError, ValueError):
            days = 14
        sub_id = request.query.get("sub_id", "").strip() or None
        timeline = await irminsul.feed_event_timeline(days=days, sub_id=sub_id)
        return web.json_response({"days": timeline})

    async def sentiment_sources_api(
        self, request: web.Request,
    ) -> web.Response:
        """信源 Top（按 sources_json flatten 后的域名 count 降序）。"""
        if not self._check_auth(request):
            return web.json_response({"error": "Unauthorized"}, status=401)
        irminsul = self.state.irminsul
        if not irminsul:
            return web.json_response({"sources": []})
        try:
            days = max(1, min(int(request.query.get("days", "7")), 30))
        except (TypeError, ValueError):
            days = 7
        try:
            limit = max(1, min(int(request.query.get("limit", "10")), 50))
        except (TypeError, ValueError):
            limit = 10
        sub_id = request.query.get("sub_id", "").strip() or None
        sources = await irminsul.feed_event_sources_top(
            days=days, limit=limit, sub_id=sub_id,
        )
        return web.json_response({"sources": sources})

    # ---------- 推送归档（替代主动聊天推送）----------

    async def push_archive_unread_api(self, request: web.Request) -> web.Response:
        """全局未读计数 + 按 actor 分组（导航栏红点 30s 轮询）。"""
        if not self._check_auth(request):
            return web.json_response({"error": "Unauthorized"}, status=401)
        irminsul = self.state.irminsul
        if not irminsul:
            return web.json_response({"total": 0, "by_actor": {}})
        grouped = await irminsul.push_archive_count_unread_grouped()
        total = sum(grouped.values())
        return web.json_response({"total": total, "by_actor": grouped})

    async def push_archive_list_api(self, request: web.Request) -> web.Response:
        """归档列表，可按 actor / 仅未读 / 全文搜索过滤。"""
        if not self._check_auth(request):
            return web.json_response({"error": "Unauthorized"}, status=401)
        irminsul = self.state.irminsul
        if not irminsul:
            return web.json_response({"records": []})
        actor = request.query.get("actor", "").strip() or None
        only_unread = request.query.get("unread", "").strip().lower() in ("1", "true", "yes")
        q = (request.query.get("q", "") or "").strip()
        try:
            limit = max(1, min(int(request.query.get("limit", "50")), 200))
        except (TypeError, ValueError):
            limit = 50

        def _parse_ts(name: str) -> float | None:
            raw = (request.query.get(name, "") or "").strip()
            if not raw:
                return None
            try:
                return float(raw)
            except (TypeError, ValueError):
                return None
        since = _parse_ts("since")
        until = _parse_ts("until")

        # 搜索时先大窗口拉再过滤（避免 limit 截断后漏了更早的命中条目）；
        # 没搜索时直接 limit
        fetch_limit = max(limit, 500) if q else limit
        records = await irminsul.push_archive_list(
            actor=actor, only_unread=only_unread,
            since=since, until=until, limit=fetch_limit,
        )
        # 全文搜索：在 message_md / source 上做不区分大小写包含匹配
        if q:
            q_low = q.lower()
            records = [
                r for r in records
                if q_low in (r.message_md or "").lower()
                or q_low in (r.source or "").lower()
            ]
            records = records[:limit]

        return web.json_response({
            "records": [
                {
                    "id": r.id,
                    "source": r.source,
                    "actor": r.actor,
                    "level": r.level,
                    "message_md": r.message_md,
                    "extra": r.extra,
                    "created_at": r.created_at,
                    "read_at": r.read_at,
                }
                for r in records
            ]
        })

    async def push_archive_detail_api(self, request: web.Request) -> web.Response:
        """单条归档详情（看时不自动 mark_read，前端拉完后单独调 read 接口）。"""
        if not self._check_auth(request):
            return web.json_response({"error": "Unauthorized"}, status=401)
        irminsul = self.state.irminsul
        if not irminsul:
            return web.json_response({"error": "世界树未就绪"}, status=500)
        rec_id = request.match_info["rec_id"]
        rec = await irminsul.push_archive_get(rec_id)
        if not rec:
            return web.json_response({"error": "记录不存在"}, status=404)
        return web.json_response({
            "id": rec.id,
            "source": rec.source,
            "actor": rec.actor,
            "level": rec.level,
            "channel_name": rec.channel_name,
            "chat_id": rec.chat_id,
            "message_md": rec.message_md,
            "extra": rec.extra,
            "created_at": rec.created_at,
            "read_at": rec.read_at,
        })

    async def push_archive_mark_read_api(self, request: web.Request) -> web.Response:
        if not self._check_auth(request):
            return web.json_response({"error": "Unauthorized"}, status=401)
        irminsul = self.state.irminsul
        if not irminsul:
            return web.json_response({"ok": False, "error": "世界树未就绪"}, status=500)
        rec_id = request.match_info["rec_id"]
        ok = await irminsul.push_archive_mark_read(rec_id)
        return web.json_response({"ok": ok})

    async def push_archive_mark_read_all_api(self, request: web.Request) -> web.Response:
        if not self._check_auth(request):
            return web.json_response({"error": "Unauthorized"}, status=401)
        irminsul = self.state.irminsul
        if not irminsul:
            return web.json_response({"ok": False, "error": "世界树未就绪"}, status=500)
        actor = request.query.get("actor", "").strip() or None
        n = await irminsul.push_archive_mark_read_all(actor=actor)
        return web.json_response({"ok": True, "marked": n})

    # ---------- 岩神 · 理财面板 ----------

    def _snap_to_dict(self, s) -> dict:
        """ScoreSnapshot → JSON 可序列化 dict。"""
        return {
            "id": s.id,
            "scan_date": s.scan_date,
            "stock_code": s.stock_code,
            "stock_name": s.stock_name,
            "industry": s.industry,
            "total_score": s.total_score,
            "sustainability_score": s.sustainability_score,
            "fortress_score": s.fortress_score,
            "valuation_score": s.valuation_score,
            "track_record_score": s.track_record_score,
            "momentum_score": s.momentum_score,
            "penalty": s.penalty,
            "dividend_yield": s.dividend_yield,
            "pe": s.pe,
            "pb": s.pb,
            "roe": s.roe,
            "market_cap": s.market_cap,
            "reasons": s.reasons,
            "advice": s.advice,
        }

    async def wealth_page(self, request: web.Request) -> web.Response:
        if not self._check_auth(request):
            return web.Response(text=self._get_login_html(), content_type="text/html")
        from paimon.channels.webui.wealth_html import build_wealth_html
        return web.Response(
            text=build_wealth_html(),
            content_type="text/html",
            headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
        )

    async def wealth_stats_api(self, request: web.Request) -> web.Response:
        if not self._check_auth(request):
            return web.json_response({"error": "Unauthorized"}, status=401)
        irminsul = self.state.irminsul
        march = self.state.march
        if not irminsul:
            return web.json_response({
                "watchlist_count": 0, "latest_scan_date": None,
                "changes_7d": 0, "p0_count_7d": 0, "p1_count_7d": 0,
                "cron_enabled": False,
            })
        wl = await irminsul.watchlist_get()
        latest = await irminsul.snapshot_latest_date()
        changes = await irminsul.change_recent(7)
        cron_on = False
        if march:
            tasks = await march.list_tasks()
            # 方案 D：按 task_type 分类（原 task_prompt.startswith("[DIVIDEND_SCAN] ") 2026-04-29 废弃）
            cron_on = any(
                t.task_type == "dividend_scan" and t.enabled
                for t in tasks
            )
        # 近 7 天 P0 / P1 事件累计：从 push_archive(actor="岩神") 的 extra 读 p0/p1_count
        import time as _time
        p0_total = 0
        p1_total = 0
        try:
            recent = await irminsul.push_archive_list(
                actor="岩神",
                since=_time.time() - 7 * 86400,
                limit=50,
            )
            for rec in recent:
                p0_total += int((rec.extra or {}).get("p0_count", 0) or 0)
                p1_total += int((rec.extra or {}).get("p1_count", 0) or 0)
        except Exception as e:
            logger.debug("[WebUI·wealth_stats] 查 P0/P1 失败: {}", e)
        return web.json_response({
            "watchlist_count": len(wl),
            "latest_scan_date": latest,
            "changes_7d": len(changes),
            "p0_count_7d": p0_total,
            "p1_count_7d": p1_total,
            "cron_enabled": cron_on,
        })

    async def wealth_scan_scope_api(self, request: web.Request) -> web.Response:
        """各扫描模式的实际范围数量（给前端按钮下方文案用）。

        candidates_size: 候选池股票数（最近一次全扫描产出，日更扫描的范围）
        watchlist_size:  推荐池股票数（行业均衡选出，公告聚焦对象）
        full_market_size: 全市场参考数（A 股 ~5500，写死方便前端展示）
        """
        if not self._check_auth(request):
            return web.json_response({"error": "Unauthorized"}, status=401)
        irminsul = self.state.irminsul
        if not irminsul:
            return web.json_response({
                "candidates_size": 0, "watchlist_size": 0,
                "full_market_size": 5500,
            })
        # 候选池 = 最近一次全扫描产出的 codes（用 watchlist.last_refresh 当基准）
        last_full_date = await irminsul.watchlist_last_refresh()
        candidates = (
            await irminsul.snapshot_codes_at_date(last_full_date)
            if last_full_date else []
        )
        watchlist = await irminsul.watchlist_get()
        return web.json_response({
            "candidates_size": len(candidates),
            "watchlist_size": len(watchlist),
            "full_market_size": 5500,
        })

    async def wealth_running_api(self, request: web.Request) -> web.Response:
        """岩神采集是否在跑（供 /wealth 公告区"采集中"状态条 + 轮询）。

        progress 字段（仅在 running=true 时有意义）：
        ``{stage, cur, total, started_at, updated_at, ...stage特有字段}``
        - stage ∈ init / board / board_codes / dividend / financial /
          scoring_dividend / scoring_financial / scoring_rescore
        - 前端按 stage 拼"行情扫描 X/Y"等文案

        last_error 字段（10 分钟内的最近一次失败，超出窗口为 null）：
        ``{ts, mode, message, age_seconds}`` —— 前端红色横幅显示
        """
        if not self._check_auth(request):
            return web.json_response({"error": "Unauthorized"}, status=401)
        zhongli = self.state.zhongli
        running = bool(zhongli and zhongli.is_scanning())
        progress = zhongli.get_progress() if (zhongli and running) else None
        last_error = zhongli.get_last_error() if zhongli else None
        return web.json_response({
            "running": running,
            "progress": progress,
            "last_error": last_error,
        })

    async def wealth_recommended_api(self, request: web.Request) -> web.Response:
        if not self._check_auth(request):
            return web.json_response({"error": "Unauthorized"}, status=401)
        irminsul = self.state.irminsul
        if not irminsul:
            return web.json_response({"stocks": []})
        rows = await irminsul.snapshot_latest_for_watchlist()
        return web.json_response({"stocks": [self._snap_to_dict(r) for r in rows]})

    async def wealth_ranking_api(self, request: web.Request) -> web.Response:
        if not self._check_auth(request):
            return web.json_response({"error": "Unauthorized"}, status=401)
        irminsul = self.state.irminsul
        if not irminsul:
            return web.json_response({"stocks": []})
        try:
            n = max(1, min(int(request.query.get("n", "100")), 200))
        except (TypeError, ValueError):
            n = 100
        rows = await irminsul.snapshot_latest_top(n)
        return web.json_response({"stocks": [self._snap_to_dict(r) for r in rows]})

    async def wealth_changes_api(self, request: web.Request) -> web.Response:
        if not self._check_auth(request):
            return web.json_response({"error": "Unauthorized"}, status=401)
        irminsul = self.state.irminsul
        if not irminsul:
            return web.json_response({"changes": []})
        try:
            days = max(1, min(int(request.query.get("days", "30")), 180))
        except (TypeError, ValueError):
            days = 30
        chs = await irminsul.change_recent(days)
        return web.json_response({
            "changes": [
                {
                    "id": c.id,
                    "event_date": c.event_date,
                    "stock_code": c.stock_code,
                    "stock_name": c.stock_name,
                    "event_type": c.event_type,
                    "old_value": c.old_value,
                    "new_value": c.new_value,
                    "description": c.description,
                }
                for c in chs
            ]
        })

    async def wealth_stock_api(self, request: web.Request) -> web.Response:
        if not self._check_auth(request):
            return web.json_response({"error": "Unauthorized"}, status=401)
        irminsul = self.state.irminsul
        if not irminsul:
            return web.json_response({"history": [], "current": None})
        code = request.match_info["code"]
        import re as _re
        if not _re.fullmatch(r"\d{6}", code):
            return web.json_response({"error": "股票代码必须是 6 位数字"}, status=400)
        try:
            days = max(1, min(int(request.query.get("days", "90")), 365))
        except (TypeError, ValueError):
            days = 90
        history = await irminsul.snapshot_history(code, days)
        current = history[-1] if history else None
        return web.json_response({
            "history": [self._snap_to_dict(h) for h in history],
            "current": self._snap_to_dict(current) if current else None,
        })

    async def wealth_trigger_api(self, request: web.Request) -> web.Response:
        if not self._check_auth(request):
            return web.json_response({"error": "Unauthorized"}, status=401)
        if not self.state.zhongli or not self.state.irminsul or not self.state.march:
            return web.json_response({"ok": False, "error": "岩神/世界树/三月未就绪"}, status=500)
        try:
            data = await request.json()
            mode = (data.get("mode") or "").strip()
        except Exception:
            return web.json_response({"ok": False, "error": "JSON 无效"}, status=400)
        if mode not in ("full", "daily", "rescore"):
            return web.json_response({"ok": False, "error": "mode 必须是 full/daily/rescore"}, status=400)

        # 防并发：正在跑时拒绝，避免 full_scan 15 分钟内被多次触发排队
        if self.state.zhongli.is_scanning():
            return web.json_response(
                {"ok": False, "error": "已有扫描在进行中，请等待完成后再触发"},
                status=409,
            )

        asyncio.create_task(self.state.zhongli.collect_dividend(
            mode=mode,
            irminsul=self.state.irminsul,
            march=self.state.march,
            chat_id=PUSH_CHAT_ID,   # 同文件顶部的常量
            channel_name=self.name,
        ))
        return web.json_response({"ok": True, "mode": mode})

    # ---------- 用户关注股（user_watchlist）----------

    @staticmethod
    def _normalize_stock_code(raw: str) -> str | None:
        """用户输入 → baostock 格式 'sh.xxxxxx' / 'sz.xxxxxx'。非法返回 None。

        支持：'600519' / 'sh.600519' / 'SH600519' / 'sh600519'。
        6 开头 → sh，其他 → sz（与 provider_baostock._to_bscode 一致）。
        """
        import re as _re
        if not raw:
            return None
        s = raw.strip().lower().replace(".", "").replace(" ", "")
        m = _re.match(r"^(sh|sz)?(\d{6})$", s)
        if not m:
            return None
        prefix, digits = m.group(1), m.group(2)
        if prefix:
            return f"{prefix}.{digits}"
        # 沪市：6/5/9 开头；深市：0/3 开头
        if digits[0] in "659":
            return f"sh.{digits}"
        return f"sz.{digits}"

    async def _compute_watch_row(self, irminsul, entry) -> dict:
        """把 UserWatchEntry 组装成前端展示用 dict（含最新价、sparkline、PE/PB 分位）。"""
        latest = await irminsul.user_watch_price_latest(entry.stock_code)
        recent = await irminsul.user_watch_price_recent(entry.stock_code, 30)
        pe_series = await irminsul.user_watch_price_series(entry.stock_code, "pe")
        pb_series = await irminsul.user_watch_price_series(entry.stock_code, "pb")

        def percentile(series: list[float], cur: float) -> float | None:
            """当前值在序列中的百分位（0~1）。序列空或当前值 ≤0 时返回 None。"""
            if not series or cur <= 0:
                return None
            below = sum(1 for v in series if v < cur)
            return round(below / len(series), 4)

        # 无数据时用 None 让前端渲染 '-'，0 会被前端当成"涨跌 0%"显示成 '0.00%'
        has_data = bool(latest and latest.close > 0)
        return {
            "stock_code": entry.stock_code,
            "stock_name": entry.stock_name,
            "note": entry.note,
            "added_date": entry.added_date,
            "alert_pct": entry.alert_pct,
            "price": latest.close if has_data else None,
            "change_pct": latest.change_pct if has_data else None,
            "pe": latest.pe if has_data else None,
            "pb": latest.pb if has_data else None,
            "pe_percentile": percentile(pe_series, latest.pe if has_data else 0),
            "pb_percentile": percentile(pb_series, latest.pb if has_data else 0),
            "last_date": latest.date if latest else "",
            "sparkline": [p.close for p in recent],
            "history_count": len(pe_series) or 0,
        }

    async def wealth_user_watch_list_api(self, request: web.Request) -> web.Response:
        if not self._check_auth(request):
            return web.json_response({"error": "Unauthorized"}, status=401)
        irminsul = self.state.irminsul
        if not irminsul:
            return web.json_response({"items": []})
        entries = await irminsul.user_watch_list()
        items = [await self._compute_watch_row(irminsul, e) for e in entries]
        return web.json_response({"items": items})

    async def wealth_user_watch_add_api(self, request: web.Request) -> web.Response:
        if not self._check_auth(request):
            return web.json_response({"error": "Unauthorized"}, status=401)
        irminsul = self.state.irminsul
        if not irminsul:
            return web.json_response({"ok": False, "error": "世界树未就绪"}, status=500)
        try:
            data = await request.json()
        except Exception:
            return web.json_response({"ok": False, "error": "JSON 无效"}, status=400)

        code = self._normalize_stock_code(data.get("code", ""))
        if not code:
            return web.json_response(
                {"ok": False, "error": "股票代码无效（需 6 位数字，可前缀 sh/sz）"},
                status=400,
            )
        note = (data.get("note") or "").strip()[:200]
        try:
            alert_pct = float(data.get("alert_pct", 3.0))
        except (TypeError, ValueError):
            alert_pct = 3.0
        alert_pct = max(0.1, min(alert_pct, 50.0))

        from paimon.foundation.irminsul import UserWatchEntry
        entry = UserWatchEntry(
            stock_code=code, stock_name="",  # 名称由 zhongli 扫描后补齐
            note=note, added_date=date.today().isoformat(),
            alert_pct=alert_pct,
        )
        added = await irminsul.user_watch_add(entry, actor="WebUI")
        if not added:
            return web.json_response({"ok": False, "error": "股票已在关注列表中"}, status=409)

        # 首次添加后异步补抓 3 年历史 + 最新快照（不阻塞请求）
        if self.state.zhongli:
            asyncio.create_task(
                self.state.zhongli.collect_user_watchlist(irminsul)
            )

        return web.json_response({"ok": True, "code": code})

    async def wealth_user_watch_remove_api(self, request: web.Request) -> web.Response:
        if not self._check_auth(request):
            return web.json_response({"error": "Unauthorized"}, status=401)
        irminsul = self.state.irminsul
        if not irminsul:
            return web.json_response({"ok": False, "error": "世界树未就绪"}, status=500)
        try:
            data = await request.json()
        except Exception:
            return web.json_response({"ok": False, "error": "JSON 无效"}, status=400)
        code = self._normalize_stock_code(data.get("code", ""))
        if not code:
            return web.json_response({"ok": False, "error": "股票代码无效"}, status=400)
        ok = await irminsul.user_watch_remove(code, actor="WebUI")
        return web.json_response({"ok": ok})

    async def wealth_user_watch_update_api(self, request: web.Request) -> web.Response:
        if not self._check_auth(request):
            return web.json_response({"error": "Unauthorized"}, status=401)
        irminsul = self.state.irminsul
        if not irminsul:
            return web.json_response({"ok": False, "error": "世界树未就绪"}, status=500)
        try:
            data = await request.json()
        except Exception:
            return web.json_response({"ok": False, "error": "JSON 无效"}, status=400)
        code = self._normalize_stock_code(data.get("code", ""))
        if not code:
            return web.json_response({"ok": False, "error": "股票代码无效"}, status=400)

        note = data.get("note")
        if note is not None:
            note = str(note).strip()[:200]
        alert_pct = data.get("alert_pct")
        if alert_pct is not None:
            try:
                alert_pct = max(0.1, min(float(alert_pct), 50.0))
            except (TypeError, ValueError):
                alert_pct = None

        ok = await irminsul.user_watch_update(
            code, note=note, alert_pct=alert_pct, actor="WebUI",
        )
        return web.json_response({"ok": ok})

    async def wealth_user_watch_refresh_api(self, request: web.Request) -> web.Response:
        """手动触发关注股抓取（不等晚上 cron）。"""
        if not self._check_auth(request):
            return web.json_response({"error": "Unauthorized"}, status=401)
        if not self.state.zhongli or not self.state.irminsul:
            return web.json_response({"ok": False, "error": "岩神/世界树未就绪"}, status=500)
        asyncio.create_task(
            self.state.zhongli.collect_user_watchlist(self.state.irminsul)
        )
        return web.json_response({"ok": True})

    # ==================== 水神·游戏面板（米哈游） ====================

    async def game_page(self, request: web.Request) -> web.Response:
        if not self._check_auth(request):
            return web.Response(text=self._get_login_html(), content_type="text/html")
        from paimon.channels.webui.game_html import build_game_html
        return web.Response(
            text=build_game_html(), content_type="text/html",
            headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
        )

    async def game_overview_api(self, request: web.Request) -> web.Response:
        if not self._check_auth(request):
            return web.json_response({"error": "Unauthorized"}, status=401)
        if not self.state.furina_game:
            return web.json_response({"accounts": []})
        return web.json_response(await self.state.furina_game.overview())

    async def game_qr_create_api(self, request: web.Request) -> web.Response:
        if not self._check_auth(request):
            return web.json_response({"error": "Unauthorized"}, status=401)
        if not self.state.furina_game:
            return web.json_response({"ok": False, "error": "水神未就绪"}, status=500)
        try:
            r = await self.state.furina_game.qr_create()
        except Exception as e:
            return web.json_response({"ok": False, "error": str(e)}, status=500)
        return web.json_response({"ok": True, **r})

    async def game_qr_poll_api(self, request: web.Request) -> web.Response:
        if not self._check_auth(request):
            return web.json_response({"error": "Unauthorized"}, status=401)
        if not self.state.furina_game:
            return web.json_response({"stat": "Error", "msg": "水神未就绪"})
        try:
            r = await self.state.furina_game.qr_poll(
                request.query.get("app_id", "2"),
                request.query.get("ticket", ""),
                request.query.get("device", ""),
            )
        except Exception as e:
            return web.json_response({"stat": "Error", "msg": str(e)})
        return web.json_response(r)

    async def game_unbind_api(self, request: web.Request) -> web.Response:
        if not self._check_auth(request):
            return web.json_response({"error": "Unauthorized"}, status=401)
        irminsul = self.state.irminsul
        if not irminsul:
            return web.json_response({"ok": False, "error": "世界树未就绪"})
        try:
            data = await request.json()
        except Exception:
            return web.json_response({"ok": False, "error": "JSON 无效"}, status=400)
        game = (data.get("game") or "").strip()
        uid = (data.get("uid") or "").strip()
        if game not in ("gs", "sr", "zzz") or not uid:
            return web.json_response({"ok": False, "error": "game/uid 无效"}, status=400)
        ok = await irminsul.mihoyo_account_remove(game, uid, actor="WebUI")
        return web.json_response({"ok": ok})

    async def game_sign_api(self, request: web.Request) -> web.Response:
        if not self._check_auth(request):
            return web.json_response({"error": "Unauthorized"}, status=401)
        if not self.state.furina_game:
            return web.json_response({"ok": False, "msg": "水神未就绪"})
        try:
            data = await request.json()
        except Exception:
            return web.json_response({"ok": False, "msg": "JSON 无效"}, status=400)
        r = await self.state.furina_game.sign_in(data["game"], data["uid"])
        return web.json_response(r)

    async def game_sign_all_api(self, request: web.Request) -> web.Response:
        if not self._check_auth(request):
            return web.json_response({"error": "Unauthorized"}, status=401)
        if not self.state.furina_game:
            return web.json_response({"ok": False, "msg": "水神未就绪"})
        results = await self.state.furina_game.sign_all()
        return web.json_response({"ok": True, "results": results})

    async def game_collect_one_api(self, request: web.Request) -> web.Response:
        """只采单个账号（WebUI 单账号"刷新此账号数据"按钮）。"""
        if not self._check_auth(request):
            return web.json_response({"error": "Unauthorized"}, status=401)
        if not self.state.furina_game:
            return web.json_response({"ok": False, "msg": "水神未就绪"})
        try:
            data = await request.json()
        except Exception:
            return web.json_response({"ok": False, "msg": "JSON 无效"}, status=400)
        game = (data.get("game") or "").strip()
        uid = (data.get("uid") or "").strip()
        if game not in ("gs", "sr", "zzz") or not uid:
            return web.json_response({"ok": False, "msg": "game/uid 无效"}, status=400)
        asyncio.create_task(self.state.furina_game.collect_one(
            game, uid,
            march=self.state.march, chat_id=PUSH_CHAT_ID, channel_name=self.name,
        ))
        return web.json_response({"ok": True})

    async def game_collect_all_api(self, request: web.Request) -> web.Response:
        if not self._check_auth(request):
            return web.json_response({"error": "Unauthorized"}, status=401)
        if not self.state.furina_game:
            return web.json_response({"ok": False, "msg": "水神未就绪"})
        # 异步跑（通常 10~30s，不等它）
        asyncio.create_task(self.state.furina_game.collect_all(
            march=self.state.march,
            chat_id=PUSH_CHAT_ID, channel_name=self.name,
        ))
        return web.json_response({"ok": True})

    async def game_abyss_latest_api(self, request: web.Request) -> web.Response:
        if not self._check_auth(request):
            return web.json_response({"error": "Unauthorized"}, status=401)
        irminsul = self.state.irminsul
        if not irminsul:
            return web.json_response({"abyss": None})
        game = request.query.get("game", "gs")
        uid = request.query.get("uid", "")
        abyss_type = request.query.get("type", "spiral")
        # spiral/poetry/stygian=原神三副本；forgotten_hall/pure_fiction/apocalyptic=崩铁三；shiyu/mem=绝区零
        if abyss_type not in ("spiral", "poetry", "stygian",
                              "forgotten_hall", "pure_fiction", "apocalyptic",
                              "shiyu", "mem"):
            return web.json_response({"error": "type invalid"}, status=400)
        a = await irminsul.mihoyo_abyss_latest(game, uid, abyss_type)
        if not a:
            return web.json_response({"abyss": None})
        return web.json_response({"abyss": {
            "schedule_id": a.schedule_id, "scan_ts": a.scan_ts,
            "max_floor": a.max_floor, "total_star": a.total_star,
            "total_battle": a.total_battle, "total_win": a.total_win,
            "start_time": a.start_time, "end_time": a.end_time,
        }})

    async def game_gacha_import_api(self, request: web.Request) -> web.Response:
        if not self._check_auth(request):
            return web.json_response({"error": "Unauthorized"}, status=401)
        if not self.state.furina_game:
            return web.json_response({"ok": False, "msg": "水神未就绪"})
        try:
            data = await request.json()
        except Exception:
            return web.json_response({"ok": False, "msg": "JSON 无效"}, status=400)
        url = (data.get("url") or "").strip()
        if not url:
            return web.json_response({"ok": False, "msg": "url 必填"}, status=400)
        r = await self.state.furina_game.import_gacha_from_url(url)
        return web.json_response(r)

    async def game_characters_api(self, request: web.Request) -> web.Response:
        if not self._check_auth(request):
            return web.json_response({"error": "Unauthorized"}, status=401)
        irminsul = self.state.irminsul
        if not irminsul:
            return web.json_response({"characters": []})
        game = request.query.get("game", "gs")
        uid = request.query.get("uid", "")
        if not uid:
            return web.json_response({"characters": []})
        chars = await irminsul.mihoyo_character_list(game, uid)
        return web.json_response({"characters": [
            {
                "avatar_id": c.avatar_id, "name": c.name, "element": c.element,
                "rarity": c.rarity, "level": c.level,
                "constellation": c.constellation, "fetter": c.fetter,
                "weapon": c.weapon, "relics": c.relics,
                "icon_url": c.icon_url,
            }
            for c in chars
        ]})

    async def game_gacha_stats_api(self, request: web.Request) -> web.Response:
        if not self._check_auth(request):
            return web.json_response({"error": "Unauthorized"}, status=401)
        if not self.state.furina_game:
            return web.json_response({"stats": None})
        uid = request.query.get("uid", "")
        gacha_type = request.query.get("gacha_type", "301")
        if not uid:
            return web.json_response({"stats": None})
        stats = await self.state.furina_game.gacha_stats(uid, gacha_type)
        return web.json_response({"stats": stats})

    # ==================== 三月·自检面板 ====================

    async def selfcheck_page(self, request: web.Request) -> web.Response:
        if not self._check_auth(request):
            return web.Response(
                text=self._get_login_html(), content_type="text/html",
            )
        from paimon.channels.webui.selfcheck_html import build_selfcheck_html
        cfg = self.state.cfg
        deep_hidden = bool(getattr(cfg, "selfcheck_deep_hidden", True)) if cfg else True
        return web.Response(
            text=build_selfcheck_html(deep_hidden=deep_hidden),
            content_type="text/html",
            headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
        )

    def _run_to_json(self, run) -> dict:
        """SelfcheckRun → JSON dict（给前端 + API 用）"""
        return {
            "id": run.id,
            "kind": run.kind,
            "triggered_at": run.triggered_at,
            "triggered_by": run.triggered_by,
            "status": run.status,
            "duration_seconds": run.duration_seconds,
            "check_args": run.check_args,
            "error": run.error,
            "p0_count": run.p0_count,
            "p1_count": run.p1_count,
            "p2_count": run.p2_count,
            "p3_count": run.p3_count,
            "findings_total": run.findings_total,
            "quick_summary": run.quick_summary,
            "progress": run.progress,  # deep running 期间 watcher 填充
        }

    async def selfcheck_quick_latest_api(
        self, request: web.Request,
    ) -> web.Response:
        if not self._check_auth(request):
            return web.json_response({"error": "Unauthorized"}, status=401)
        svc = self.state.selfcheck
        if not svc:
            return web.json_response({"run": None})
        latest = await svc.latest_run("quick")
        return web.json_response({"run": self._run_to_json(latest) if latest else None})

    async def selfcheck_quick_run_api(
        self, request: web.Request,
    ) -> web.Response:
        if not self._check_auth(request):
            return web.json_response({"error": "Unauthorized"}, status=401)
        svc = self.state.selfcheck
        if not svc:
            return web.json_response({"error": "selfcheck 未启用"}, status=503)
        run = await svc.run_quick(triggered_by="webui")
        return web.json_response({"run": self._run_to_json(run)})

    async def selfcheck_runs_list_api(
        self, request: web.Request,
    ) -> web.Response:
        if not self._check_auth(request):
            return web.json_response({"error": "Unauthorized"}, status=401)
        svc = self.state.selfcheck
        if not svc:
            return web.json_response({"runs": []})
        kind = request.query.get("kind", "").strip() or None
        if kind and kind not in ("quick", "deep"):
            return web.json_response({"error": "kind 必须是 quick 或 deep"}, status=400)
        try:
            limit = max(1, min(int(request.query.get("limit", "50")), 500))
            offset = max(0, int(request.query.get("offset", "0")))
        except (TypeError, ValueError):
            limit, offset = 50, 0
        runs = await svc.list_runs(kind=kind, limit=limit, offset=offset)
        total = await svc.count_runs(kind=kind)
        return web.json_response({
            "runs": [self._run_to_json(r) for r in runs],
            "total": total,
        })

    async def selfcheck_run_detail_api(
        self, request: web.Request,
    ) -> web.Response:
        if not self._check_auth(request):
            return web.json_response({"error": "Unauthorized"}, status=401)
        svc = self.state.selfcheck
        if not svc:
            return web.json_response({"error": "selfcheck 未启用"}, status=503)
        run_id = request.match_info["run_id"]
        run = await svc.get_run(run_id)
        if not run:
            return web.json_response({"error": "not found"}, status=404)
        return web.json_response({"run": self._run_to_json(run)})

    async def selfcheck_run_report_api(
        self, request: web.Request,
    ) -> web.Response:
        if not self._check_auth(request):
            return web.json_response({"error": "Unauthorized"}, status=401)
        svc = self.state.selfcheck
        if not svc:
            return web.json_response({"error": "selfcheck 未启用"}, status=503)
        run_id = request.match_info["run_id"]
        text = await svc.get_report(run_id)
        if text is None:
            return web.Response(text="report.md 不存在（Quick 记录或 Deep 未完成）", status=404)
        return web.Response(
            text=text,
            content_type="text/markdown",
            charset="utf-8",
            headers={
                "Content-Disposition": f'inline; filename="report-{run_id[:8]}.md"',
            },
        )

    async def selfcheck_run_findings_api(
        self, request: web.Request,
    ) -> web.Response:
        if not self._check_auth(request):
            return web.json_response({"error": "Unauthorized"}, status=401)
        svc = self.state.selfcheck
        if not svc:
            return web.json_response({"findings": []})
        run_id = request.match_info["run_id"]
        findings = await svc.get_findings(run_id)
        return web.json_response({"findings": findings, "count": len(findings)})

    async def selfcheck_run_quick_api(
        self, request: web.Request,
    ) -> web.Response:
        if not self._check_auth(request):
            return web.json_response({"error": "Unauthorized"}, status=401)
        svc = self.state.selfcheck
        if not svc:
            return web.json_response({"snapshot": None})
        run_id = request.match_info["run_id"]
        snap = await svc.get_quick_snapshot(run_id)
        return web.json_response({"snapshot": snap})

    async def selfcheck_run_delete_api(
        self, request: web.Request,
    ) -> web.Response:
        if not self._check_auth(request):
            return web.json_response({"error": "Unauthorized"}, status=401)
        svc = self.state.selfcheck
        if not svc:
            return web.json_response({"error": "selfcheck 未启用"}, status=503)
        run_id = request.match_info["run_id"]
        ok = await svc.delete_run(run_id)
        return web.json_response({"ok": ok})

    async def selfcheck_deep_run_api(
        self, request: web.Request,
    ) -> web.Response:
        if not self._check_auth(request):
            return web.json_response({"error": "Unauthorized"}, status=401)
        # Deep 暂缓开关（docs/todo.md §三月·自检·Deep 暂缓）
        cfg = self.state.cfg
        if cfg and getattr(cfg, "selfcheck_deep_hidden", True):
            return web.json_response(
                {
                    "error": "Deep 自检当前暂缓（LLM 执行不充分）",
                    "hint": "换 Claude Opus 级模型后设 SELFCHECK_DEEP_HIDDEN=false",
                },
                status=503,
            )
        svc = self.state.selfcheck
        if not svc:
            return web.json_response({"error": "selfcheck 未启用"}, status=503)
        try:
            data = await request.json() if request.body_exists else {}
        except Exception:
            data = {}
        args = (data.get("args") or "").strip() or None
        result = await svc.run_deep(args=args, triggered_by="webui")
        status = 200 if result.get("started") else 409
        return web.json_response(result, status=status)

    # ==================== /三月·自检面板 ====================

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

        # 方案 D：不再过滤内部任务；内部类型经 task_types registry 查元信息注入 source 段，
        # 前端据此渲染 chip + 跳转链接 + 禁用启停，避免双写冲突同时保持可见性
        from paimon.foundation import task_types as _tt

        tasks = await march.list_tasks()
        rows: list[dict] = []
        for t in tasks:
            row = {
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
                "task_type": t.task_type or "user",
                "source_entity_id": t.source_entity_id or "",
            }
            if t.task_type and t.task_type != "user":
                meta = _tt.get(t.task_type)
                if meta:
                    desc = ""
                    if meta.description_builder:
                        try:
                            desc = await meta.description_builder(
                                t.source_entity_id, self.state.irminsul,
                            )
                        except Exception as e:
                            logger.debug(
                                "[WebUI·tasks] description_builder 失败 {}: {}",
                                t.task_type, e,
                            )
                            desc = t.source_entity_id or ""
                    else:
                        desc = t.source_entity_id or ""
                    anchor = ""
                    if meta.anchor_builder and t.source_entity_id:
                        try:
                            anchor = meta.anchor_builder(t.source_entity_id)
                        except Exception:
                            anchor = ""
                    jump_url = (
                        f"{meta.manager_panel}#{anchor}"
                        if anchor else meta.manager_panel
                    )
                    row["source"] = {
                        "task_type": t.task_type,
                        "label": meta.display_label,
                        "icon": meta.icon,
                        "description": desc,
                        "jump_url": jump_url,
                        "manager_panel": meta.manager_panel,
                        "editable": False,   # 内部类型统一禁止 /tasks 编辑
                    }
                else:
                    # 未注册类型：展示 ❓ chip + 允许手动删除做孤儿清理
                    row["source"] = {
                        "task_type": t.task_type,
                        "label": f"❓ {t.task_type}",
                        "icon": "",
                        "description": t.source_entity_id or "（未知来源）",
                        "jump_url": "",
                        "manager_panel": "",
                        "editable": False,
                    }
            rows.append(row)

        return web.json_response({"tasks": rows})

    async def tasks_complex_list_api(self, request: web.Request) -> web.Response:
        """四影任务列表（docs/interaction.md §四 WebUI tab）。

        筛选规则与 /task-list 指令一致：creator startswith '派蒙' +
        lifecycle_stage != 'archived' + 7 天内 + 取 20 条（按 updated_at DESC）。
        """
        if self.require_auth:
            token = request.cookies.get("paimon_token")
            if not token or token not in self.valid_tokens:
                return web.json_response({"error": "Unauthorized"}, status=401)

        irminsul = self.state.irminsul
        if not irminsul:
            return web.json_response({"tasks": []})

        import time as _time
        edicts = await irminsul.task_list(limit=50)
        now = _time.time()
        cutoff = now - 7 * 86400

        items = [
            e for e in edicts
            if (e.creator or "").startswith("派蒙")
            and e.lifecycle_stage != "archived"
            and (e.updated_at or e.created_at) >= cutoff
        ][:20]

        # 拉子任务计数（顺手汇总；任务数 ≤ 20，单 query 数量可控）
        out = []
        for e in items:
            try:
                subs = await irminsul.subtask_list(e.id)
                sub_total = len(subs)
                sub_done = sum(1 for s in subs if s.status == "completed")
                sub_failed = sum(1 for s in subs if s.status == "failed")
            except Exception as ex:
                logger.debug("[四影面板] 子任务计数失败 task={}: {}", e.id[:8], ex)
                sub_total = sub_done = sub_failed = 0
            end_ts = e.archived_at or e.updated_at or 0
            duration = (end_ts - e.created_at) if e.created_at and end_ts > e.created_at else 0
            out.append({
                "id": e.id,
                "title": e.title,
                "status": e.status,
                "lifecycle_stage": e.lifecycle_stage,
                "creator": e.creator,
                "session_id": e.session_id,
                "created_at": e.created_at,
                "updated_at": e.updated_at,
                "archived_at": e.archived_at,
                "duration_seconds": int(duration),
                "subtask_total": sub_total,
                "subtask_completed": sub_done,
                "subtask_failed": sub_failed,
            })
        return web.json_response({"tasks": out})

    async def tasks_complex_detail_api(self, request: web.Request) -> web.Response:
        """四影任务详情（用于面板 modal）。"""
        if self.require_auth:
            token = request.cookies.get("paimon_token")
            if not token or token not in self.valid_tokens:
                return web.json_response({"error": "Unauthorized"}, status=401)

        task_id = request.match_info["task_id"]
        irminsul = self.state.irminsul
        if not irminsul:
            return web.json_response({"error": "irminsul not ready"}, status=503)

        edict = await irminsul.task_get(task_id)
        if not edict:
            return web.json_response({"error": "not found"}, status=404)

        subtasks = await irminsul.subtask_list(task_id)
        end_ts = edict.archived_at or edict.updated_at or 0
        duration = (end_ts - edict.created_at) if edict.created_at and end_ts > edict.created_at else 0

        # 摘要：复用 /task-index 同款 fallback 链（workspace summary.md →
        # push_archive 终局消息 → subtask.result 拼接 → 诊断兜底）
        from paimon.shades._task_summary import resolve_task_summary
        summary_md = await resolve_task_summary(
            irminsul, task_id, subtasks, max_chars=5000,
        )

        return web.json_response({
            "task": {
                "id": edict.id,
                "title": edict.title,
                "description": edict.description,
                "status": edict.status,
                "lifecycle_stage": edict.lifecycle_stage,
                "creator": edict.creator,
                "session_id": edict.session_id,
                "created_at": edict.created_at,
                "updated_at": edict.updated_at,
                "archived_at": edict.archived_at,
                "duration_seconds": int(duration),
            },
            "subtasks": [
                {
                    "id": s.id,
                    "assignee": s.assignee,
                    "description": s.description,
                    "status": s.status,
                    "verdict_status": s.verdict_status,
                    "round": s.round,
                    "result": (s.result or "")[:1500],
                    "created_at": s.created_at,
                    "updated_at": s.updated_at,
                }
                for s in subtasks
            ],
            "summary_md": summary_md,
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
            except (ConnectionResetError, ConnectionError, asyncio.CancelledError):
                connection_closed = True
                logger.info("[派蒙·WebUI] SSE连接断开 session={}", session_id[:8])
                raise
            except Exception as e:
                logger.error("[派蒙·WebUI] SSE发送失败: {}", e)
                raise

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
        self._active_replies[chat_id] = reply

        msg = IncomingMessage(
            channel_name=self.name,
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
            # 无论上面走哪条分支（含早退 return / 异常），都清理活跃回调 + 停 watchdog
            self._active_replies.pop(chat_id, None)
            watchdog_task.cancel()
            try:
                await watchdog_task
            except (asyncio.CancelledError, Exception):
                pass

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
