"""任务相关指令：/tasks 列定时任务 + /task 强走四影管线。"""
from __future__ import annotations

from loguru import logger

from paimon.channels.base import IncomingMessage
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


@command("task")
async def cmd_task(ctx: CommandContext) -> str:
    """/task <描述> — 强制走四影管线处理复杂任务（绕过意图分类）。"""
    if not ctx.args:
        return "用法: /task <任务描述>\n强制走四影管线处理复杂任务"

    session_mgr = state.session_mgr
    if not session_mgr:
        return "会话管理器未初始化"

    session = session_mgr.get_current(ctx.msg.channel_key)
    if not session:
        session = session_mgr.create()
        session_mgr.switch(ctx.msg.channel_key, session.id)

    # 四影管线耗时长，不能 await 阻塞 SSE；复用 chat.enter_shades_pipeline_background
    # _reply 必须透传：pipeline 要用 make_reply(task_msg) 拿 reply 推 notice（docs/interaction.md）
    task_msg = IncomingMessage(
        channel_name=ctx.msg.channel_name,
        chat_id=ctx.msg.chat_id,
        text=ctx.args,
        _reply=ctx.msg._reply,
    )
    # 入口立即 persist user 占位：让任务跑期间切 tab/刷新能看到自己发的 /task 指令。
    # 外层 on_channel_message:155 的 _persist_turn(msg.text, final) 走 case 2 补 assistant。
    # 不经 _persist_turn 抽象层直接操作 session —— 保证 append + save 一定生效且
    # 日志里能直接看到"入口 persist user"凭证（否则任务跑几分钟后才知道到底有没有生效）。
    session.messages.append({"role": "user", "content": ctx.msg.text})
    await session_mgr.save_session_async(session)
    logger.info(
        "[派蒙·四影·入口 persist] task_user={!r} (session={} msgs={})",
        ctx.msg.text[:60], session.id[:8], len(session.messages),
    )
    from paimon.core.chat import enter_shades_pipeline_background
    return await enter_shades_pipeline_background(
        task_msg, ctx.channel, session,
        persist_user_text=ctx.msg.text,
    )


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

    blocks.append("> 标准命令：`/help`")
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
