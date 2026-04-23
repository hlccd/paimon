"""
派蒙指令系统

统一指令注册与分发，所有频道共用。
"""
from __future__ import annotations

import json
import re
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


# 敏感检测：复用 paimon.core.safety，保持向后兼容的旧私有别名
from paimon.core.safety import SENSITIVE_PATTERNS as _SENSITIVE_PATTERNS  # noqa: F401
from paimon.core.safety import detect_sensitive as _detect_sensitive  # noqa: F401


@command("remember")
async def cmd_remember(ctx: CommandContext) -> str:
    """/remember <内容> — L1 记忆显式入口。
    LLM 自动判别类型（user/feedback/project/reference）；失败降级到 user。
    """
    content = ctx.args.strip()
    if not content:
        return "用法: /remember <要记住的内容>"
    # 防御：单条 /remember 内容上限 2000 字符（符合 memory 域设计）
    _MAX_REMEMBER_CHARS = 2000
    if len(content) > _MAX_REMEMBER_CHARS:
        return f"内容过长（{len(content)} 字），单条记忆上限 {_MAX_REMEMBER_CHARS} 字；请拆分后分别 /remember"
    # 敏感串拒绝：跨会话 memory 会每次注入 system prompt，不应包含密钥/隐私
    hit = _detect_sensitive(content)
    if hit:
        logger.warning("[派蒙·记忆] /remember 命中敏感串 (pattern={}) 已拒绝", hit)
        return (
            f"⚠️ 检测到疑似敏感信息（pattern: {hit}），已拒绝写入。\n"
            "L1 记忆会注入每次对话的系统提示；请勿在此存储密钥/密码/身份证/银行卡等隐私信息。"
        )
    if not state.irminsul or not state.model:
        return "世界树 / 模型未就绪"

    mem_type, title, subject = await _classify_memory(content, state.model)
    if mem_type is None:
        # LLM 失败降级：默认 user / default / 前 30 字标题（并清理控制字符）
        mem_type, subject = "user", "default"
        safe = content.replace("\n", " ").replace("\r", " ").replace("\t", " ")
        title = safe[:30]

    # subject 防 injection：只保留字母数字/中文/_-；可能含路径穿越的降级 default
    subject = _sanitize_subject(subject)

    try:
        mem_id = await state.irminsul.memory_write(
            mem_type=mem_type, subject=subject, title=title,
            body=content,
            source=f"cmd /remember @ {ctx.msg.channel_name}",
            actor="派蒙",
        )
    except ValueError as e:
        logger.warning("[派蒙·记忆] /remember 参数无效: {}", e)
        return f"⚠️ 内容或参数无效: {e}"
    except Exception as e:
        logger.error("[派蒙·记忆] /remember 写入失败: {}", e)
        return f"记忆写入失败: {e}"

    return f"已记住 [{mem_type}/{subject}] {title} (id={mem_id[:8]})"


_SUBJECT_SAFE_RE = re.compile(r"^[\w\u4e00-\u9fff\-]+$")


def _sanitize_subject(subject: str) -> str:
    """subject 必须是简单标识符（字母/数字/下划线/中文/短横）。
    含路径字符 / 空格 / 特殊字符的一律降级到 'default'，避免 resolve_safe 抛 + 文件系统问题。
    """
    s = (subject or "").strip() or "default"
    if ".." in s or "/" in s or "\\" in s:
        return "default"
    if not _SUBJECT_SAFE_RE.match(s):
        return "default"
    return s[:80]


_CLASSIFY_MEMORY_PROMPT = """\
你是记忆分类器。用户用 /remember 命令告诉派蒙一段要记住的内容。
请把内容归入以下类型之一：
- user: 用户画像 / 偏好 / 角色（"我主要用 Go"、"偏好简洁"）
- feedback: 对派蒙行为的纠正 / 规范（"不要给总结"、"用中文"）
- project: 当前项目的持久事实（"这个项目在 /xxx"、"DB 是 PostgreSQL"）
- reference: 外部资源指针（"bugs 在 Linear INGEST"、"面板 grafana.xx"）

只输出 JSON 对象，严格格式：
{"type": "user|feedback|project|reference", "title": "短标题(<=20字)", "subject": "主题词(user/feedback 用 default, project 用项目名, reference 用简短关键词)"}

不要输出任何其他文字、不要 markdown 代码块。
"""


async def _classify_memory(content: str, model) -> tuple:
    """LLM 分类 /remember 内容。返回 (type, title, subject)，全部为 None 表示失败。"""
    messages = [
        {"role": "system", "content": _CLASSIFY_MEMORY_PROMPT},
        {"role": "user", "content": f"内容：\n{content}"},
    ]
    try:
        raw, usage = await model._stream_text(messages)
        await model._record_primogem(
            "", "remember", usage, purpose="记忆分类",
        )
    except Exception as e:
        logger.warning("[派蒙·记忆] /remember 分类 LLM 失败: {}", e)
        return None, None, None

    text = raw.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if len(lines) >= 2 and lines[-1].strip() == "```":
            text = "\n".join(lines[1:-1]).strip()

    try:
        obj = json.loads(text)
    except Exception as e:
        logger.warning("[派蒙·记忆] /remember JSON 解析失败: {} 原始={}", e, text[:200])
        return None, None, None

    # 必须是 dict（防御 null/list/数字/字符串等 JSON 合法但结构错误的情况）
    if not isinstance(obj, dict):
        logger.warning("[派蒙·记忆] /remember 输出非对象: {}", type(obj).__name__)
        return None, None, None

    mem_type = obj.get("type", "")
    title = (obj.get("title") or "").strip()
    subject = (obj.get("subject") or "").strip() or "default"
    if mem_type not in ("user", "feedback", "project", "reference") or not title:
        return None, None, None
    return mem_type, title[:80], subject[:80]


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
        "  /remember <内容> - 记住一段跨会话信息（偏好/规范/项目事实）\n"
        "  /help - 显示此帮助"
    )
