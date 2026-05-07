"""会话内调用四影 ShadesPipeline：被 /task 命令 + 命令行入口共用。

跟 entry.py 的 enter_shades_pipeline_background 区别：这里是同步等到完成后再
返回上层（命令行/CLI 用），不分流式 vs 批次渠道。
"""
from __future__ import annotations

import asyncio

from loguru import logger

from paimon.channels.base import Channel, IncomingMessage
from paimon.session import Session
from paimon.state import state

from ._persist import _persist_shades_turn
from ._runtime import _require_runtime


async def run_shades_pipeline(
    msg: IncomingMessage,
    channel: Channel,
    session: Session,
):
    """全程同步等四影 pipeline 完成；过程中状态 generating / 完成 completed / 中断 interrupted。"""
    cfg, session_mgr, model = _require_runtime()

    logger.info("[派蒙·四影] [{}] 复杂任务: {}", session.id[:8], msg.text)

    reply = await channel.make_reply(msg)

    # 进入 generating；无论成功/失败最终必须把状态复位，避免 UI 卡 "generating"
    session.response_status = "generating"
    try:
        session_mgr.save_session(session)
    except Exception:
        pass

    result: str = ""
    pipeline_ok = True
    cancelled = False
    try:
        try:
            from paimon.shades.pipeline import ShadesPipeline
            pipeline = ShadesPipeline(
                model, state.irminsul,
                channel=channel,
                chat_id=msg.chat_id,
                authz_cache=state.authz_cache,
                reply=reply,
            )

            result = await pipeline.run(
                msg.text, session_id=session.id,
            )
        except asyncio.CancelledError:
            # 外部 cancel（如用户 /stop）：不把异常吞掉，但先把收尾做完
            cancelled = True
            pipeline_ok = False
            logger.info("[派蒙·四影] 管线被取消 session={}", session.id[:8])
            raise
        except Exception as e:
            pipeline_ok = False
            logger.error("[派蒙·四影] 管线异常: {}", e)
            result = f"[错误] 四影管线执行失败: {e}"

        # reply.send 的 I/O 错误不影响 pipeline_ok（管线可能已成功只是连接断了）
        if not cancelled:
            try:
                if result:
                    prefix = "\n\n> " if not pipeline_ok else ""
                    await reply.send(prefix + result)
                cost = model.last_chat_cost_usd
                cost_str = f"${cost:.4f}" if cost < 0.01 else f"${cost:.2f}"
                model_name = getattr(model, "last_chat_model_name", "") or "?"
                await reply.send(f"\n\n---\n~{cost_str} · 🧠 {model_name}")
            except Exception as e:
                logger.debug("[派蒙·四影] reply.send 失败（连接可能已断）: {}", e)
    finally:
        # 无论成功/异常/cancel，都要收尾 session 状态，避免 UI 卡 "generating"
        try:
            await reply.flush()
        except Exception:
            pass

        # 会话状态补录：complex 直送路径下主会话完全没过 model.chat，需要手动补 user+assistant
        # cancelled 时不强求补产物（可能不完整），但 response_status 仍要复位
        if not cancelled:
            try:
                _persist_shades_turn(session, msg.text, result, pipeline_ok)
            except Exception as e:
                logger.debug("[派蒙·四影] 会话状态补录失败: {}", e)

        if cancelled:
            session.response_status = "interrupted"
        else:
            session.response_status = "completed" if pipeline_ok else "interrupted"
        try:
            session_mgr.save_session(session)
        except Exception as e:
            logger.debug("[派蒙·四影] save_session 失败: {}", e)
