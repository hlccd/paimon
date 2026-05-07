"""/help — 派蒙指令总入口（精简 markdown 输出）。

设计：
- 标准命令静态写死（命令稳定）
- skill 部分（自动触发段）从 skill_registry 动态读
- 输出纯 markdown：粗体主题 + 反引号命令 + 列表项 — 短描述
- 短描述精简到一行可读，长描述截到首个句号
"""
from __future__ import annotations

from ._dispatch import CommandContext, command


# 主题分组：每个主题 = (name, items)
# items 元素 = (cmd_with_args, summary)；summary 空字符串表示纯罗列模式
_TOPICS: list[tuple[str, list[tuple[str, str]]]] = [
    ("会话", [
        ("/new", ""),
        ("/sessions", ""),
        ("/switch <ID>", ""),
        ("/clear", ""),
        ("/rename <名>", ""),
        ("/delete [ID]", ""),
        ("/stop", ""),
    ]),
    ("任务", [
        ("/task <描述>", "复杂任务（四影）"),
        ("/tasks", "定时任务列表"),
        ("/task-list", "深度任务历史"),
        ("/task-index [N]", "任务详情"),
        ("/task-merge <id>", "合并任务产物"),
        ("/task-discard <id>", "丢弃任务工作区"),
        ("/task-summary [id]", "任务总结"),
    ]),
    ("订阅记忆", [
        ("/subscribe <关键词>", "话题订阅"),
        ("/subs", "订阅管理"),
        ("/remember <内容>", "跨会话记忆"),
    ]),
    ("理财", [
        ("/dividend", "红利股追踪"),
    ]),
    ("系统", [
        ("/selfcheck", ""),
        ("/stat", ""),
        ("/skills", ""),
        ("/help", ""),
    ]),
]


def _render_topic(name: str, items: list[tuple[str, str]]) -> list[str]:
    """单主题渲染：
    - 全部无 summary → 同行罗列（`**name**` + 反引号命令列表）
    - 有 summary → markdown 列表（`**name**` 一行 + `- \`cmd\` — summary` 多行）
    """
    plain = [(c, s) for c, s in items if not s]
    detailed = [(c, s) for c, s in items if s]

    if plain and not detailed:
        cmds = " ".join(f"`{c}`" for c, _ in plain)
        return [f"**{name}** {cmds}"]

    out = [f"**{name}**"]
    for cmd, summ in detailed:
        out.append(f"- `{cmd}` — {summ}")
    if plain:
        cmds = " ".join(f"`{c}`" for c, _ in plain)
        out.append(f"- {cmds}")
    return out


@command("help")
async def cmd_help(ctx: CommandContext) -> str:
    """/help — 列出全部可用指令的简要说明。"""
    from paimon.state import state

    blocks: list[str] = []
    for name, items in _TOPICS:
        blocks.append("\n".join(_render_topic(name, items)))

    # 自动触发提示（从 skill_registry 动态拼一句话）
    skill_registry = state.skill_registry
    auto_skills: list[str] = []
    if skill_registry and skill_registry.skills:
        for s in skill_registry.list_all():
            if s.triggers and s.triggers.strip():
                auto_skills.append(f"`/{s.name}`")

    tail = "> 子动作详情：直接调命令（如 `/dividend`）　|　Skill 列表：`/skills`"
    if auto_skills:
        tail += f"\n> 部分 Skill 自动识别（无需斜杠），见 `/skills`"

    return "\n\n".join(blocks) + "\n\n" + tail
