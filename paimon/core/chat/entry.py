"""入站消息总入口 + 后台四影 pipeline 启动器：负责权限询问 / 入口过滤 / 命令分流 / 意图分发。

`on_channel_message` 是所有渠道（QQ/Web/TG）消息的第一站；
`enter_shades_pipeline_background` 是 complex 意图的后台执行器，分流式/批次双路径。
"""
from __future__ import annotations

import asyncio

from loguru import logger

from paimon.channels.base import Channel, IncomingMessage
from paimon.session import Session
from paimon.state import state

from ._persist import _persist_turn
from ._runtime import _require_runtime
from .session import run_session_chat


async def on_channel_message(msg: IncomingMessage, channel: Channel):
    """渠道消息总入口：权限答复消化 / 入口过滤 / 命令分流 / 意图分类（complex/skill/chat）。"""
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
                "如果是正常需求请换一种表达；确需执行高风险操作请用 `/task` 走四影审查。"
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
        # 去重交给 _persist_turn（/task 经 enter_shades_pipeline_background 已落一份）
        await _persist_turn(channel_key, msg.text, reply_text)
        return

    cfg, session_mgr, model = _require_runtime()

    session = session_mgr.get_current(channel_key)
    if not session:
        session = session_mgr.create()
        session_mgr.switch(channel_key, session.id)

    from paimon.core.intent import classify_intent
    intent = await classify_intent(model, session, msg.text, state.skill_registry)

    if intent.kind == "complex":
        # ack 由 pipeline.prepare 内部发（那时已有 LLM 短标题，更可读）
        reply = await channel.make_reply(msg)
        # 关键：任务开始前立即 persist user 占位，让任务跑几分钟期间用户切 tab 回来
        # 点会话能看到自己发过的问题（否则 shield(execute) 卡住整条 await，user 都
        # 要等任务完成才落盘）。直接 append + save 不经 _persist_turn 抽象层，
        # 保证一定生效 + 日志可见。任务完成后下面 _persist_turn 走 case 2 补 assistant。
        session.messages.append({"role": "user", "content": msg.text})
        await session_mgr.save_session_async(session)
        logger.info(
            "[派蒙·四影·入口 persist] complex_user={!r} (session={} msgs={})",
            msg.text[:60], session.id[:8], len(session.messages),
        )
        hint = await enter_shades_pipeline_background(msg, channel, session)
        # hint 为空串（QQ 批次路径，final 已在 _bg 内部 reply.send 过）时跳过外层 send，
        # 避免发 SSE 空 message frame 把前端 typing 占位替换为空气泡。
        if hint:
            try:
                await reply.send(hint)
                await reply.flush()
            except Exception:
                pass
        # persist 统一由外层做：/task 命令路径走 dispatch_command 分支自带 _persist_turn；
        # complex intent 分支（非命令）之前漏了，这里补一次。hint 为空也要存 user 一侧
        # 让 LLM 下轮至少知道"上一轮用户发起了四影任务"。
        await _persist_turn(msg.channel_key, msg.text, hint)
    elif intent.kind == "skill":
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


async def enter_shades_pipeline_background(
    msg: IncomingMessage, channel: Channel, session: Session,
    *, persist_user_text: str | None = None,
) -> str:
    """前台同步跑 prepare（入口审 + round-1 plan + 批量授权），execute 按渠道分流。

    - prepare 必须在 SSE 活跃时跑（ask_user 要问用户）
    - execute 分流：
        * 流式渠道（WebUI SSE）：asyncio.shield 同步等到完成，final 作为正文返回
          给上层 reply.send，前端把 typing 占位替换为正文气泡。SSE 断开时
          CancelledError 不穿透打断 execute。
        * 批次渠道（QQ）：create_task 后台跑，final 在 _bg 里 reply.send+flush 送达。
    - persist 职责分两阶段：
        1) 入口由外层 caller 立即 `_persist_turn(user, "")` 存 user 占位（让任务
           跑期间用户切 tab/刷新能看到自己发的问题）
        2) 任务完成后外层再 `_persist_turn(user, final)` 走 case 2 补 assistant
    - `persist_user_text` 用于 SSE 断开后台 finalize 的 case 2 persist —— 必须
      和入口 persist 的一致。/task 命令路径下 msg.text=ctx.args（不含前缀），
      外层入口用 ctx.msg.text（含 /task 前缀），两者不一致，所以需要透传。
      None 时默认 msg.text。
    """
    channel_name = msg.channel_name
    chat_id = msg.chat_id
    text = msg.text
    finalize_user_text = persist_user_text if persist_user_text is not None else text

    reply_for_notice = await channel.make_reply(msg)

    from paimon.shades.pipeline import ShadesPipeline
    pipeline = ShadesPipeline(
        state.model, state.irminsul,
        channel=channel, chat_id=chat_id,
        authz_cache=state.authz_cache,
        reply=reply_for_notice,
    )

    # 注册当前协程（实际是 SSE handler task）到 state.session_tasks，让 /stop 能在
    # prepare 阶段就 cancel —— prepare 含 jonova review + naberius plan 多次 LLM 调用，
    # 几十秒级别。如果只在 execute 阶段注册（旧实现），用户在 prepare 期间发 /stop
    # 就找不到任务回复"当前没有正在生成的回复"。execute 创建后会切换为 execute_task。
    _stop_lock = state.session_task_locks.setdefault(session.id, asyncio.Lock())
    _entry_task = asyncio.current_task()
    if _entry_task is not None:
        async with _stop_lock:
            state.session_tasks[session.id] = _entry_task

    try:
        # 前台：入口审 + plan + 批量授权（SSE 必须活跃）
        prep = await pipeline.prepare(
            text, session_id=session.id,
        )
    except BaseException:
        # prepare 抛出（含 /stop 触发的 CancelledError）→ 兜底清理后透传
        if _entry_task is not None:
            async with _stop_lock:
                if state.session_tasks.get(session.id) is _entry_task:
                    del state.session_tasks[session.id]
        raise
    if not prep.ok:
        # 准备阶段失败（死执拒/授权全拒/异常）→ 回一段字给外层做正文送达 + persist
        if _entry_task is not None:
            async with _stop_lock:
                if state.session_tasks.get(session.id) is _entry_task:
                    del state.session_tasks[session.id]
        return prep.msg

    task_id = prep.task.id
    plan = prep.plan
    assert plan is not None  # ok=True 保证

    async def _push_summary() -> None:
        """execute 完成后推 workspace summary.md 到 📨 推送（有就推，两渠道都保留）。"""
        try:
            from paimon.foundation.task_workspace import (
                get_workspace_path, workspace_exists,
            )
            if state.march and workspace_exists(task_id):
                summary = get_workspace_path(task_id) / "summary.md"
                if summary.exists():
                    await state.march.ring_event(
                        channel_name=channel_name, chat_id=chat_id,
                        source="四影", message=summary.read_text(encoding="utf-8")[:4000],
                    )
        except Exception as e:
            logger.warning("[派蒙·四影] 推 summary 失败: {}", e)

    from paimon.foundation.bg import bg

    if reply_for_notice.streaming:
        # 流式渠道：同步等 execute，拿 final 交给外层走正文。
        # shield 保护 execute —— SSE 断（用户刷新/关页）时 CancelledError 不穿透，
        # execute 继续后台跑完归档，不会把任务卡在 status=running 直到 stuck_timeout。
        logger.info(
            "[派蒙·四影] streaming 渠道 {} 同步等 execute task={}",
            channel_name, task_id[:8],
        )
        execute_task = asyncio.create_task(
            pipeline.execute(prep.task, plan, session_id=session.id)
        )

        # 切换注册：从 _entry_task 切到 execute_task
        # —— prepare 已结束，execute 才是真正的工作单元；/stop 直接 cancel execute_task
        # 而非 SSE handler，让 shield 不再阻挡（shield 只保护内部 task 不被 awaiter
        # cancel 传播；inner task 自身被 cancel 时仍会抛 CancelledError）
        async with _stop_lock:
            state.session_tasks[session.id] = execute_task

        async def _finalize_after_disconnect() -> None:
            """SSE 断开时的后台收尾：等 execute 归档 + 推 📨 summary + 补 persist assistant。

            用户可能几分钟后回来点会话；user 已在入口由外层 persist 过（占位），
            这里补 assistant 让历史完整（_persist_turn 走 case 2 只补 assistant）。
            persist 必须用 `finalize_user_text`（外层入口 persist 时用的同款 text）,
            否则 case 2 匹配不上会再 append 一对，变成 4 msgs。
            """
            final = ""
            try:
                final = await execute_task
            except Exception as e:
                logger.exception(
                    "[派蒙·四影] execute 异常（断连后台）task={}: {}", task_id, e,
                )
                final = f"💥 任务异常：{e}"
            await _push_summary()
            await _persist_turn(
                msg.channel_key, finalize_user_text,
                (final or "(无产物)")[:5000],
            )

        final_result = ""
        try:
            try:
                final_result = await asyncio.shield(execute_task)
            except asyncio.CancelledError:
                # 区分两种 CancelledError 来源：
                #   1) execute_task 自身被取消（/stop 命令调 stop_session_task）→ 已无 inner 任务
                #      可继续，不再 bg finalize；CancelledError 透传到上层让 SSE 收尾
                #   2) 外层被取消（SSE 断 / shield 的 awaiter 被 cancel）→ inner 仍在跑，
                #      bg finalize 接管"等 execute 完成 + 推 summary + 补 persist assistant"
                if execute_task.done():
                    logger.info(
                        "[派蒙·四影] task={} 被显式取消（/stop）", task_id[:8],
                    )
                else:
                    logger.info(
                        "[派蒙·四影] SSE 断开 task={}，execute 继续后台完成",
                        task_id[:8],
                    )
                    bg(_finalize_after_disconnect(), label=f"shades·finalize·{task_id[:8]}")
                raise
            except Exception as e:
                logger.exception("[派蒙·四影] execute 异常 task={}: {}", task_id, e)
                final_result = f"💥 任务异常：{e}"

            await _push_summary()
            # final 作为正文返回 —— 外层 reply.send(final) 会触发 SSE data.type=message，
            # 前端 fullResponse += final + marked.parse 把 typing 气泡替换为正文气泡。
            return (final_result or "(无产物)")[:5000]
        finally:
            async with _stop_lock:
                if state.session_tasks.get(session.id) is execute_task:
                    del state.session_tasks[session.id]

    # 批次渠道（QQ）：后台跑，final 在 _bg 里通过 reply.send + flush 送达 + persist assistant。
    async def _bg() -> None:
        """QQ 批次渠道后台执行：跑 execute → 推 summary → reply.send final → persist。"""
        final = ""
        try:
            final = await pipeline.execute(prep.task, plan, session_id=session.id)
        except Exception as e:
            logger.exception("[派蒙·四影 bg] execute 失败: {}", e)
            final = f"💥 任务异常：{e}"
        await _push_summary()
        if final:
            try:
                await reply_for_notice.send(final[:5000])
                await reply_for_notice.flush()
            except Exception as e:
                logger.debug("[派蒙·四影 bg] 推 final 失败（可能窗口已关）: {}", e)
        # persist assistant 让 LLM 下轮能看到上轮产出（case 2 命中：user 已在入口占位）。
        await _persist_turn(
            msg.channel_key, finalize_user_text,
            (final or "(无产物)")[:5000],
        )

    bg(_bg(), label=f"shades·qq_bg·{task_id[:8]}")
    # QQ 路径 return 空串，外层不再 reply.send 正文 hint（信息已在 🚀 milestone 里）。
    # 入口 _entry_task 注册收尾：QQ 分支由 bg 接管 execute，prepare 已结束 → 解绑
    if _entry_task is not None:
        async with _stop_lock:
            if state.session_tasks.get(session.id) is _entry_task:
                del state.session_tasks[session.id]
    return ""
