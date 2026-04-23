"""尼可 · 魔女会桥 — 天使路径失败兜底到四影

docs/aimon.md §2.1 / docs/angels/angels.md §魔女会通道：
  天使失败 → 派蒙轻量校验 → 尼可（魔女会对接人）→ 四影

本模块落地"天使失败 → 询问用户 → 转交四影"这一条兜底链路。
按项目命名惯例（四影用成员名 Jonova/Naberius/Asmoday/Istaroth），
魔女会在此由对接人尼可（Nicole）代表。
"""
from __future__ import annotations

import asyncio
from typing import Literal

from loguru import logger

from paimon.channels.base import Channel, IncomingMessage
from paimon.session import Session


AngelFailureStage = Literal["tool_timeout", "total_timeout", "exec_error"]


class AngelFailure(Exception):
    """天使路径执行失败，需要魔女会兜底转交。"""

    def __init__(self, reason: str, stage: AngelFailureStage = "exec_error"):
        super().__init__(reason)
        self.reason = reason
        self.stage = stage


async def escalate_to_shades(
    msg: IncomingMessage,
    channel: Channel,
    session: Session,
    *,
    reason: str,
) -> None:
    """天使失败兜底：询问用户是否转交四影，同意则调四影管线。"""
    from paimon.core.authz.keywords import classify_reply
    from paimon.state import state

    logger.warning(
        "[天使·魔女会] [{}] 触发兜底 reason={}",
        session.id[:8], reason,
    )

    prompt = (
        f"天使处理未完成（原因：{reason}）。\n"
        f"要转交四影深度处理吗？回复「同意 / 放行」即转交，回复「拒绝 / 算了」即终止。"
    )

    try:
        reply = await channel.ask_user(msg.chat_id, prompt, timeout=30.0)
    except NotImplementedError:
        logger.info("[天使·魔女会] 频道 {} 未支持 ask_user，放弃转交", channel.name)
        await msg.reply(
            f"\n\n> [天使·魔女会] 天使处理未完成（原因：{reason}）。"
            "本频道不支持交互询问，任务已终止，请在 WebUI 中重试。\n"
        )
        return
    except asyncio.TimeoutError:
        logger.info("[天使·魔女会] 用户 30s 无答复，取消转交")
        await msg.reply(
            f"\n\n> [天使·魔女会] 天使处理未完成（原因：{reason}）。"
            "30 秒无答复，已取消转交。\n"
        )
        return

    kind = classify_reply(reply)
    logger.info(
        "[天使·魔女会] 用户答复='{}' 分类={}",
        reply[:40], kind,
    )

    if kind not in ("allow", "perm_allow"):
        await msg.reply("\n\n> [天使·魔女会] 已取消转交，任务终止。\n")
        return

    # 派蒙"再次轻量校验"（docs/angels/angels.md §协作流转 · 流转前校验）
    # MVP：仅记日志占位，后续可按需补充关键词/格式级拦截
    logger.info("[派蒙·魔女会] 轻量校验通过 → 转交四影")

    await msg.reply("\n\n> [天使·魔女会] 正在转交四影深度处理...\n")

    # 覆盖 handle_chat finally 落盘的 "interrupted" 状态，并同步落盘让 UI 反映当前走四影
    session.response_status = "generating"
    if state.session_mgr is not None:
        try:
            state.session_mgr.save_session(session)
        except Exception as e:
            logger.debug("[派蒙·魔女会] session 状态落盘失败: {}", e)

    from paimon.core.chat import run_shades_pipeline

    await run_shades_pipeline(
        msg, channel, session,
        escalation_reason=reason,
    )
