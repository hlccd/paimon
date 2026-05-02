"""/help — 派蒙指令快速速查表。"""
from __future__ import annotations

from ._dispatch import CommandContext, command


@command("help")
async def cmd_help(ctx: CommandContext) -> str:
    """/help — 列出全部可用指令的简要说明。"""
    return (
        "派蒙指令帮助:\n"
        "  /new - 创建新会话\n"
        "  /sessions - 查看所有会话\n"
        "  /switch <ID/名称> - 切换会话\n"
        "  /stop - 停止当前回复\n"
        "  /clear - 清空当前会话\n"
        "  /rename <新名称> - 重命名当前会话\n"
        "  /delete [ID/名称] - 删除会话\n"
        "  /stat - 查看token用量统计\n"
        "  /skills - 查看可用 Skill\n"
        "  /tasks - 查看定时任务\n"
        "  /task <描述> - 强制走四影处理复杂任务\n"
        "  /task-list - 列最近 7 天的深度任务（带 1-基序号，10 分钟内有效）\n"
        "  /task-index [N] - 查看任务详情（无参=最近一条；自动按需重建索引）\n"
        "  /remember <内容> - 记住一段跨会话信息（偏好/规范/项目事实）\n"
        "  /subscribe <关键词> [| <cron>] [| <engine>] - 订阅话题定时推送\n"
        "  /subs list|rm|on|off|run <id> - 订阅管理\n"
        "  /dividend on|off|run-full|run-daily|rescore|top|recommended|changes|history - 红利股追踪\n"
        "  /selfcheck - 三月 Quick 自检（秒级组件探针；Deep 暂缓）\n"
        "  /task-merge <id前缀> [--overwrite] - 合并写代码任务产物到当前工作目录\n"
        "  /task-discard <id前缀> - 丢弃写代码任务工作区\n"
        "  /task-summary [id前缀] - 查看任务产物总结（无参数列所有）\n"
        "  /help - 显示此帮助"
    )
