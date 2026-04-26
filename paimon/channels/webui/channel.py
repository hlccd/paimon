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
        self.app.router.add_get("/preferences", self.preferences_page)
        self.app.router.add_get("/api/preferences/list", self.preferences_list_api)
        self.app.router.add_post("/api/preferences/delete", self.preferences_delete_api)
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

    async def preferences_page(self, request: web.Request) -> web.Response:
        if self.require_auth:
            token = request.cookies.get("paimon_token")
            if not token or token not in self.valid_tokens:
                return web.Response(text=self._get_login_html(), content_type="text/html")

        from paimon.channels.webui.preferences_html import build_preferences_html
        return web.Response(
            text=build_preferences_html(),
            content_type="text/html",
            headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
        )

    async def preferences_list_api(self, request: web.Request) -> web.Response:
        """列 L1 记忆（仅 user / feedback），含完整 body 和 preview。"""
        if self.require_auth:
            token = request.cookies.get("paimon_token")
            if not token or token not in self.valid_tokens:
                return web.json_response({"error": "Unauthorized"}, status=401)

        mem_type = request.query.get("mem_type", "").strip()
        if mem_type not in ("user", "feedback"):
            return web.json_response(
                {"error": "mem_type 必须是 user 或 feedback"}, status=400,
            )

        irminsul = self.state.irminsul
        if not irminsul:
            return web.json_response({"items": []})

        try:
            metas = await irminsul.memory_list(mem_type=mem_type, limit=200)
        except Exception as e:
            logger.error("[派蒙·偏好面板] 列记忆异常 type={}: {}", mem_type, e)
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

    async def preferences_delete_api(self, request: web.Request) -> web.Response:
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
            logger.error("[派蒙·偏好面板] 删除记忆异常: {}", e)
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
        out = []
        for s in subs:
            count = await irminsul.feed_items_count(sub_id=s.id)
            out.append({
                "id": s.id,
                "query": s.query,
                "channel_name": s.channel_name,
                "chat_id": s.chat_id,
                "schedule_cron": s.schedule_cron,
                "engine": s.engine,
                "enabled": s.enabled,
                "last_run_at": s.last_run_at,
                "last_error": s.last_error,
                "created_at": s.created_at,
                "item_count": count,
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

        # 搜索时先大窗口拉再过滤（避免 limit 截断后漏了更早的命中条目）；
        # 没搜索时直接 limit
        fetch_limit = max(limit, 500) if q else limit
        records = await irminsul.push_archive_list(
            actor=actor, only_unread=only_unread, limit=fetch_limit,
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
                "changes_7d": 0, "cron_enabled": False,
            })
        wl = await irminsul.watchlist_get()
        latest = await irminsul.snapshot_latest_date()
        changes = await irminsul.change_recent(7)
        cron_on = False
        if march:
            tasks = await march.list_tasks()
            cron_on = any(
                t.task_prompt.startswith("[DIVIDEND_SCAN] ") and t.enabled
                for t in tasks
            )
        return web.json_response({
            "watchlist_count": len(wl),
            "latest_scan_date": latest,
            "changes_7d": len(changes),
            "cron_enabled": cron_on,
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

        tasks = await march.list_tasks()
        # 过滤专用内部任务（归各自面板管理，避免冲突启停）：
        # - [FEED_COLLECT]  → /feed 信息流面板
        # - [DIVIDEND_SCAN] → /wealth 理财面板 + /dividend 指令
        tasks = [
            t for t in tasks
            if not t.task_prompt.startswith("[FEED_COLLECT] ")
            and not t.task_prompt.startswith("[DIVIDEND_SCAN] ")
        ]
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
