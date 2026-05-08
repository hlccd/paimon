"""/evolve 自进化命令——主动触发 skill 提案产生。

用法：
- `/evolve` —— 让 AI 反思**当前会话最近的对话/任务**凝练 skill 草案
- `/evolve <提示>` —— 用户给附加提示（如"重点看本周做的笔记类任务"）

实现：拼一个特殊 task description 走四影管线（plan → propose_skill → review_proposal）。
LLM 在 plan 阶段会编排 propose_skill + review_proposal 节点；
若没值得做的 skill，propose_skill 输出 SKIP，review_proposal 短路 pass。

不强制频率：用户主动调，跟 cron / archive hook（todo）正交。
"""
from __future__ import annotations

from loguru import logger

from paimon.channels.base import IncomingMessage
from paimon.state import state

from ._dispatch import CommandContext, command


_EVOLVE_PROMPT_HEAD = (
    "请反思当前会话最近的对话和任务，凝练**可复用**的 skill 草案落自进化提案队列。"
    "判断标准从严：单次问答、太琐碎、跟现有 skill 重叠 → 输出 SKIP 不要硬凑。"
)


@command("evolve")
async def cmd_evolve(ctx: CommandContext) -> str:
    """/evolve [提示] — 触发自进化提案产生（走四影 propose_skill + review_proposal）。"""
    session_mgr = state.session_mgr
    if not session_mgr:
        return "会话管理器未初始化"

    session = session_mgr.get_current(ctx.msg.channel_key)
    if not session:
        return "当前没有活跃会话——请先发条消息建会话再 /evolve"

    # 拼任务描述：固定头 + 用户附加 + 最近会话片段（让 LLM 看上下文判断）
    user_hint = ctx.args.strip() if ctx.args else ""
    recent_msgs = session.messages[-20:] if len(session.messages) > 1 else []
    recent_brief = "\n".join(
        f"[{m.get('role', '?')}] {str(m.get('content', ''))[:300]}"
        for m in recent_msgs
        if m.get("role") in ("user", "assistant") and m.get("content")
    )[:3000]

    task_desc_parts = [_EVOLVE_PROMPT_HEAD]
    if user_hint:
        task_desc_parts.append(f"\n用户附加提示：{user_hint}")
    if recent_brief:
        task_desc_parts.append(f"\n## 最近会话片段（参考）\n{recent_brief}")
    task_desc = "\n".join(task_desc_parts)

    task_msg = IncomingMessage(
        channel_name=ctx.msg.channel_name,
        chat_id=ctx.msg.chat_id,
        text=task_desc,
        _reply=ctx.msg._reply,
    )

    session.messages.append({"role": "user", "content": ctx.msg.text})
    await session_mgr.save_session_async(session)
    logger.info(
        "[派蒙·/evolve] 触发自进化提案 user_hint={!r} session={} msgs={}",
        user_hint[:60], session.id[:8], len(session.messages),
    )
    from paimon.core.chat import enter_shades_pipeline_background
    return await enter_shades_pipeline_background(
        task_msg, ctx.channel, session,
        persist_user_text=ctx.msg.text,
    )
