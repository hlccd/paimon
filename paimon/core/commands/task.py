"""任务相关指令：/tasks 列定时任务 + /skills 列可用 skill。"""
from __future__ import annotations

from paimon.state import state

from ._dispatch import CommandContext, command


@command("tasks")
async def cmd_tasks(ctx: CommandContext) -> str:
    """/tasks — 列出三月调度的全部任务（启用/触发器/下次时间/描述）。"""
    march = state.march
    if not march:
        return "三月调度服务未启动"
    tasks = await march.list_tasks()
    if not tasks:
        return "暂无定时任务"
    import time as _time
    from paimon.foundation import task_types as _tt
    lines = ["定时任务列表:"]
    for t in tasks:
        status = "启用" if t.enabled else "禁用"
        next_str = _time.strftime(
            "%m-%d %H:%M", _time.localtime(t.next_run_at),
        ) if t.next_run_at > 0 else "-"
        err = f" [错误: {t.last_error[:30]}]" if t.last_error else ""
        # 方案 D：内部类型优先按 registry 渲染来源 + 描述
        if t.task_type and t.task_type != "user":
            meta = _tt.get(t.task_type)
            label = meta.display_label if meta else f"❓{t.task_type}"
            desc = ""
            if meta and meta.description_builder:
                try:
                    desc = await meta.description_builder(
                        t.source_entity_id, state.irminsul,
                    )
                except Exception:
                    desc = t.source_entity_id or ""
            else:
                desc = t.source_entity_id or ""
            display = f"[{label}] {desc}"[:60]
        else:
            display = t.task_prompt[:40]
        lines.append(
            f"  {t.id} | {status} | {t.trigger_type} | 下次: {next_str} | {display}{err}"
        )
    return "\n".join(lines)


@command("skills")
async def cmd_skills(ctx: CommandContext) -> str:
    """/skills — 列出可调 Skill（精简 markdown）。

    分两段：
    1. 直调（user-invocable=true）—— `/<name>` 直接调用
    2. 自动识别 —— 凡有 triggers 的 skill（含 user-invocable=true 的 + 仅 trigger-invoke 的）

    orchestrator-only / io-only（user-invocable=false 且无 triggers）的 skill 不展示。
    """
    skill_registry = state.skill_registry
    if not skill_registry or not skill_registry.skills:
        return "暂无可用 Skill"

    direct: list = []
    triggered: list = []
    for s in skill_registry.list_all():
        if s.user_invocable:
            direct.append(s)
        if s.triggers and s.triggers.strip():
            # 自动识别段含所有有 triggers 的（即便 user_invocable=true 也列，用作"无需斜杠"提示）
            triggered.append(s)

    blocks: list[str] = []

    if direct:
        lines = ["**直调**"]
        for s in direct:
            lines.append(f"- `/{s.name}` — {_short_desc(s.description)}")
        blocks.append("\n".join(lines))

    if triggered:
        lines = ["**自动识别（无需斜杠）**"]
        for s in triggered:
            kws = [t.strip() for t in s.triggers.split(",") if t.strip()][:3]
            kws_str = " / ".join(f"`{k}`" for k in kws)
            lines.append(f"- {kws_str} → `/{s.name}`")
        blocks.append("\n".join(lines))

    return "\n\n".join(blocks)


def _short_desc(desc: str, max_chars: int = 40) -> str:
    """精简 skill description：按多种分隔符切首段，取**位置最早**的分隔符。

    SKILL.md 作者写的 description 常见模式：
    - "短描述。详细说明…"   → 截 "短描述"
    - "短描述（细节）…"     → 截 "短描述"
    - "短描述 - 详细说明"   → 截 "短描述"
    都没匹配则字符截。
    """
    if not desc:
        return ""
    desc = desc.strip()
    candidates = []
    for sep in ("。", " - ", " — ", "（", ". "):
        idx = desc.find(sep)
        if 0 < idx <= max_chars:
            candidates.append(idx)
    if candidates:
        return desc[:min(candidates)]
    return desc[:max_chars] + ("…" if len(desc) > max_chars else "")
