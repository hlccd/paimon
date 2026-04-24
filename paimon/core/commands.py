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

# IncomingMessage 需运行时可用（cmd_task / _invoke_skill 里 new 实例），不能只放 TYPE_CHECKING
from paimon.channels.base import IncomingMessage

if TYPE_CHECKING:
    from paimon.channels.base import Channel


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
    # 过滤订阅 / 红利股专用任务：归专属面板管理（/subs list、/dividend、/wealth）
    tasks = [
        t for t in tasks
        if not t.task_prompt.startswith("[FEED_COLLECT] ")
        and not t.task_prompt.startswith("[DIVIDEND_SCAN] ")
    ]
    if not tasks:
        return "暂无定时任务（订阅推送见 /subs list；红利股追踪见 /dividend）"
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

    # 四影管线耗时长，不能 await 阻塞 SSE；复用 chat.enter_shades_pipeline_background
    task_msg = IncomingMessage(
        channel_name=ctx.msg.channel_name,
        chat_id=ctx.msg.chat_id,
        text=ctx.args,
        _reply=None,
    )
    from paimon.core.chat import enter_shades_pipeline_background
    return await enter_shades_pipeline_background(task_msg, ctx.channel, session)


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


# --------------- 话题订阅（风神）---------------

_DEFAULT_SUBSCRIBE_CRON = "0 10 * * *"   # 每天 10 点
_MAX_SUBSCRIBE_QUERY_LEN = 200
_VALID_ENGINES = {"", "baidu", "bing"}


def _parse_subscribe_args(args: str) -> tuple[str, str, str] | str:
    """解析 /subscribe 参数。返回 (query, cron, engine) 或错误字符串。

    支持格式：
      "<query>"                         → cron=默认, engine=默认
      "<query> | <cron>"                → engine=默认
      "<query> | <cron> | <engine>"     → 全指定
    """
    if not args or not args.strip():
        return (
            "用法: /subscribe <关键词> [| <cron表达式>] [| <engine>]\n"
            "例: /subscribe Claude 4.7\n"
            "    /subscribe 小米 SU7 | 0 10 * * *\n"
            "    /subscribe 大模型 | */6 * * * * | bing\n"
            f"默认 cron: {_DEFAULT_SUBSCRIBE_CRON} (每日 10 点)\n"
            "engine 可选: baidu / bing / 留空=双引擎"
        )

    parts = [p.strip() for p in args.split("|")]
    query = parts[0].strip()
    cron = parts[1].strip() if len(parts) > 1 and parts[1].strip() else _DEFAULT_SUBSCRIBE_CRON
    engine = parts[2].strip().lower() if len(parts) > 2 else ""

    if not query:
        return "关键词不能为空"
    if len(query) > _MAX_SUBSCRIBE_QUERY_LEN:
        return f"关键词过长（{len(query)} 字），上限 {_MAX_SUBSCRIBE_QUERY_LEN}"
    if engine not in _VALID_ENGINES:
        return f"engine 必须是 baidu / bing / 留空，收到: {engine}"

    try:
        from croniter import croniter
        croniter(cron)
    except Exception as e:
        return f"cron 表达式无效 '{cron}': {e}"

    return query, cron, engine


async def create_subscription(
    *, query: str, cron: str, engine: str,
    channel_name: str, chat_id: str,
    supports_push: bool = True,
) -> tuple[bool, str]:
    """订阅创建的核心逻辑（命令 / WebUI 共用）。返回 (ok, message)。

    成功时 message 是"订阅已创建 #xxx ..."的用户回显文本；失败时是错误描述。
    """
    if not state.irminsul or not state.march:
        return False, "世界树 / 三月未就绪"

    query = (query or "").strip()
    cron = (cron or "").strip() or _DEFAULT_SUBSCRIBE_CRON
    engine = (engine or "").strip().lower()

    if not query:
        return False, "关键词不能为空"
    if len(query) > _MAX_SUBSCRIBE_QUERY_LEN:
        return False, f"关键词过长（{len(query)} 字），上限 {_MAX_SUBSCRIBE_QUERY_LEN}"
    if engine not in _VALID_ENGINES:
        return False, f"engine 必须是 baidu / bing / 留空，收到: {engine}"
    try:
        from croniter import croniter
        croniter(cron)
    except Exception as e:
        return False, f"cron 表达式无效 '{cron}': {e}"

    if not supports_push:
        return False, (
            f"当前频道 {channel_name} 不支持主动推送，无法订阅。\n"
            "订阅推送依赖推送能力，可改用 WebUI 或 Telegram 频道订阅。"
        )

    from paimon.foundation.irminsul.subscription import Subscription

    sub = Subscription(
        query=query,
        channel_name=channel_name,
        chat_id=chat_id,
        schedule_cron=cron,
        engine=engine,
    )
    sub_id = await state.irminsul.subscription_create(sub, actor="派蒙")

    try:
        task_id = await state.march.create_task(
            chat_id=chat_id,
            channel_name=channel_name,
            prompt=f"[FEED_COLLECT] {sub_id}",
            trigger_type="cron",
            trigger_value={"expr": cron},
        )
    except Exception as e:
        await state.irminsul.subscription_delete(sub_id, actor="派蒙")
        return False, f"定时任务创建失败，订阅已回滚: {e}"

    await state.irminsul.subscription_update(
        sub_id, actor="派蒙", linked_task_id=task_id,
    )

    task = await state.irminsul.schedule_get(task_id)
    import time as _time
    next_str = (
        _time.strftime("%Y-%m-%d %H:%M", _time.localtime(task.next_run_at))
        if task and task.next_run_at > 0 else "-"
    )
    engine_label = engine or "双引擎"
    message = (
        f"订阅已创建 #{sub_id[:8]}\n"
        f"  关键词: {query}\n"
        f"  周期: {cron}\n"
        f"  引擎: {engine_label}\n"
        f"  下次运行: {next_str}\n"
        f"可用 /subs list 查看全部，/subs rm {sub_id[:8]} 删除"
    )
    return True, message


@command("subscribe")
async def cmd_subscribe(ctx: CommandContext) -> str:
    """创建话题订阅。

    /subscribe <关键词> [| <cron>] [| <engine>]

    风神会按 cron 定时调 web-search 采集，过滤已见 URL 后交 LLM 写日报，
    推送给当前频道。
    """
    parsed = _parse_subscribe_args(ctx.args)
    if isinstance(parsed, str):
        return parsed
    query, cron, engine = parsed

    ok, msg = await create_subscription(
        query=query, cron=cron, engine=engine,
        channel_name=ctx.msg.channel_name,
        chat_id=ctx.msg.chat_id,
        supports_push=getattr(ctx.channel, "supports_push", True),
    )
    return msg


async def _resolve_subscription(prefix: str):
    """按 id 前缀解析订阅，要求精确 12 字 id 或唯一前缀。"""
    if not state.irminsul:
        return None, "世界树未就绪"
    prefix = prefix.strip()
    if not prefix:
        return None, "缺少订阅 ID"
    sub = await state.irminsul.subscription_get(prefix)
    if sub:
        return sub, ""
    # 前缀匹配
    all_subs = await state.irminsul.subscription_list()
    matches = [s for s in all_subs if s.id.startswith(prefix)]
    if len(matches) == 1:
        return matches[0], ""
    if len(matches) > 1:
        return None, f"前缀 '{prefix}' 匹配到 {len(matches)} 个订阅，请输入更长 ID"
    return None, f"未找到订阅: {prefix}"


@command("subs")
async def cmd_subs(ctx: CommandContext) -> str:
    """订阅管理：
      /subs list                 列全部订阅
      /subs rm <id>              删订阅（级联清 feed_items + scheduled_tasks）
      /subs on <id>              启用
      /subs off <id>             停用
      /subs run <id>             手动触发一次采集（立即执行，便于验证）
    """
    if not state.irminsul:
        return "世界树未就绪"

    args = ctx.args.strip()
    if not args:
        return cmd_subs.__doc__ or "用法: /subs list | rm <id> | on <id> | off <id> | run <id>"

    parts = args.split(maxsplit=1)
    action = parts[0].lower()
    rest = parts[1].strip() if len(parts) > 1 else ""

    if action == "list":
        subs = await state.irminsul.subscription_list()
        if not subs:
            return "暂无订阅。用 /subscribe <关键词> 创建"
        import time as _time
        lines = ["订阅列表:"]
        for s in subs:
            status = "启用" if s.enabled else "停用"
            last_run = (
                _time.strftime("%m-%d %H:%M", _time.localtime(s.last_run_at))
                if s.last_run_at > 0 else "-"
            )
            count = await state.irminsul.feed_items_count(sub_id=s.id)
            err = f" [错: {s.last_error[:30]}]" if s.last_error else ""
            lines.append(
                f"  #{s.id[:8]} | {status} | {s.query[:30]} | "
                f"{s.schedule_cron} | 累计 {count} 条 | 上次 {last_run}{err}"
            )
        return "\n".join(lines)

    if action == "rm":
        sub, err = await _resolve_subscription(rest)
        if not sub:
            return err
        # 同步删 scheduled_task
        if sub.linked_task_id and state.march:
            try:
                await state.march.delete_task(sub.linked_task_id)
            except Exception as e:
                logger.warning("[派蒙·订阅] 删定时任务失败 {}: {}", sub.linked_task_id, e)
        ok = await state.irminsul.subscription_delete(sub.id, actor="派蒙")
        return f"已删除订阅 #{sub.id[:8]} ({sub.query})" if ok else "删除失败"

    if action in ("on", "off"):
        sub, err = await _resolve_subscription(rest)
        if not sub:
            return err
        enable = action == "on"
        await state.irminsul.subscription_update(
            sub.id, actor="派蒙", enabled=enable,
        )
        # 同步 scheduled_task 启停
        if sub.linked_task_id and state.march:
            try:
                if enable:
                    await state.march.resume_task(sub.linked_task_id)
                else:
                    await state.march.pause_task(sub.linked_task_id)
            except Exception as e:
                logger.warning("[派蒙·订阅] 同步定时任务启停失败: {}", e)
        return f"订阅 #{sub.id[:8]} 已{'启用' if enable else '停用'}"

    if action == "run":
        sub, err = await _resolve_subscription(rest)
        if not sub:
            return err
        if not state.venti:
            return "风神未初始化"
        # 后台异步跑，不阻塞指令返回
        import asyncio as _asyncio
        _asyncio.create_task(state.venti.collect_subscription(
            sub.id, irminsul=state.irminsul, model=state.model, march=state.march,
        ))
        return f"已手动触发采集 #{sub.id[:8]} ({sub.query})，稍后查看推送"

    return f"未知子命令: {action}。可用: list / rm / on / off / run"


# --------------- 红利股追踪（岩神）---------------

# 默认 cron：工作日 19:00 收盘后 daily 更新；月 1 日 21:00 全扫刷 watchlist
_DIVIDEND_CRON_DAILY = "0 19 * * 1-5"
_DIVIDEND_CRON_FULL = "0 21 1 * *"


async def toggle_dividend_cron(
    *, enable: bool, channel_name: str, chat_id: str,
) -> tuple[bool, str]:
    """helper：开启/关闭红利股 daily + full 两个 cron。幂等。"""
    if not state.irminsul or not state.march:
        return False, "世界树 / 三月未就绪"

    # 找已有 [DIVIDEND_SCAN] 任务
    tasks = await state.march.list_tasks()
    existing = {
        t.task_prompt.split(" ", 1)[1]: t
        for t in tasks
        if t.task_prompt.startswith("[DIVIDEND_SCAN] ")
    }

    if not enable:
        # 删除所有已有 dividend cron
        removed = 0
        for mode_key, t in existing.items():
            try:
                if await state.march.delete_task(t.id):
                    removed += 1
            except Exception as e:
                logger.warning("[岩神·cron] 删任务 {} 失败: {}", t.id, e)
        return True, f"已关闭红利股定时任务（删 {removed} 条）"

    # enable：确保两个 cron 都在；已存在但被三月退避禁用的要重启
    created: list[str] = []
    resumed: list[str] = []
    for mode, cron in [("daily", _DIVIDEND_CRON_DAILY), ("full", _DIVIDEND_CRON_FULL)]:
        if mode in existing:
            t = existing[mode]
            if not t.enabled:
                try:
                    if await state.march.resume_task(t.id):
                        resumed.append(mode)
                except Exception as e:
                    logger.warning("[岩神·cron] 恢复 {} 失败: {}", mode, e)
            continue
        try:
            await state.march.create_task(
                chat_id=chat_id,
                channel_name=channel_name,
                prompt=f"[DIVIDEND_SCAN] {mode}",
                trigger_type="cron",
                trigger_value={"expr": cron},
            )
            created.append(f"{mode} ({cron})")
        except Exception as e:
            return False, f"{mode} cron 创建失败: {e}"

    if not created and not resumed:
        return True, "红利股定时任务已在运行（daily + full 都已启用）"
    parts = []
    if created:
        parts.append(f"新建: {'、'.join(created)}")
    if resumed:
        parts.append(f"恢复: {'、'.join(resumed)}")
    return True, "已启用红利股定时任务（" + "；".join(parts) + "）"


@command("dividend")
async def cmd_dividend(ctx: CommandContext) -> str:
    """红利股追踪（岩神）。

    /dividend on         启用定时：daily(工作日 19:00) + full(月 1 日 21:00)
    /dividend off        停用全部定时
    /dividend run-full   立即全市场扫描（~15 分钟）
    /dividend run-daily  立即 watchlist 日更（~1 分钟）
    /dividend rescore    秒级重评分（仅用缓存）
    /dividend top [N]    查看当前 top（默认 20）
    /dividend recommended 查看推荐选股（watchlist）
    /dividend changes [N] 近 N 天变化（默认 7）
    /dividend history <code> [days] 单股历史评分
    """
    if not state.zhongli or not state.irminsul:
        return "岩神未就绪"

    args = ctx.args.strip()
    if not args:
        return cmd_dividend.__doc__ or "用法: /dividend on|off|run-*|top|changes|history"

    parts = args.split(maxsplit=1)
    action = parts[0].lower()
    rest = parts[1].strip() if len(parts) > 1 else ""

    if action in ("on", "off"):
        ok, msg = await toggle_dividend_cron(
            enable=(action == "on"),
            channel_name=ctx.msg.channel_name,
            chat_id=ctx.msg.chat_id,
        )
        return msg

    if action in ("run-full", "run-daily", "rescore"):
        mode_map = {"run-full": "full", "run-daily": "daily", "rescore": "rescore"}
        mode = mode_map[action]
        if not state.march:
            return "三月未就绪"
        if state.zhongli.is_scanning():
            return "已有扫描在进行，请等待完成后再触发"
        import asyncio as _asyncio
        _asyncio.create_task(state.zhongli.collect_dividend(
            mode=mode,
            irminsul=state.irminsul,
            march=state.march,
            chat_id=ctx.msg.chat_id,
            channel_name=ctx.msg.channel_name,
        ))
        hint = {
            "full": "约 15-20 分钟",
            "daily": "约 30-60 秒",
            "rescore": "几秒内完成",
        }[mode]
        return f"已触发红利股 {mode} 扫描（{hint}），完成后推送报告"

    if action == "top":
        n = 20
        if rest:
            try:
                n = max(1, min(int(rest), 100))
            except ValueError:
                pass
        rows = await state.zhongli.get_top(n, state.irminsul)
        if not rows:
            return "暂无评分数据，请先跑 /dividend run-daily"
        return state.zhongli._format_ranking(rows)

    if action == "recommended":
        rows = await state.zhongli.get_recommended(state.irminsul)
        if not rows:
            return "暂无推荐数据，请先跑 /dividend run-full"
        return state.zhongli._format_recommended_snapshots(rows)

    if action == "changes":
        days = 7
        if rest:
            try:
                days = max(1, min(int(rest), 90))
            except ValueError:
                pass
        chs = await state.zhongli.get_changes(days, state.irminsul)
        if not chs:
            return f"最近 {days} 天无显著变化"
        return state.zhongli._format_changes_list(chs)

    if action == "history":
        if not rest:
            return "用法: /dividend history <6位股票代码> [days]"
        bits = rest.split()
        code = bits[0]
        days = 90
        if len(bits) > 1:
            try:
                days = max(1, min(int(bits[1]), 365))
            except ValueError:
                pass
        import re as _re
        if not _re.fullmatch(r"\d{6}", code):
            return "股票代码必须是 6 位数字"
        history = await state.zhongli.get_stock_history(code, days, state.irminsul)
        return state.zhongli._format_history(code, history)

    return (
        f"未知子命令: {action}\n"
        "可用: on / off / run-full / run-daily / rescore / top / recommended / changes / history"
    )


# --------------- 任务工作区 merge / discard ---------------


def _resolve_task_id_prefix(prefix: str) -> str | None:
    """按前缀找 workspace（.paimon/tasks/ 下的子目录名）。多个匹配返回 None。"""
    from paimon.foundation.task_workspace import _workspace_root
    prefix = prefix.strip()
    if not prefix:
        return None
    root = _workspace_root()
    if not root.exists():
        return None
    matches = [d.name for d in root.iterdir() if d.is_dir() and d.name.startswith(prefix)]
    return matches[0] if len(matches) == 1 else None


@command("task-merge")
async def cmd_task_merge(ctx: CommandContext) -> str:
    """/task-merge <task_id前缀> [--overwrite]
    把 .paimon/tasks/{id}/code/ 下的文件合并到当前工作目录。"""
    from paimon.foundation.task_workspace import merge_to_cwd, get_workspace_path

    args = ctx.args.strip().split()
    if not args:
        return "用法: /task-merge <task_id前缀> [--overwrite]"
    overwrite = "--overwrite" in args
    args = [a for a in args if not a.startswith("--")]
    if not args:
        return "缺少 task_id 前缀"

    task_id = _resolve_task_id_prefix(args[0])
    if not task_id:
        return f"未找到 task 工作区匹配 '{args[0]}'（或多个匹配）"

    ws = get_workspace_path(task_id)
    if not ws.exists():
        return f"工作区不存在: {ws}"

    result = merge_to_cwd(task_id, overwrite=overwrite)
    parts = [f"merge task #{task_id[:8]}:"]
    if result["copied"]:
        parts.append(f"  ✅ 合并 {len(result['copied'])} 个文件")
        for f in result["copied"][:10]:
            parts.append(f"     + {f}")
        if len(result["copied"]) > 10:
            parts.append(f"     ... 共 {len(result['copied'])} 个")
    if result["skipped"]:
        parts.append(f"  ⏸️  跳过 {len(result['skipped'])} 个（目标已存在且内容不同；加 --overwrite 覆盖）")
        for f in result["skipped"][:5]:
            parts.append(f"     - {f}")
    if result["errors"]:
        parts.append(f"  ❌ 错误 {len(result['errors'])} 条:")
        for e in result["errors"][:5]:
            parts.append(f"     ! {e}")
    if not any((result["copied"], result["skipped"], result["errors"])):
        parts.append("  (无变化)")
    return "\n".join(parts)


@command("task-discard")
async def cmd_task_discard(ctx: CommandContext) -> str:
    """/task-discard <task_id前缀> — 丢弃工作区（删除 .paimon/tasks/{id}/ 目录）"""
    from paimon.foundation.task_workspace import cleanup_workspace, get_workspace_path

    prefix = ctx.args.strip()
    if not prefix:
        return "用法: /task-discard <task_id前缀>"

    task_id = _resolve_task_id_prefix(prefix)
    if not task_id:
        return f"未找到 task 工作区匹配 '{prefix}'（或多个匹配）"

    removed = cleanup_workspace(task_id)
    return f"已丢弃 task #{task_id[:8]}" if removed else "工作区未找到"


@command("task-summary")
async def cmd_task_summary(ctx: CommandContext) -> str:
    """/task-summary <task_id前缀> — 查看任务 summary.md"""
    from paimon.foundation.task_workspace import get_workspace_path

    prefix = ctx.args.strip()
    if not prefix:
        # 列所有 workspace
        from paimon.foundation.task_workspace import _workspace_root
        root = _workspace_root()
        if not root.exists():
            return "暂无任务工作区"
        dirs = sorted((d.name for d in root.iterdir() if d.is_dir()))
        if not dirs:
            return "暂无任务工作区"
        return "任务工作区:\n" + "\n".join(f"  {d}" for d in dirs[:20])

    task_id = _resolve_task_id_prefix(prefix)
    if not task_id:
        return f"未找到 task 工作区匹配 '{prefix}'"
    summary = get_workspace_path(task_id) / "summary.md"
    if not summary.exists():
        return f"summary.md 不存在（任务可能未完成归档）: {summary}"
    return summary.read_text(encoding="utf-8")[:5000]


@command("selfcheck")
async def cmd_selfcheck(ctx: CommandContext) -> str:
    """三月·自检入口。/selfcheck [--deep] [--help]

    默认跑 Quick（秒级组件探针）；`--deep` 启动 Deep（调 check skill 跑项目体检，
    异步后台执行，结果见 WebUI `/selfcheck` 面板 + 📨 推送）。
    """
    svc = state.selfcheck
    if not svc:
        return "自检服务未启用（config.selfcheck_enabled=false 或未初始化）"

    args = (ctx.args or "").strip()
    # 按 token 拆而不是 startswith：避免 "/selfcheck deep foo" 的 foo 被当 Quick
    tokens = args.split(maxsplit=1)
    first = tokens[0] if tokens else ""
    rest = tokens[1].strip() if len(tokens) > 1 else ""

    if first in ("--help", "-h", "help"):
        return (
            "/selfcheck 用法:\n"
            "  /selfcheck                  - Quick 自检（秒级，组件状态表）\n"
            "  /selfcheck --help           - 本帮助\n"
            "\n"
            "面板: WebUI → /selfcheck（Quick 历史 + 详情）\n"
            "\n"
            "注：Deep 自检暂缓——当前 mimo-v2-omni 对 check skill 的\n"
            "N+M+K 多轮循环执行不充分，跑半截就停。换 Claude Opus\n"
            "级模型验证过再启用（见 docs/todo.md）。底层代码保留，\n"
            "config.selfcheck_deep_hidden=False 重启即可恢复手动入口。"
        )

    if first in ("--deep", "deep"):
        # Deep 暂缓开关：docs/todo.md §三月·自检·Deep 暂缓
        # 当前 mimo-v2-omni 模型执行不充分；底层 _run_deep_inner 代码保留
        # 未来换 Claude Opus 级模型验证后可设 selfcheck_deep_hidden=False 恢复
        from paimon.config import config as _cfg
        if getattr(_cfg, "selfcheck_deep_hidden", True):
            return (
                "Deep 自检当前暂缓（LLM 执行不充分）。\n"
                "Quick 自检可用（直接跑 /selfcheck）。\n"
                "恢复 Deep 步骤：\n"
                "  1. 给 deep pool 配 Claude Opus 级模型\n"
                "  2. .env 设 SELFCHECK_DEEP_HIDDEN=false\n"
                "  3. 重启 paimon"
            )
        # Deep：非阻塞启动，立即返回
        result = await svc.run_deep(
            args=rest or None, triggered_by="user",
        )
        if not result["started"]:
            if result["reason"] == "already_running":
                return (
                    "已有 Deep 自检在进行中，请等待完成后再试\n"
                    "（见 WebUI /selfcheck 面板 Deep Tab）"
                )
            return f"Deep 启动失败: {result['reason']}"
        return (
            f"🔬 Deep 自检已启动 run={result['run_id']}\n"
            f"后台跑 check skill（可能 3~15 分钟），完成后推📨 推送。\n"
            f"面板实时查看: /selfcheck"
        )

    # 默认 Quick
    run = await svc.run_quick(triggered_by="user")
    if run.status != "completed":
        return f"Quick 自检异常: {run.error or run.status}"

    summary = run.quick_summary or {}
    overall = summary.get("overall", "?")
    warnings = summary.get("warnings", [])
    components = summary.get("components", [])

    icon = {"ok": "✅", "degraded": "⚠️", "critical": "🚨"}.get(overall, "❓")
    lines = [
        f"{icon} Quick 自检完成 run={run.id[:8]} · 耗时 {run.duration_seconds*1000:.0f}ms",
        f"整体状态: {overall}",
        "",
        "组件状态:",
    ]
    for c in components:
        cicon = {"ok": "✓", "degraded": "△", "critical": "✗"}.get(
            c.get("status", "?"), "?",
        )
        lines.append(
            f"  {cicon} {c.get('name', '?'):<16} "
            f"[{c.get('status', '?')}] {c.get('latency_ms', 0):.1f}ms"
        )
    if warnings:
        lines.append("")
        lines.append("⚠️ 告警:")
        for w in warnings:
            lines.append(f"  - {w}")
    lines.append("")
    lines.append("详情/历史: WebUI /selfcheck")
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
