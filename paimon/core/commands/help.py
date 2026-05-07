"""/help — 派蒙指令总入口。

设计原则：
- 单页：所有标准命令按主题分组列出，不发明 `/help <主题>` 这种二级抽象层
- 子动作详情走命令本身：`/dividend` `/subs` `/selfcheck` 等无参数已自带 docstring help
- skill 走 /skills 独立维度查看，不混进 /help
- 自动触发（trigger）从 skill_registry 动态读，不硬编码
"""
from __future__ import annotations

from ._dispatch import CommandContext, command


# 主题分组：每行 (主题名, 命令列表带可选行内说明)
# 命令格式：(cmd_name, args_hint, summary)；args_hint / summary 可为空字符串
_TOPICS: list[tuple[str, list[tuple[str, str, str]]]] = [
    ("会话", [
        ("new", "", ""),
        ("sessions", "", ""),
        ("switch", "<ID/名称>", ""),
        ("clear", "", ""),
        ("rename", "<新名称>", ""),
        ("delete", "[ID/名称]", ""),
        ("stop", "", ""),
    ]),
    ("任务", [
        ("task", "<描述>", "强制走四影处理复杂任务"),
        ("tasks", "", "查看定时任务"),
        ("task-list", "", "列最近 7 天深度任务"),
        ("task-index", "[N]", "查看任务详情（无参=最近一条）"),
        ("task-merge", "<id前缀>", "合并写代码任务产物到当前工作目录"),
        ("task-discard", "<id前缀>", "丢弃任务工作区"),
        ("task-summary", "[id前缀]", "查看任务产物总结"),
    ]),
    ("订阅 / 记忆", [
        ("subscribe", "<关键词> [| <cron>] [| <engine>]", "订阅话题定时推送"),
        ("subs", "", "订阅管理 (list/rm/on/off/run)"),
        ("remember", "<内容>", "跨会话记忆（偏好/规范/项目事实）"),
    ]),
    ("理财", [
        ("dividend", "", "红利股追踪 · 含 9 子动作"),
    ]),
    ("系统", [
        ("selfcheck", "", "三月组件自检（Quick）"),
        ("stat", "", "token 用量统计"),
        ("skills", "", "所有可直接调用的 Skill"),
        ("help", "", "本帮助"),
    ]),
]


def _render_topic(name: str, cmds: list[tuple[str, str, str]]) -> list[str]:
    """主题渲染：
    - 全部无 summary → 单行罗列（如「会话」主题）
    - 有 summary 的 → 各占一行，head 与 summary 间至少 2 空格（短 head 填到 32 列对齐）
    """
    lines = [f"[{name}]"]
    plain = [c for c in cmds if not c[2]]
    detailed = [c for c in cmds if c[2]]

    if plain and not detailed:
        # 全是无说明的，单行罗列
        parts = [f"/{c}{' ' + h if h else ''}" for c, h, _ in plain]
        lines.append("  " + "  ".join(parts))
    else:
        # 有说明的命令各占一行
        for cmd, hint, summ in detailed:
            head = f"/{cmd}"
            if hint:
                head += f" {hint}"
            # 对齐：head < 32 列时填空格到 32；超出时至少 2 空格分隔
            gap = max(2, 32 - len(head))
            lines.append(f"  {head}{' ' * gap}{summ}")
        # 无说明的命令拼接到本节末尾（单行）
        if plain:
            tail_parts = [f"/{c}{' ' + h if h else ''}" for c, h, _ in plain]
            lines.append("  " + "  ".join(tail_parts))
    return lines


@command("help")
async def cmd_help(ctx: CommandContext) -> str:
    """/help — 列出全部可用指令的简要说明。"""
    from paimon.state import state

    out: list[str] = ["派蒙指令 /help", ""]

    for topic_name, cmds in _TOPICS:
        out.extend(_render_topic(topic_name, cmds))
        out.append("")

    out.append("子动作详情：直接调命令不带参数即可，例 /dividend / /subs / /selfcheck")
    out.append("")
    out.append("可调 Skill（用户直调 + 自动识别）：/skills")

    # 自动触发段：列所有有 triggers 的 skill —— 学习入口，让用户知道部分 skill
    # 无需敲斜杠也能用（如发 b 站链接自动解析）。和 /skills 内的 triggers 信息有重复，
    # 但 /help 是总入口、/skills 是细节，重复曝光反而帮用户记住能力
    skill_registry = state.skill_registry
    if skill_registry and skill_registry.skills:
        trigger_lines: list[str] = []
        for s in skill_registry.list_all():
            if s.triggers and s.triggers.strip():
                kws = [t.strip() for t in s.triggers.split(",") if t.strip()][:3]
                if kws:
                    trigger_lines.append(f"  发 {' / '.join(kws)} → /{s.name}")
        if trigger_lines:
            out.append("")
            out.append("自动触发（不用敲斜杠）：")
            out.extend(trigger_lines)

    return "\n".join(out)
