"""
派蒙指令系统

统一指令注册与分发，所有频道共用。
"""
from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING

from loguru import logger

from paimon.state import state

if TYPE_CHECKING:
    from paimon.channels.base import Channel, IncomingMessage


@dataclass
class CommandContext:
    msg: IncomingMessage
    channel: Channel
    args: str


CommandHandler = Callable[[CommandContext], Awaitable[str]]

_commands: dict[str, CommandHandler] = {}


def command(name: str):
    def decorator(fn: CommandHandler) -> CommandHandler:
        _commands[name] = fn
        return fn
    return decorator


async def dispatch_command(msg: IncomingMessage, channel: Channel) -> str | None:
    text = msg.text.strip()
    if not text.startswith("/"):
        return None

    parts = text.split(maxsplit=1)
    cmd_name = parts[0][1:].split("@")[0].lower()
    args = parts[1].strip() if len(parts) > 1 else ""

    handler = _commands.get(cmd_name)
    if handler is not None:
        ctx = CommandContext(msg=msg, channel=channel, args=args)
        logger.info("[派蒙·指令] /{} (频道={})", cmd_name, msg.channel_name)
        try:
            return await handler(ctx)
        except Exception as e:
            logger.error("[派蒙·指令] /{} 执行失败: {}", cmd_name, e)
            return f"指令执行失败: {e}"

    skill_registry = state.skill_registry
    if skill_registry and skill_registry.exists(cmd_name):
        await _invoke_skill(cmd_name, args, msg, channel)
        return ""

    return None


async def _invoke_skill(skill_name: str, args: str, msg: IncomingMessage, channel: Channel):
    from paimon.core.chat import run_session_chat

    logger.info("[天使·调度] /{} args={}", skill_name, args)

    session_mgr = state.session_mgr
    if not session_mgr:
        await msg.reply("会话管理器未初始化")
        return

    session = session_mgr.get_current(msg.channel_key)
    if not session:
        session = session_mgr.create()
        session_mgr.switch(msg.channel_key, session.id)

    skill_msg = IncomingMessage(
        channel_name=msg.channel_name,
        chat_id=msg.chat_id,
        text=args or f"请执行 {skill_name} skill",
        _reply=msg._reply,
    )

    await run_session_chat(skill_msg, channel, session, skill_name=skill_name)


# --------------- 指令实现 ---------------


@command("new")
async def cmd_new(ctx: CommandContext) -> str:
    session_mgr = state.session_mgr
    if not session_mgr:
        return "会话管理器未初始化"
    new_session = session_mgr.create()
    session_mgr.switch(ctx.msg.channel_key, new_session.id)
    return f"已创建新会话: {new_session.name} ({new_session.id})"


@command("sessions")
async def cmd_sessions(ctx: CommandContext) -> str:
    session_mgr = state.session_mgr
    if not session_mgr:
        return "会话管理器未初始化"
    if not session_mgr.sessions:
        return "当前没有任何会话"

    current = session_mgr.get_current(ctx.msg.channel_key)
    sorted_sessions = sorted(
        session_mgr.sessions.values(),
        key=lambda s: s.updated_at,
        reverse=True,
    )

    lines = ["会话列表:"]
    for s in sorted_sessions:
        marker = " <- 当前" if current and current.id == s.id else ""
        msg_count = sum(1 for m in s.messages if m.get("role") in ("user", "assistant"))
        lines.append(f"  {s.name} ({s.id}){marker} [{msg_count}条消息]")
    return "\n".join(lines)


@command("switch")
async def cmd_switch(ctx: CommandContext) -> str:
    session_mgr = state.session_mgr
    if not session_mgr:
        return "会话管理器未初始化"

    target = ctx.args.strip()
    if not target:
        return "用法: /switch <会话ID或名称前缀>"

    session = session_mgr.sessions.get(target)

    if not session:
        matches = [
            s for s in session_mgr.sessions.values()
            if s.id.startswith(target) or s.name.startswith(target)
        ]
        if len(matches) == 1:
            session = matches[0]
        elif len(matches) > 1:
            hints = ", ".join(f"{s.name}({s.id})" for s in matches[:5])
            return f"匹配到多个会话: {hints}"

    if not session:
        return f"未找到会话: {target}"

    session_mgr.switch(ctx.msg.channel_key, session.id)
    return f"已切换到会话: {session.name} ({session.id})"


@command("stop")
async def cmd_stop(ctx: CommandContext) -> str:
    from paimon.core.chat import stop_session_task

    session_mgr = state.session_mgr
    if not session_mgr:
        return "会话管理器未初始化"
    current = session_mgr.get_current(ctx.msg.channel_key)
    if not current:
        return "当前没有活跃会话"
    stopped = await stop_session_task(current.id)
    return "已停止当前回复" if stopped else "当前没有正在生成的回复"


@command("clear")
async def cmd_clear(ctx: CommandContext) -> str:
    from paimon.core.chat import stop_session_task

    session_mgr = state.session_mgr
    if not session_mgr:
        return "会话管理器未初始化"
    current = session_mgr.get_current(ctx.msg.channel_key)
    if not current:
        return "当前没有活跃会话"
    await stop_session_task(current.id)
    current.messages.clear()
    current.session_memory.clear()
    current.last_context_tokens = 0
    current.last_context_ratio = 0.0
    current.compressed_rounds = 0
    session_mgr.save_session(current)
    return f"已清空会话: {current.name}"


@command("rename")
async def cmd_rename(ctx: CommandContext) -> str:
    session_mgr = state.session_mgr
    if not session_mgr:
        return "会话管理器未初始化"
    new_name = ctx.args.strip()
    if not new_name:
        return "用法: /rename <新名称>"
    current = session_mgr.get_current(ctx.msg.channel_key)
    if not current:
        return "当前没有活跃会话"
    old_name = current.name
    current.name = new_name
    session_mgr.save_session(current)
    return f"会话已重命名: {old_name} -> {new_name}"


@command("delete")
async def cmd_delete(ctx: CommandContext) -> str:
    from paimon.core.chat import stop_session_task

    session_mgr = state.session_mgr
    if not session_mgr:
        return "会话管理器未初始化"

    target = ctx.args.strip()
    if target:
        session = session_mgr.sessions.get(target)
        if not session:
            for s in session_mgr.sessions.values():
                if s.id.startswith(target) or s.name == target:
                    session = s
                    break
        if not session:
            return f"未找到会话: {target}"
    else:
        session = session_mgr.get_current(ctx.msg.channel_key)
        if not session:
            return "当前没有活跃会话，请指定要删除的会话ID"

    await stop_session_task(session.id)
    name = session.name
    session_mgr.delete(session.id)
    return f"已删除会话: {name}"


def _format_stats(stats: dict, label: str) -> list[str]:
    total_tok = stats["total_input_tokens"] + stats["total_output_tokens"]
    lines = [
        f"{label}:",
        f"  调用: {stats['count']}次",
        f"  输入: {stats['total_input_tokens']:,} token",
        f"  输出: {stats['total_output_tokens']:,} token",
    ]
    cw = stats.get("total_cache_creation_tokens", 0)
    cr = stats.get("total_cache_read_tokens", 0)
    if cw or cr:
        lines.append(f"  缓存写入: {cw:,} / 缓存命中: {cr:,}")
    lines.append(f"  总token: {total_tok:,}")
    lines.append(f"  估算花费: ~${stats['total_cost_usd']:.4f}")
    if stats.get("by_component"):
        for comp, data in stats["by_component"].items():
            lines.append(f"    {comp}: {data['count']}次 ~${data['cost_usd']:.4f}")
    return lines


@command("stat")
async def cmd_stat(ctx: CommandContext) -> str:
    primogem = state.primogem
    if not primogem:
        return "原石模块未启用"

    session_mgr = state.session_mgr
    current = session_mgr.get_current(ctx.msg.channel_key) if session_mgr else None

    g = await primogem.get_global_stats()
    lines = _format_stats(g, "原石统计 (全局)")

    purpose_stats = await primogem.get_purpose_stats()
    if purpose_stats:
        lines.append("  按用途:")
        for purpose, data in purpose_stats.items():
            lines.append(f"    {purpose}: {data['count']}次 ~${data['cost_usd']:.4f}")

    if current:
        s = await primogem.get_session_stats(current.id)
        if s["count"] > 0:
            lines.append("")
            lines.extend(_format_stats(s, f"当前会话 ({current.name})"))

    return "\n".join(lines)


@command("tasks")
async def cmd_tasks(ctx: CommandContext) -> str:
    march = state.march
    if not march:
        return "三月调度服务未启动"
    tasks = await march.list_tasks()
    if not tasks:
        return "暂无定时任务"
    import time as _time
    lines = ["定时任务列表:"]
    for t in tasks:
        status = "启用" if t.enabled else "禁用"
        next_str = _time.strftime("%m-%d %H:%M", _time.localtime(t.next_run_at)) if t.next_run_at > 0 else "-"
        err = f" [错误: {t.last_error[:30]}]" if t.last_error else ""
        lines.append(f"  {t.id} | {status} | {t.trigger_type} | 下次: {next_str} | {t.task_prompt[:40]}{err}")
    return "\n".join(lines)


@command("task")
async def cmd_task(ctx: CommandContext) -> str:
    if not ctx.args:
        return "用法: /task <任务描述>\n强制走四影管线处理复杂任务"

    from paimon.core.chat import run_shades_pipeline

    session_mgr = state.session_mgr
    if not session_mgr:
        return "会话管理器未初始化"

    session = session_mgr.get_current(ctx.msg.channel_key)
    if not session:
        session = session_mgr.create()
        session_mgr.switch(ctx.msg.channel_key, session.id)

    task_msg = IncomingMessage(
        channel_name=ctx.msg.channel_name,
        chat_id=ctx.msg.chat_id,
        text=ctx.args,
        _reply=ctx.msg._reply,
    )
    await run_shades_pipeline(task_msg, ctx.channel, session)
    return ""


@command("skills")
async def cmd_skills(ctx: CommandContext) -> str:
    skill_registry = state.skill_registry
    if not skill_registry or not skill_registry.skills:
        return "暂无可用 Skill"
    lines = ["可用 Skills:"]
    for s in skill_registry.list_all():
        lines.append(f"  /{s.name} - {s.description}")
    return "\n".join(lines)


@command("help")
async def cmd_help(ctx: CommandContext) -> str:
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
        "  /help - 显示此帮助"
    )
