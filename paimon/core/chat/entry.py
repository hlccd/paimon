"""入站消息总入口：权限询问 / 入口过滤 / 命令分流 / 意图分发。

`on_channel_message` 是所有渠道（QQ/Web/TG）消息的第一站；按 chat / skill 二选一分流。
"""
from __future__ import annotations

from loguru import logger

from paimon.channels.base import Channel, IncomingMessage
from paimon.state import state

from ._persist import _persist_turn
from ._runtime import _require_runtime
from .session import run_session_chat


async def on_channel_message(msg: IncomingMessage, channel: Channel):
    """渠道消息总入口：权限答复消化 / 入口过滤 / 命令分流 / 意图分类（chat / skill）。"""
    # 0) 若有挂起的权限询问，本条消息当作答复消化，不走正常 chat 流
    channel_key = msg.channel_key
    pending = state.pending_asks.get(channel_key)
    if pending is not None and not pending.done():
        pending.set_result(msg.text)
        logger.info("[派蒙·授权] 收到答复 channel_key={} text='{}'",
                    channel_key, msg.text[:40])
        # 落盘用户答复；问题由 ask_user() 发 SSE，没存到 session.messages，
        # 这里补个提示性 assistant 回执避免答案孤立
        await _persist_turn(channel_key, msg.text, "（已作为权限询问的答复）")
        return

    # 1) 入口轻量安全过滤（docs/paimon/paimon.md §轻量安全校验）
    #    两档：shell_danger=block / prompt_injection=warn 放行
    #    `/` 开头的命令消息跳过——命令由 dispatch_command 处理；其中 /task
    #    明确是"绕过轻量审查进入四影深度审查"的通道，不该被入口拦
    cfg = state.cfg
    is_command = msg.text.lstrip().startswith("/") if msg.text else False
    if cfg and cfg.input_filter_enabled and not is_command:
        from paimon.core.pre_filter import pre_filter
        hit = pre_filter(msg.text)
        if hit.verdict == "block":
            logger.warning(
                "[派蒙·入口过滤] 拒绝 {}: {} text={!r}",
                hit.category, hit.reason, msg.text[:80],
            )
            if state.irminsul:
                try:
                    await state.irminsul.audit_append(
                        event_type="input_filtered",
                        payload={
                            "verdict": "block",
                            "category": hit.category,
                            "reason": hit.reason,
                            "channel_key": channel_key,
                            "text_prefix": msg.text[:200],
                        },
                        actor="派蒙",
                    )
                except Exception as e:
                    logger.debug("[派蒙·入口过滤] audit 写入失败: {}", e)
            filter_hint = (
                f"⚠️ 消息被入口过滤拦截：{hit.reason}。\n"
                "如果是正常需求请换一种表达。"
            )
            await msg.reply(filter_hint)
            await _persist_turn(channel_key, msg.text, filter_hint)
            return
        elif hit.verdict == "warn":
            logger.info(
                "[派蒙·入口过滤] 警告通过 {}: {} text={!r}",
                hit.category, hit.reason, msg.text[:80],
            )
            if state.irminsul:
                try:
                    await state.irminsul.audit_append(
                        event_type="input_filtered",
                        payload={
                            "verdict": "warn",
                            "category": hit.category,
                            "reason": hit.reason,
                            "channel_key": channel_key,
                            "text_prefix": msg.text[:200],
                        },
                        actor="派蒙",
                    )
                except Exception as e:
                    logger.debug("[派蒙·入口过滤] audit 写入失败: {}", e)
            # 不 return，继续后续流程

    from paimon.core.commands import dispatch_command
    from paimon.core.commands._dispatch import SKILL_HANDLED_SENTINEL

    reply_text = await dispatch_command(msg, channel)
    if reply_text is not None:
        # skill 兜底分支已在 _invoke_skill 内 ephemeral 跑 + merge 主 session 带 meta
        # 这里跳过 msg.reply（避免推空 frame）和 _persist_turn（避免 user 文本无 meta
        # 写主 session 反而污染 LLM）；dispatch 的纯命令路径 reply_text 是真字符串照常落盘
        if reply_text == SKILL_HANDLED_SENTINEL:
            return
        await msg.reply(reply_text)
        await _persist_turn(channel_key, msg.text, reply_text)
        return

    cfg, session_mgr, model = _require_runtime()

    session = session_mgr.get_current(channel_key)
    if not session:
        session = session_mgr.create()
        session_mgr.switch(channel_key, session.id)

    from paimon.core.intent import classify_intent
    intent = await classify_intent(model, session, msg.text, state.skill_registry)

    if intent.kind == "skill":
        reply = await channel.make_reply(msg)
        sk = state.skill_registry.get(intent.skill_name) if state.skill_registry else None
        desc = (sk.description if sk else intent.skill_name) or intent.skill_name
        try:
            # 用 milestone 而不是 ack：QQ 端 ack 设计是暂存到首条 milestone 才发
            # （四影 prepare 阶段为省 seq 的优化），但天使路径没有后续 milestone，
            # ack 暂存会导致用户在 30s+ 工具循环里看不到任何提示。这里要立即发。
            # 同时用 reply.flush 把首次发送 chunk 推出去（QQ 是批次渠道，notice
            # 自身已直发，无需 flush；这里 flush 兜底以防别处实现差异）。
            await reply.notice(f"🎯 走 {intent.skill_name} —— {desc[:60]}", kind="milestone")
        except Exception:
            pass
        # 意图路由 skill 跟 /<skill> 兜底语义一致：ephemeral 跑 + merge 主 session 带 meta
        # 跳过 _persist_turn（_run_skill_isolated 内部已落盘带 meta 的两条）
        from paimon.core.commands._dispatch import _run_skill_isolated
        await _run_skill_isolated(
            skill_name=intent.skill_name, skill_msg=msg,
            channel=channel, main_session=session,
            main_user_text=msg.text,
        )
    else:
        await run_session_chat(msg, channel, session)

