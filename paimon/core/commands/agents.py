"""/agents 命令 — 多视角讨论入口（晨星召集 3-5 个天使讨论议题）。"""
from __future__ import annotations

from loguru import logger

from paimon.state import state

from ._dispatch import SKILL_HANDLED_SENTINEL, CommandContext, command


_MERGE_META = {"skip_llm": True, "kind": "agents"}


@command("agents")
async def cmd_agents(ctx: CommandContext) -> str:
    """/agents <议题> — 多视角讨论；无参时返领域 help。"""
    topic = ctx.args.strip()
    if not topic:
        return (
            "- `/agents <议题>` 召集多视角讨论 ← **带议题才开启**\n"
            "\n"
            "适用：决策 / 选型权衡 / 需求澄清 / 复盘对抗 / 方案评估\n"
            "例：`/agents 用 sqlite 还是 postgres`\n"
            "    `/agents 应不应该上 RBAC`"
        )

    if not state.session_mgr:
        return "会话管理器未就绪"
    if not state.model:
        return "神之心未就绪"

    main_session = state.session_mgr.get_current(ctx.msg.channel_key)
    if not main_session:
        main_session = state.session_mgr.create()
        state.session_mgr.switch(ctx.msg.channel_key, main_session.id)

    # 入口立即 append user 占位 + save：让讨论跑期间用户切 tab / 重连能看到自己发的指令
    # 跟 entry.py:119 /task 路径一致；morningstar 末尾只 append assistant 配对
    # 带 meta=skip_llm 让 LLM 下次主对话看不到这条；UI 可见
    main_session.messages.append({
        "role": "user", "content": ctx.msg.text, "meta": _MERGE_META,
    })
    await state.session_mgr.save_session_async(main_session)
    logger.info(
        "[晨星·入口 persist] /agents user={!r} (session={} msgs={})",
        ctx.msg.text[:60], main_session.id[:8], len(main_session.messages),
    )

    from paimon.morningstar import run_agents
    try:
        await run_agents(
            topic=topic, msg=ctx.msg, channel=ctx.channel,
            main_session=main_session,
        )
    except Exception as e:
        logger.error("[晨星] 讨论异常: {}", e)
        err_msg = f"晨星讨论异常：{type(e).__name__}: {e}"
        # 异常时也补 assistant 配对，避免 session.messages 留 dangling user
        # 同样带 meta 不污染 LLM；reply 走 channel 让用户看到错误
        try:
            await ctx.msg.reply(err_msg)
        except Exception:
            pass
        main_session.messages.append({
            "role": "assistant", "content": err_msg, "meta": _MERGE_META,
        })
        try:
            await state.session_mgr.save_session_async(main_session)
        except Exception as save_e:
            logger.warning("[晨星] 异常路径 save 失败: {}", save_e)
        return SKILL_HANDLED_SENTINEL

    # 已自行 stream + merge 主 session，让 entry 跳过 reply / persist 避免重复
    return SKILL_HANDLED_SENTINEL
