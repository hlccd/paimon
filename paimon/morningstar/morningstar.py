"""/agents 主入口：流式 reply + merge 主 session。

设计：
- 不建 ephemeral session（讨论 history 本来就在 council.run_council 内 list 里跑，
  从未污染派蒙的 session.messages —— 跟 skill 调用模式不同，无需 ephemeral 兜底）
- 流式：每个天使发言完毕通过 on_speak 推 reply，用户实时看到讨论进展
- merge：跑完只把「user 议题 + 综合结论」两条带 meta=skip_llm,kind=agents append 主 session
  （UI 历史可见 / 下次主对话 LLM filter 掉）
"""
from __future__ import annotations

from loguru import logger

from paimon.channels.base import Channel, IncomingMessage
from paimon.session import Session
from paimon.state import state

from .council import CouncilResult, run_council


async def run_agents(
    topic: str,
    msg: IncomingMessage,
    channel: Channel,
    main_session: Session,
) -> CouncilResult:
    """跑 /agents 多视角讨论：流式输出每个发言 + 综合结论 → merge 主 session。"""
    if not state.model:
        raise RuntimeError("神之心未就绪")

    reply = await channel.make_reply(msg)
    try:
        await reply.notice("🌅 晨星召集天使中…", kind="milestone")
    except Exception:
        pass

    async def _on_speak(role_key: str, role_name: str, content: str):
        text = f"\n\n**[{role_name}]**\n{content}\n"
        try:
            await reply.send(text)
            # QQ 等 batch 渠道需要 flush 才推到前端；webui SSE flush 无副作用
            # 不 flush 时 QQ 会 buffer 整轮讨论攒到末尾一次发，可能超 4500 字符上限
            await reply.flush()
        except Exception as e:
            logger.warning("[晨星] stream 发言失败 ({}): {}", role_name, e)

    result = await run_council(
        topic, state.model,
        on_speak=_on_speak,
        session_id=main_session.id,
    )

    # 综合结论
    final_block = (
        f"\n\n---\n\n## 📋 综合结论\n\n{result.final}\n\n"
        f"_（{len(result.history)} 轮发言 / {result.llm_calls} LLM / 收敛 {result.converge_reason}）_"
    )
    try:
        await reply.send(final_block)
        await reply.flush()
    except Exception as e:
        logger.warning("[晨星] stream 综合失败: {}", e)

    # merge 主 session 只 append assistant 配对（user 占位由 cmd_agents 入口已落）
    # 带 meta=skip_llm，UI 可见 / 下次 LLM 看不见
    # 含完整发言 history + 综合结论 —— 用户切 session 再回来仍能看到全部讨论过程
    # （reply.send 推的内容只在当时 SSE 通道有效，session.messages 才是持久化历史）
    history_md = "\n\n".join(
        f"**[{h['role_name']}]**\n{h['content']}"
        for h in result.history
    )
    meta = {"skip_llm": True, "kind": "agents"}
    main_session.messages.append({
        "role": "assistant",
        "content": (
            f"召集天使：{', '.join(result.members)}\n\n"
            + (history_md + "\n\n---\n\n" if history_md else "")
            + f"## 📋 综合结论\n\n{result.final}\n\n"
            + f"_（{len(result.history)} 轮发言 / {result.llm_calls} LLM / 收敛 {result.converge_reason}）_"
        ),
        "meta": meta,
    })
    try:
        if state.session_mgr:
            await state.session_mgr.save_session_async(main_session)
    except Exception as e:
        logger.warning("[晨星] merge 主 session 落盘失败: {}", e)

    return result
