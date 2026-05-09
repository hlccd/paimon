"""/evolve 自进化命令——主动触发 skill 提案产生。

用法：
- `/evolve` —— 反思当前会话最近的对话/任务，凝练 skill 草案
- `/evolve <提示>` —— 用户附加提示

实现：直接调 propose_skill + review_proposal 函数链（不走 pipeline 编排）。
跟 archive hook 的 `_run_propose_review_chain` 用同一个 helper，确保两条
触发路径行为一致。

跑前会过一道派蒙 task_review 入口安全审，防止用户输入恶意被注入到 prompt。
"""
from __future__ import annotations

import time
import uuid

from loguru import logger

from paimon.state import state

from ._dispatch import CommandContext, command


_EVOLVE_HEAD = (
    "请反思当前会话最近的对话和任务，凝练**可复用**的 skill 草案。\n\n"
    "判断标准从严：单次问答、太琐碎、跟现有 skill 重叠 → 直接 SKIP 不要硬凑。"
)


@command("evolve")
async def cmd_evolve(ctx: CommandContext) -> str:
    """/evolve [提示] — 触发 propose_skill + review_proposal 链产生 skill 提案。"""
    session_mgr = state.session_mgr
    if not session_mgr:
        return "会话管理器未初始化"
    if not state.model:
        return "LLM 未就绪"
    if not state.irminsul:
        return "世界树未就绪"

    session = session_mgr.get_current(ctx.msg.channel_key)
    if not session:
        return "当前没有活跃会话——请先发条消息建会话再 /evolve"

    user_hint = ctx.args.strip() if ctx.args else ""
    recent_msgs = session.messages[-20:] if len(session.messages) > 1 else []
    recent_brief = "\n".join(
        f"[{m.get('role', '?')}] {str(m.get('content', ''))[:300]}"
        for m in recent_msgs
        if m.get("role") in ("user", "assistant") and m.get("content")
    )[:3000]

    parts = [_EVOLVE_HEAD]
    if user_hint:
        parts.append(f"\n用户附加提示：{user_hint}")
    if recent_brief:
        parts.append(f"\n## 最近会话片段（参考）\n{recent_brief}")
    context = "\n".join(parts)

    # 合成 TaskEdict（task_review + propose 链共用）
    from paimon.foundation.irminsul.task import TaskEdict
    from paimon.shades.istaroth._propose_trigger import (
        PROPOSE_TRIGGER_MARKER, _run_propose_review_chain,
    )

    now = time.time()
    syn_origin = TaskEdict(
        id=uuid.uuid4().hex,
        title=f"用户主动 /evolve{('：' + user_hint[:50]) if user_hint else ''}",
        description=f"{PROPOSE_TRIGGER_MARKER}\n{context[:500]}",
        creator="派蒙·/evolve",
        status="completed",
        session_id=session.id,
        created_at=now, updated_at=now,
    )

    # 派蒙入口安全审：防止用户输入注入或越权
    from paimon.core.safety import task_review
    try:
        approved, reason = await task_review(syn_origin, state.model, state.irminsul)
    except Exception as e:
        logger.warning("[派蒙·/evolve] task_review 异常，保守拒绝：{}", e)
        return f"安全审查异常，本次 /evolve 终止：{e}"
    if not approved:
        return f"派蒙·入口安全审拒：{reason}"

    # 立即 persist user 占位（让任务跑期间切 tab/刷新能看到自己发的命令）
    session.messages.append({"role": "user", "content": ctx.msg.text})
    await session_mgr.save_session_async(session)
    logger.info(
        "[派蒙·/evolve] 触发自进化提案 user_hint={!r} session={}",
        user_hint[:60], session.id[:8],
    )

    try:
        await _run_propose_review_chain(
            origin_task=syn_origin,
            context=context,
            trigger_reason=f"用户主动 /evolve{('：' + user_hint[:60]) if user_hint else ''}",
            irminsul=state.irminsul,
            model=state.model,
        )
    except Exception as e:
        logger.error("[派蒙·/evolve] 提案产生异常：{}", e)
        return f"自进化提案产生失败：{e}"

    # 查最新 pending 提案给用户反馈
    props = await state.irminsul.skill_proposal_list(status="pending", limit=3)
    if not props:
        return (
            "✓ 自进化判定**未产出新提案**——LLM 看完最近对话认为没有值得沉淀的 skill。\n"
            "你也可以加 `/evolve <更具体的提示>` 引导方向。"
        )

    latest = props[0]
    verdict_label = {
        "pass": "死执·通过",
        "needs_revise": "死执·要修",
        "reject": "死执·拒",
        "": "死执·待审",
    }.get(latest.review_verdict, "死执·待审")
    return (
        f"✓ 已产出新提案：**{latest.name}**（{verdict_label}）\n\n"
        f"{latest.description}\n\n"
        f"前往 `/plugins#proposals` 查看完整草案 + 同意/拒绝。"
    )
