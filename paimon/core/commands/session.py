"""会话管理指令：new / sessions / switch / stop / clear / rename / delete。"""
from __future__ import annotations

from paimon.state import state

from ._dispatch import CommandContext, command


@command("session")
async def cmd_session(ctx: CommandContext) -> str:
    """/session — 会话领域命令清单（纯 help 入口；具体命令各自调）。"""
    return (
        "- `/new` 新建会话\n"
        "- `/sessions` 列出会话\n"
        "- `/switch <ID>` 切换会话\n"
        "- `/rename <名>` 重命名会话\n"
        "- `/delete [ID]` 删除会话\n"
        "- `/clear` 清空当前会话\n"
        "- `/stop` 停止生成"
    )


@command("new")
async def cmd_new(ctx: CommandContext) -> str:
    """新建会话并切到它（当前 channel）。"""
    session_mgr = state.session_mgr
    if not session_mgr:
        return "会话管理器未初始化"
    new_session = session_mgr.create()
    session_mgr.switch(ctx.msg.channel_key, new_session.id)
    return f"已创建新会话: {new_session.name} ({new_session.id})"


@command("sessions")
async def cmd_sessions(ctx: CommandContext) -> str:
    """列出所有会话，标记当前并显示消息数。"""
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
    """按 ID/名称（前缀）切换当前会话。多匹配时报错让用户输入更长。"""
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
    """中止当前会话正在生成的回复。"""
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
    """清空当前会话所有消息 + session_memory；先 stop 再清。"""
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
    """重命名当前会话。"""
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
    """删除会话；省略参数则删当前。先 stop 再删。"""
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
