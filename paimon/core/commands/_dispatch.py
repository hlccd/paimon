"""指令调度核心：CommandContext / 注册表 / dispatch_command / Skill 兜底。

`command` 装饰器把 cmd_xxx 注册到 _commands；dispatch_command 按 name 取出执行；
未匹配且 skill_registry 里有同名 skill 时降级走天使路径调起。
"""
from __future__ import annotations

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
    """单次 /xxx 触发的上下文：原始 msg + channel + 参数串。"""
    msg: IncomingMessage
    channel: "Channel"
    args: str


CommandHandler = Callable[[CommandContext], Awaitable[str]]

_commands: dict[str, CommandHandler] = {}


def command(name: str):
    """注册装饰器：@command("foo") 把 fn 写入 _commands['foo']。"""
    def decorator(fn: CommandHandler) -> CommandHandler:
        _commands[name] = fn
        return fn
    return decorator


async def dispatch_command(msg: IncomingMessage, channel: "Channel") -> str | None:
    """渠道入口分发：识别 /cmd → 调 handler → 错误兜底；找不到指令时尝试 Skill 名。"""
    text = msg.text.strip()
    if not text.startswith("/"):
        return None

    parts = text.split(maxsplit=1)
    raw = parts[0][1:].split("@")[0].lower()
    cmd_name = raw
    extra_args = ""

    # 容错：用户在 QQ/聊天框常忘记命令和参数之间的空格
    # 例：/task-index1 → cmd=task-index, args="1"；/task-list2 → cmd=task-list, args="2"
    # 触发条件：raw 不是已注册命令 且 尾部含数字 且 切出的前缀是已注册命令
    if cmd_name not in _commands:
        m = re.match(r"^([a-zA-Z][a-zA-Z_-]*?)(\d.*)$", raw)
        if m and m.group(1) in _commands:
            cmd_name = m.group(1)
            extra_args = m.group(2)

    args = extra_args
    if len(parts) > 1:
        args = (args + " " + parts[1]).strip() if args else parts[1].strip()

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


async def _invoke_skill(skill_name: str, args: str, msg: IncomingMessage, channel: "Channel"):
    """/<skill_name> 兜底：当用户输入了 Skill 名当指令时调天使路径。"""
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
