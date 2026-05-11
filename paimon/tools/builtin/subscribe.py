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
        "管理**话题订阅**（风神每天定时跑 topic UGC 调研 → 覆盖式落表 → /feed 面板渲染）。\n"
        "action ∈ create / list / delete / run / pause / resume / latest_digest。\n"
        "**何时用**：用户说「订阅某话题 / 关注某话题 / 每天给我跑一份某话题的资讯」"
        "或者**问「最近某话题怎么样 / 最近的新闻」**（用 latest_digest 拉最新调研结果）。\n"
        "**不要用** schedule 工具做这个——schedule 只是到点发 prompt 给 LLM 跑一次，"
        "本工具会落库 + 持久订阅 + 每天定时刷新 markdown。\n"
        "topic 调研走 5 源 UGC（B 站/小红书/知乎/贴吧/微博）30 天窗口，覆盖式存最新一份，不主动推送到聊天。"
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
                "description": "调研关键词（create 时必填），例: '小米 SU7'",
            },
            "cron": {
                "type": "string",
                "description": (
                    "5 字段 cron 表达式（create 可选，默认 '0 7 * * *' 每日 7 点）。"
                    "例: '0 9 * * 1-5' 工作日 9 点。三月轮询粒度是分钟。"
                ),
            },
            "sub_id": {
                "type": "string",
                "description": (
                    "目标订阅（delete/run/pause/resume 必填，latest_digest 可选缩窄到指定订阅）。"
                    "支持：完整 id / id 前缀（8 字即可）/ query 关键词模糊匹配。"
                    "例如用户说「删掉小米订阅」可直接传 '小米'。"
                ),
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
        """拉指定订阅最近一份 topic 调研结果（覆盖式 markdown）。"""
        from paimon.state import state

        sub_id_arg = (kwargs.get("sub_id") or "").strip()
        if not sub_id_arg:
            # 没指定 sub_id 时列出所有 topic 订阅最新结果摘要
            subs = await state.irminsul.subscription_list_by_binding("topic_research")
            if not subs:
                return "暂无 topic 订阅。可用 create 创建。"
            lines = []
            for s in subs:
                rec = await state.irminsul.feed_topic_research_get(s.id)
                if not rec or not rec.get("markdown"):
                    lines.append(f"## #{s.id[:8]} {s.query}\n（暂无内容，cron 还没跑过）")
                else:
                    lines.append(f"## #{s.id[:8]} {s.query}\n\n{rec['markdown']}")
            return "\n\n---\n\n".join(lines)

        # 模糊解析订阅
        sub = await state.irminsul.subscription_get(sub_id_arg)
        if not sub:
            all_subs = await state.irminsul.subscription_list_by_binding("topic_research")
            arg_lower = sub_id_arg.lower()
            matches = (
                [s for s in all_subs if s.id.startswith(sub_id_arg)]
                or [s for s in all_subs if arg_lower in s.query.lower()]
            )
            sub = matches[0] if matches else None
        if not sub:
            return f"未找到订阅: {sub_id_arg}"

        rec = await state.irminsul.feed_topic_research_get(sub.id)
        if not rec or not rec.get("markdown"):
            return f"订阅「{sub.query}」暂无调研结果（cron 还没跑过 / 首次创建可触发 run）。"
        return f"## #{sub.id[:8]} {sub.query}\n\n{rec['markdown']}"

    async def _create(self, ctx: ToolContext, kwargs: dict) -> str:
        from paimon.core.commands import create_subscription

        channel_name = ctx.channel.name if ctx.channel else "webui"
        supports_push = getattr(ctx.channel, "supports_push", True) if ctx.channel else True

        ok, msg = await create_subscription(
            query=kwargs.get("query", ""),
            cron=kwargs.get("cron", ""),
            channel_name=channel_name,
            chat_id=ctx.chat_id,
            supports_push=supports_push,
        )
        return msg if ok else f"❌ 订阅创建失败: {msg}"

    async def _list(self) -> str:
        from paimon.state import state

        subs = await state.irminsul.subscription_list_by_binding("topic_research")
        if not subs:
            return "暂无订阅"
        lines = ["订阅列表:"]
        for s in subs:
            status = "启用" if s.enabled else "停用"
            last_run = (
                time.strftime("%m-%d %H:%M", time.localtime(s.last_run_at))
                if s.last_run_at > 0 else "-"
            )
            err = f" [错: {s.last_error[:40]}]" if s.last_error else ""
            lines.append(
                f"  #{s.id[:8]} | {status} | {s.query[:30]} | "
                f"{s.schedule_cron} | 上次 {last_run}{err}"
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
            from paimon.foundation.bg import bg
            bg(state.venti.collect_subscription(
                sub.id,
                irminsul=state.irminsul, model=state.model, march=march,
            ), label=f"venti·订阅采集·{sub.id[:8]}·tool")
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
