"""schedule — 定时任务管理工具（三月调度）"""
from __future__ import annotations

import json
import time
from typing import Any

from paimon.tools.base import BaseTool, ToolContext


class ScheduleTool(BaseTool):
    name = "schedule"
    description = (
        "管理定时任务。支持创建、列出、暂停、恢复、删除定时任务。"
        "定时任务到期时会自动执行 prompt 并将结果发送给用户。"
    )
    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["create", "list", "pause", "resume", "delete"],
                "description": "操作类型",
            },
            "prompt": {
                "type": "string",
                "description": "定时任务的执行内容/提示词（create 时必填）",
            },
            "trigger_type": {
                "type": "string",
                "enum": ["once", "interval", "cron"],
                "description": "触发方式：once=一次性, interval=固定间隔, cron=cron表达式",
            },
            "trigger_value": {
                "type": "string",
                "description": "触发参数：once 填秒级时间戳，interval 填秒数，cron 填表达式如 '0 9 * * *'",
            },
            "task_id": {
                "type": "string",
                "description": "任务ID（pause/resume/delete 时必填）",
            },
        },
        "required": ["action"],
    }

    async def execute(self, ctx: ToolContext, **kwargs: Any) -> str:
        from paimon.state import state

        march = state.march
        if not march:
            return "三月调度服务未启动"

        action = kwargs.get("action", "")

        if action == "create":
            return await self._create(ctx, march, kwargs)
        elif action == "list":
            return await self._list(march)
        elif action == "pause":
            return await self._pause(march, kwargs.get("task_id", ""))
        elif action == "resume":
            return await self._resume(march, kwargs.get("task_id", ""))
        elif action == "delete":
            return await self._delete(march, kwargs.get("task_id", ""))
        else:
            return f"未知操作: {action}"

    async def _create(self, ctx: ToolContext, march, kwargs: dict) -> str:
        prompt = kwargs.get("prompt", "")
        if not prompt:
            return "缺少 prompt 参数"

        trigger_type = kwargs.get("trigger_type", "interval")
        trigger_str = kwargs.get("trigger_value", "")

        if trigger_type == "once":
            try:
                at = float(trigger_str) if trigger_str else time.time() + 60
            except ValueError:
                at = time.time() + 60
            trigger_value = {"at": at}
        elif trigger_type == "interval":
            try:
                seconds = int(trigger_str) if trigger_str else 3600
            except ValueError:
                seconds = 3600
            trigger_value = {"seconds": seconds}
        elif trigger_type == "cron":
            trigger_value = {"expr": trigger_str or "0 * * * *"}
        else:
            return f"未知触发类型: {trigger_type}"

        task_id = await march.create_task(
            chat_id=ctx.chat_id,
            channel_name="webui",
            prompt=prompt,
            trigger_type=trigger_type,
            trigger_value=trigger_value,
        )
        return f"定时任务已创建: {task_id} (类型={trigger_type})"

    async def _list(self, march) -> str:
        tasks = await march.list_tasks()
        if not tasks:
            return "暂无定时任务"
        lines = ["定时任务列表:"]
        for t in tasks:
            status = "启用" if t.enabled else "禁用"
            next_str = time.strftime("%m-%d %H:%M", time.localtime(t.next_run_at)) if t.next_run_at > 0 else "-"
            lines.append(f"  [{t.id}] {status} | {t.trigger_type} | 下次={next_str} | {t.task_prompt[:40]}")
        return "\n".join(lines)

    async def _pause(self, march, task_id: str) -> str:
        if not task_id:
            return "缺少 task_id"
        ok = await march.pause_task(task_id)
        return f"任务 {task_id} 已暂停" if ok else f"任务 {task_id} 不存在"

    async def _resume(self, march, task_id: str) -> str:
        if not task_id:
            return "缺少 task_id"
        ok = await march.resume_task(task_id)
        return f"任务 {task_id} 已恢复" if ok else f"任务 {task_id} 不存在"

    async def _delete(self, march, task_id: str) -> str:
        if not task_id:
            return "缺少 task_id"
        ok = await march.delete_task(task_id)
        return f"任务 {task_id} 已删除" if ok else f"任务 {task_id} 不存在"
