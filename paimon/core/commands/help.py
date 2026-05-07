"""/help — 派蒙指令总入口（二级目录）。

设计：
- /help 只列各领域的二级入口（每个领域有自己的展开命令）
- 领域内具体命令通过对应 /xxx-help 命令查看
- /skills 是 skill 领域入口（含直调 skill + 自动识别）
- /dividend / /subs 等带子动作的命令无参时自带 docstring help
"""
from __future__ import annotations

from ._dispatch import CommandContext, command


_TOP_LEVEL: list[tuple[str, str]] = [
    ("/session", "会话管理"),
    ("/task", "任务"),
    ("/agents", "多视角讨论"),
    ("/subscribe", "订阅 / 记忆"),
    ("/dividend", "红利股追踪"),
    ("/skills", "Skill 列表（含自动识别）"),
    ("/selfcheck", "组件自检"),
    ("/stat", "token 用量"),
    ("/help", "本帮助"),
]


@command("help")
async def cmd_help(ctx: CommandContext) -> str:
    """/help — 列出各领域二级入口；具体命令进对应 /xxx-help 看。"""
    return "\n".join(f"- `{cmd}` {summ}" for cmd, summ in _TOP_LEVEL)
