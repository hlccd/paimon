"""派蒙指令系统子包入口 —— 必须导入所有 cmd_* 子模块触发 @command 装饰器注册。

子模块：
- _dispatch.py     —— CommandContext / @command 装饰器 / dispatch_command 路由
- session.py       —— /new /sessions /switch /stop /clear /rename /delete
- stat.py          —— /stat 原石统计
- task.py          —— /tasks /task /skills
- agents.py        —— /agents 多视角讨论（晨星召集天使）
- memory.py        —— /remember
- subscribe.py     —— /subscribe /subs；导出 create_subscription（外部 API）
- dividend.py      —— /dividend；导出 toggle_dividend_cron（外部 API）
- task_workspace.py —— /task-merge /task-discard /task-summary
- task_index.py    —— /task-list /task-index
- selfcheck.py     —— /selfcheck
- help.py          —— /help

外部 import 路径不变：from paimon.core.commands import dispatch_command / create_subscription / toggle_dividend_cron / command。
"""
from __future__ import annotations

from ._dispatch import CommandContext, command, dispatch_command
from .dividend import toggle_dividend_cron
from .subscribe import create_subscription

# 触发各 cmd 模块顶层 @command(...) 注册（必须 import 一次）
from . import (  # noqa: F401
    agents,
    dividend,
    help,
    memory,
    selfcheck,
    session,
    stat,
    subscribe,
    task,
    task_index,
    task_workspace,
)

__all__ = [
    "CommandContext",
    "command",
    "create_subscription",
    "dispatch_command",
    "toggle_dividend_cron",
]
