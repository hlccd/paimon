"""subscribe — 话题订阅管理工具（风神）

让派蒙（天使 tool-loop）识别自然语言「每 N 分钟给我推送 xxx」自动建订阅，
不必让用户手动 /subscribe。

本工具不绕过既有写入链路：内部调 `paimon.core.commands.create_subscription`
helper，与 /subscribe / WebUI 面板走同一路径（含 cron 校验、回滚、级联）。
"""
from __future__ import annotations

import time
from typing import Any

from paimon.tools.base import BaseTool, ToolContext


class SubscribeTool(BaseTool):
    name = "subscribe"
    description = (
        "管理**话题订阅**（风神定时采集 web-search 结果 → LLM 写日报 → 归档到面板）。\n"
        "action ∈ create / list / delete / run / pause / resume / latest_digest。\n"
        "**何时用**：用户说「订阅 / 每 N 分钟给我推送某主题的最新消息 / 关注某话题」"
        "或者**问「今天的舆情怎么样 / 最近的新闻 / 风神最新一篇日报」**（用 latest_digest）。\n"
        "**不要用** schedule 工具做这个——schedule 只是到点发 prompt 给 LLM 跑一次，"
        "本工具会落库 + 去重 + 日报化归档。\n"
        "**注意**：日报不再主动推送到聊天，只归档到 /sentiment 面板和推送抽屉；"
        "用户问起时务必用 latest_digest 把内容拉出来复述。"
    )
    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["create", "list", "delete", "run", "pause", "resume", "latest_digest"],
                "description": "操作类型",
            },
            "query": {
                "type": "string",
                "description": "搜索关键词（create 时必填），例: '小米 SU7'",
            },
            "cron": {
                "type": "string",
                "description": (
                    "5 字段 cron 表达式（create 可选，默认 '0 10 * * *' 每日 10 点）"
                    "。例: '*/30 * * * *' 每 30 分钟；'0 9 * * 1-5' 工作日 9 点。"
                    "注意三月轮询粒度是分钟，小于 1 分钟无意义。"
                ),
            },
            "engine": {
                "type": "string",
                "enum": ["", "bing", "baidu"],
                "description": "搜索引擎（create 可选）：空=双引擎并发 / bing / baidu",
            },
            "sub_id": {
                "type": "string",
                "description": (
                    "目标订阅（delete/run/pause/resume 必填，latest_digest 可选缩窄到指定订阅）。"
                    "支持：完整 id / id 前缀（8 字即可）/ query 关键词模糊匹配。"
                    "例如用户说「删掉小米订阅」可直接传 '小米'。"
                ),
            },
            "limit": {
                "type": "integer",
                "description": "latest_digest 时拉取最近 N 篇（默认 1，上限 5）",
            },
        },
        "required": ["action"],
    }

    async def execute(self, ctx: ToolContext, **kwargs: Any) -> str:
        from paimon.state import state

        if not state.irminsul:
            return "世界树未就绪"

        action = kwargs.get("action", "")
        if action == "create":
            return await self._create(ctx, kwargs)
        if action == "list":
            return await self._list()
        if action == "latest_digest":
            return await self._latest_digest(kwargs)
        if action in ("delete", "run", "pause", "resume"):
            return await self._manage(action, kwargs.get("sub_id", ""))
        return f"未知 action: {action}"

    async def _latest_digest(self, kwargs: dict) -> str:
        """从推送归档里拉风神最近的 N 篇 digest（用户问「今天舆情怎样」时调）。"""
        from paimon.state import state

        try:
            limit = int(kwargs.get("limit", 1) or 1)
        except (TypeError, ValueError):
            limit = 1
        limit = max(1, min(limit, 5))

        sub_id_arg = (kwargs.get("sub_id") or "").strip()
        target_query = ""
        if sub_id_arg:
            # 模糊解析订阅，缩窄到指定订阅的 digest
            sub = await state.irminsul.subscription_get(sub_id_arg)
            if not sub:
                all_subs = await state.irminsul.subscription_list()
                arg_lower = sub_id_arg.lower()
                matches = (
                    [s for s in all_subs if s.id.startswith(sub_id_arg)]
                    or [s for s in all_subs if arg_lower in s.query.lower()]
                )
                if matches:
                    sub = matches[0]
            if sub:
                target_query = sub.query

        # 拉风神 actor 的归档（按 created_at 降序）
        records = await state.irminsul.push_archive_list(
            actor="风神", limit=20,
        )
        if target_query:
            # 二次过滤：日报 message_md 通常含订阅 query，做包含匹配
            records = [
                r for r in records
                if target_query in r.message_md or target_query in r.source
            ]

        records = records[:limit]
        if not records:
            hint = f"（订阅: {target_query}）" if target_query else ""
            return f"暂无风神日报归档{hint}。可能尚未触发采集，或订阅不存在。"

        out = []
        for r in records:
            ts = time.strftime("%m-%d %H:%M", time.localtime(r.created_at))
            unread = " [未读]" if r.read_at is None else ""
            out.append(f"## 【{r.source}】{ts}{unread}\n\n{r.message_md}")
        return "\n\n---\n\n".join(out)

    async def _create(self, ctx: ToolContext, kwargs: dict) -> str:
        from paimon.core.commands import create_subscription

        # 当前频道名，避免硬编码（与 schedule tool 同样处理）
        channel_name = ctx.channel.name if ctx.channel else "webui"
        supports_push = getattr(ctx.channel, "supports_push", True) if ctx.channel else True

        ok, msg = await create_subscription(
            query=kwargs.get("query", ""),
            cron=kwargs.get("cron", ""),
            engine=kwargs.get("engine", ""),
            channel_name=channel_name,
            chat_id=ctx.chat_id,
            supports_push=supports_push,
        )
        # 明确标记成败，防 LLM 误读错误消息为成功
        return msg if ok else f"❌ 订阅创建失败: {msg}"

    async def _list(self) -> str:
        from paimon.state import state

        subs = await state.irminsul.subscription_list()
        if not subs:
            return "暂无订阅"
        lines = ["订阅列表:"]
        for s in subs:
            status = "启用" if s.enabled else "停用"
            last_run = (
                time.strftime("%m-%d %H:%M", time.localtime(s.last_run_at))
                if s.last_run_at > 0 else "-"
            )
            count = await state.irminsul.feed_items_count(sub_id=s.id)
            err = f" [错: {s.last_error[:40]}]" if s.last_error else ""
            lines.append(
                f"  #{s.id[:8]} | {status} | {s.query[:30]} | "
                f"{s.schedule_cron} | 累计 {count} 条 | 上次 {last_run}{err}"
            )
        return "\n".join(lines)

    async def _manage(self, action: str, sub_id_arg: str) -> str:
        from paimon.state import state

        sub_id_arg = (sub_id_arg or "").strip()
        if not sub_id_arg:
            return "缺少 sub_id"

        # id 精确 → id 前缀 → query 子串模糊
        sub = await state.irminsul.subscription_get(sub_id_arg)
        if not sub:
            all_subs = await state.irminsul.subscription_list()
            matches = [s for s in all_subs if s.id.startswith(sub_id_arg)]
            if not matches:
                # 按 query 模糊匹配（用户可能直接传关键词）
                arg_lower = sub_id_arg.lower()
                matches = [s for s in all_subs if arg_lower in s.query.lower()]
            if len(matches) == 1:
                sub = matches[0]
            elif len(matches) > 1:
                hints = " / ".join(f"#{s.id[:8]} {s.query}" for s in matches[:5])
                return f"❌ '{sub_id_arg}' 匹配多个订阅: {hints}，请指定更精确的 ID 或关键词"
            else:
                return f"❌ 未找到订阅: {sub_id_arg}"

        march = state.march

        if action == "delete":
            if sub.linked_task_id and march:
                try:
                    await march.delete_task(sub.linked_task_id)
                except Exception:
                    pass
            await state.irminsul.subscription_delete(sub.id, actor="派蒙·工具")
            return f"订阅 #{sub.id[:8]} 已删除（级联清除 feed_items + 定时任务）"

        if action == "run":
            if not state.venti:
                return "风神未就绪"
            import asyncio as _asyncio
            _asyncio.create_task(state.venti.collect_subscription(
                sub.id,
                irminsul=state.irminsul, model=state.model, march=march,
            ))
            return f"已手动触发 #{sub.id[:8]} ({sub.query})，稍后查看推送"

        if action == "pause":
            await state.irminsul.subscription_update(
                sub.id, actor="派蒙·工具", enabled=False,
            )
            if sub.linked_task_id and march:
                try:
                    await march.pause_task(sub.linked_task_id)
                except Exception:
                    pass
            return f"订阅 #{sub.id[:8]} 已停用"

        if action == "resume":
            await state.irminsul.subscription_update(
                sub.id, actor="派蒙·工具", enabled=True,
            )
            if sub.linked_task_id and march:
                try:
                    await march.resume_task(sub.linked_task_id)
                except Exception:
                    pass
            return f"订阅 #{sub.id[:8]} 已启用"

        return f"未知 action: {action}"
