"""dividend — 红利股追踪管理工具（岩神）

让派蒙（天使 tool-loop）识别「红利股推荐 / 茅台最近怎样 / 最新变化」自然语言
自动调岩神查询 API 或触发采集。

本工具不绕业务层：所有操作经 `state.zhongli.*` 或 `core.commands.dividend` helper。
"""
from __future__ import annotations

import re
from typing import Any

from paimon.tools.base import BaseTool, ToolContext


_VALID_ACTIONS = {
    "top", "recommended", "changes", "history", "query",
    "trigger_full", "trigger_daily", "rescore",
    "cron_on", "cron_off",
}


class DividendTool(BaseTool):
    name = "dividend"
    description = (
        "管理**红利股追踪**（岩神后台 cron 扫描 A 股 + 评分 + 推送）。\n"
        "action ∈ top / recommended / changes / history / query / trigger_full / "
        "trigger_daily / rescore / cron_on / cron_off。\n"
        "**何时用**：用户问「红利股推荐」/「某股票（如茅台/601988）最近评分怎样」/"
        "「最近红利股变化」/「帮我全扫一下红利股」/「开启红利股定时推送」。\n"
        "**不要用** schedule/subscribe——这是专用红利股工具，走世界树 dividend 域 + "
        "skill dividend-tracker 数据源。\n"
        "**查询优先读数据库**（top/recommended/changes 秒级）；触发扫描耗时 15+ 分钟（full）"
        "或 ≤1 分钟（daily/rescore），尽量只在用户明确要求时调。"
    )
    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": list(_VALID_ACTIONS),
                "description": "操作类型",
            },
            "n": {
                "type": "integer",
                "description": "top N（action=top 时用，默认 20，上限 100）",
            },
            "days": {
                "type": "integer",
                "description": "查询近 N 天（changes / history 用，默认 7/90）",
            },
            "code": {
                "type": "string",
                "description": "6 位股票代码（action=history 必填）例：600519",
            },
            "query": {
                "type": "string",
                "description": "自由文本查询（action=query 时用，让岩神自然语言分派）",
            },
        },
        "required": ["action"],
    }

    async def execute(self, ctx: ToolContext, **kwargs: Any) -> str:
        from paimon.state import state

        if not state.zhongli or not state.irminsul:
            return "❌ 岩神未就绪"

        action = kwargs.get("action", "")
        if action not in _VALID_ACTIONS:
            return f"❌ 未知 action: {action}"

        zhongli = state.zhongli
        irminsul = state.irminsul

        # -------- 查询类（秒级）--------

        if action == "top":
            n = max(1, min(int(kwargs.get("n") or 20), 100))
            rows = await zhongli.get_top(n, irminsul)
            if not rows:
                return "暂无评分数据，请先跑 trigger_daily 或 trigger_full"
            return zhongli._format_ranking(rows)

        if action == "recommended":
            rows = await zhongli.get_recommended(irminsul)
            if not rows:
                return "暂无推荐，请先跑 trigger_full"
            return zhongli._format_recommended_snapshots(rows)

        if action == "changes":
            days = max(1, min(int(kwargs.get("days") or 7), 90))
            chs = await zhongli.get_changes(days, irminsul)
            if not chs:
                return f"最近 {days} 天无显著变化"
            return zhongli._format_changes_list(chs)

        if action == "history":
            code = (kwargs.get("code") or "").strip()
            if not code:
                # 尝试从 query 字段里提取
                q = (kwargs.get("query") or "").strip()
                m = re.search(r"(\d{6})", q)
                if m:
                    code = m.group(1)
            if not code or not re.fullmatch(r"\d{6}", code):
                return "❌ history 需要 6 位股票代码（code='600519'）"
            days = max(1, min(int(kwargs.get("days") or 90), 365))
            history = await zhongli.get_stock_history(code, days, irminsul)
            return zhongli._format_history(code, history)

        if action == "query":
            text = (kwargs.get("query") or "").strip()
            if not text:
                return "❌ query 需要传 query 字段（自然语言查询文本）"
            return await zhongli.handle_query(text, irminsul)

        # -------- 触发类（后台 task 异步跑）--------

        if action in ("trigger_full", "trigger_daily", "rescore"):
            if not state.march:
                return "❌ 三月未就绪"
            if zhongli.is_scanning():
                return "❌ 已有扫描在进行，请等待完成后再触发"
            mode = {
                "trigger_full": "full",
                "trigger_daily": "daily",
                "rescore": "rescore",
            }[action]
            channel_name = ctx.channel.name if ctx.channel else "webui"

            import asyncio as _asyncio
            _asyncio.create_task(zhongli.collect_dividend(
                mode=mode,
                irminsul=irminsul,
                march=state.march,
                chat_id=ctx.chat_id,
                channel_name=channel_name,
            ))
            hint = {
                "full": "全市场扫描约 15-20 分钟，完成后会自动推送报告",
                "daily": "watchlist 日更约 30-60 秒，完成后自动推送",
                "rescore": "缓存重评分几秒内完成",
            }[mode]
            return f"已触发红利股 {mode}：{hint}。查询可用 action=top/recommended"

        # -------- cron 启停（委托给 core.commands helper）--------

        if action in ("cron_on", "cron_off"):
            from paimon.core.commands import toggle_dividend_cron
            channel_name = ctx.channel.name if ctx.channel else "webui"
            enable = action == "cron_on"
            ok, msg = await toggle_dividend_cron(
                enable=enable,
                channel_name=channel_name,
                chat_id=ctx.chat_id,
            )
            return msg if ok else f"❌ {msg}"

        return f"❌ 未处理的 action: {action}"
