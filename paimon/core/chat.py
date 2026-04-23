from __future__ import annotations

import asyncio
import time

from loguru import logger

from paimon.channels.base import Channel, IncomingMessage
from paimon.session import Session
from paimon.state import state


def _require_runtime():
    cfg = state.cfg
    session_mgr = state.session_mgr
    model = state.model
    if not cfg or not session_mgr or not model:
        raise RuntimeError("运行时状态未初始化")
    return cfg, session_mgr, model


async def on_channel_message(msg: IncomingMessage, channel: Channel):
    # 0) 若有挂起的权限询问，本条消息当作答复消化，不走正常 chat 流
    channel_key = msg.channel_key
    pending = state.pending_asks.get(channel_key)
    if pending is not None and not pending.done():
        pending.set_result(msg.text)
        logger.info("[派蒙·授权] 收到答复 channel_key={} text='{}'",
                    channel_key, msg.text[:40])
        return

    from paimon.core.commands import dispatch_command

    reply_text = await dispatch_command(msg, channel)
    if reply_text is not None:
        await msg.reply(reply_text)
        return

    cfg, session_mgr, model = _require_runtime()

    session = session_mgr.get_current(channel_key)
    if not session:
        session = session_mgr.create()
        session_mgr.switch(channel_key, session.id)

    from paimon.core.intent import classify_intent
    intent = await classify_intent(model, session, msg.text, state.skill_registry)

    if intent.kind == "complex":
        await run_shades_pipeline(msg, channel, session)
    elif intent.kind == "skill":
        await run_session_chat(msg, channel, session, skill_name=intent.skill_name)
    else:
        await run_session_chat(msg, channel, session)


async def run_session_chat(
    msg: IncomingMessage, channel: Channel, session: Session,
    skill_name: str = "",
):
    # 天使路径权限闸（docs/aimon.md §2.4）：敏感 skill 需询问用户
    if skill_name and state.authz_decision is not None:
        from paimon.core.authz import Verdict
        verdict, hint = await state.authz_decision.check_skill(
            skill_name, channel=channel, chat_id=msg.chat_id, session=session,
        )
        if verdict == Verdict.DENY:
            if hint:
                await msg.reply(hint)
            return
        if hint:
            # 放行时附带的友好提示（如"按之前的永久授权放行"）
            await msg.reply(hint + "\n")

    lock = state.session_task_locks.setdefault(session.id, asyncio.Lock())
    task: asyncio.Task | None = None

    async with lock:
        existing = state.session_tasks.get(session.id)
        if existing and not existing.done():
            existing.cancel()
            try:
                await existing
            except asyncio.CancelledError:
                pass
            except Exception as e:
                logger.debug("[派蒙·对话] 会话{}旧任务结束: {}", session.id, e)

        task = asyncio.create_task(handle_chat(msg, channel, session, skill_name=skill_name))
        state.session_tasks[session.id] = task

    # 天使路径（skill_name 非空）套整体超时；闲聊路径不套
    from paimon.angels.nicole import AngelFailure, escalate_to_shades

    cfg = state.cfg
    total_timeout = (
        cfg.angel_total_timeout_seconds if (skill_name and cfg) else None
    )

    angel_failure: AngelFailure | None = None
    try:
        if total_timeout is not None:
            # 注意：不用 asyncio.wait_for —— handle_chat 会吞 CancelledError 并正常 return，
            # 导致 wait_for 看到 task "正常完成"，超时信号丢失。
            # 改用 asyncio.wait 显式判断 task 是否仍在 pending。
            done, pending = await asyncio.wait({task}, timeout=total_timeout)
            if task in pending:
                task.cancel()
                # race 防护：task 被 cancel 前可能已经在抛 AngelFailure(tool_timeout)。
                # 必须把它识别出来，保留真实失败原因；只有当 task 确实被 cancel 消化
                # 或无异常时，才用 total_timeout 作为兜底原因。
                try:
                    await task
                except AngelFailure as e:
                    angel_failure = e
                except asyncio.CancelledError:
                    pass
                except Exception:
                    pass
                if angel_failure is None:
                    angel_failure = AngelFailure(
                        reason=f"整体超过 {total_timeout} 秒未完成",
                        stage="total_timeout",
                    )
            else:
                exc = task.exception()
                if exc is not None:
                    if isinstance(exc, AngelFailure):
                        angel_failure = exc
                    else:
                        # CancelledError / 其他异常：原样传播
                        raise exc
        else:
            await task
    except AngelFailure as e:
        angel_failure = e
    except asyncio.CancelledError:
        raise
    finally:
        async with lock:
            if state.session_tasks.get(session.id) is task:
                del state.session_tasks[session.id]

    if angel_failure is not None:
        await escalate_to_shades(
            msg, channel, session,
            reason=angel_failure.reason,
        )


async def stop_session_task(session_id: str) -> bool:
    lock = state.session_task_locks.setdefault(session_id, asyncio.Lock())
    async with lock:
        task = state.session_tasks.get(session_id)
        if not task or task.done():
            return False
        task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
    except Exception as e:
        logger.debug("[派蒙·对话] 会话{}停止任务: {}", session_id, e)
    return True


async def run_shades_pipeline(
    msg: IncomingMessage,
    channel: Channel,
    session: Session,
    *,
    escalation_reason: str | None = None,
):
    cfg, session_mgr, model = _require_runtime()

    logger.info("[派蒙·四影] [{}] 复杂任务: {}", session.id[:8], msg.text)

    reply = await channel.make_reply(msg)

    try:
        from paimon.shades.pipeline import ShadesPipeline
        pipeline = ShadesPipeline(model, state.irminsul)

        result = await pipeline.run(
            msg.text, session_id=session.id,
            escalation_reason=escalation_reason,
        )

        if result:
            await reply.send(result)

        cost = model.last_chat_cost_usd
        cost_str = f"${cost:.4f}" if cost < 0.01 else f"${cost:.2f}"
        await reply.send(f"\n\n---\n~{cost_str}")
    except Exception as e:
        logger.error("[派蒙·四影] 管线异常: {}", e)
        await reply.send(f"\n\n> [错误] 四影管线执行失败: {e}")
    finally:
        try:
            await reply.flush()
        except Exception:
            pass


async def handle_chat(
    msg: IncomingMessage,
    channel: Channel,
    session: Session,
    skill_name: str = "",
):
    from paimon.angels.nicole import AngelFailure

    start_time = time.time()
    cfg, session_mgr, model = _require_runtime()

    sp = _build_system_prompt(skill_name=skill_name)
    if session.messages and session.messages[0].get("role") == "system":
        session.messages[0] = {"role": "system", "content": sp}
    else:
        session.messages.insert(0, {"role": "system", "content": sp})

    logger.info("[派蒙·对话] [{}] 用户: {}", session.id[:8], msg.text)

    tools = None
    tool_executor = None
    component = skill_name or "chat"
    purpose = skill_name or "闲聊"

    # 天使路径才启用单 tool 超时（闲聊工具如 knowledge/memory 不套）
    tool_timeout = cfg.angel_tool_timeout_seconds if skill_name else None
    angel_tool_timeouts = 0

    if state.tool_registry:
        from paimon.tools.base import ToolContext
        tool_ctx = ToolContext(
            registry=state.tool_registry,
            channel=channel,
            chat_id=msg.chat_id,
            session=session,
        )

        async def _execute_tool(name: str, arguments: str) -> str:
            nonlocal angel_tool_timeouts
            if tool_timeout is None:
                return await state.tool_registry.execute(name, arguments, tool_ctx)

            def _trip_timeout(actual_elapsed: float | None = None) -> None:
                """命中超时一次：累加计数，第 2 次抛 AngelFailure。"""
                nonlocal angel_tool_timeouts
                angel_tool_timeouts += 1
                if actual_elapsed is not None:
                    logger.warning(
                        "[天使·超时] [{}] 工具 {} 耗时 {:.1f}s > 阈值 {}s（第 {} 次）",
                        session.id[:8], name, actual_elapsed, tool_timeout, angel_tool_timeouts,
                    )
                else:
                    logger.warning(
                        "[天使·超时] [{}] 工具 {} 在 {}s 内未返回（第 {} 次）",
                        session.id[:8], name, tool_timeout, angel_tool_timeouts,
                    )
                if angel_tool_timeouts >= 2:
                    raise AngelFailure(
                        reason=f"工具连续 {angel_tool_timeouts} 次超时（阈值 {tool_timeout}s）",
                        stage="tool_timeout",
                    )

            t0 = time.time()
            try:
                result = await asyncio.wait_for(
                    state.tool_registry.execute(name, arguments, tool_ctx),
                    timeout=tool_timeout,
                )
            except asyncio.TimeoutError:
                _trip_timeout()
                return (
                    f"[天使·超时] 工具 {name} 在 {tool_timeout}s 内未返回。"
                    "请改换方式，或直接告诉用户当前任务超出天使能力范围。"
                )
            # 工具"正常返回"但实际耗时超阈值：常见于工具内部自捕获超时并返错字符串
            # （例如 video_process / audio_process 内嵌 subprocess timeout），或工具同步
            # 阻塞事件循环导致 asyncio cancel 无效。按墙钟耗时兜底判定。
            elapsed = time.time() - t0
            if elapsed >= tool_timeout:
                _trip_timeout(actual_elapsed=elapsed)
                return (
                    f"[天使·超时提醒] 工具 {name} 实际耗时 {elapsed:.1f}s，"
                    f"超过 {tool_timeout}s 阈值。工具原始结果：\n{result}"
                )
            return result

        tool_executor = _execute_tool

        if skill_name:
            tools = state.tool_registry.to_openai_tools()
        else:
            # 闲聊模式下派蒙可以调用的"安全"工具集 —— 单次调用、无破坏性副作用
            # 严格排除的：
            #   - exec / file_ops —— 需要走四影安全审查
            #   - use_skill —— 会绕过 AuthzDecision 直接注入 skill 指令；改由意图分类走 skill 路径
            #   - skill_manage —— 冰神专属
            #   - audio/video_process —— 重型，归七神
            _CHAT_TOOLS = {
                "schedule",       # 定时任务（写世界树 scheduled_tasks 域，无副作用）
                "web_fetch",      # 抓取 URL（只读外部）
                "knowledge",      # 知识库读写（写的是用户自己的域）
                "memory",         # 记忆读写
            }
            tools = [
                t for t in state.tool_registry.to_openai_tools()
                if t["function"]["name"] in _CHAT_TOOLS
            ] or None

    reply = await channel.make_reply(msg)
    buf = ""
    any_text_sent = False
    interrupted = False
    angel_failed = False
    angel_failure_exc: "BaseException | None" = None

    session.response_status = "generating"
    try:
        session_mgr.save_session(session)
    except Exception:
        pass

    try:
        async for text in model.chat(
            session, msg.text,
            tools=tools, tool_executor=tool_executor,
            component=component, purpose=purpose,
        ):
            buf += text
            await reply.send(text)
            any_text_sent = True
    except (asyncio.CancelledError, ConnectionResetError, ConnectionError):
        interrupted = True
        logger.info("[派蒙·对话] 会话{}回复中断", session.id)
    except AngelFailure as e:
        # 魔女会信号：延后到 finally 之后再 raise，保证清理一致性
        angel_failed = True
        angel_failure_exc = e
        logger.info(
            "[派蒙·对话] 会话{}天使失败，将转交魔女会: {}",
            session.id, e.reason,
        )
    finally:
        # 魔女会路径：跳过"(空回复)"+花费条，仅 flush 已发内容
        if not interrupted and not angel_failed:
            try:
                if not any_text_sent:
                    await reply.send("(空回复)")
                elapsed = time.time() - start_time
                if elapsed < 60:
                    time_str = f"{elapsed:.2f}秒"
                else:
                    minutes = int(elapsed // 60)
                    seconds = elapsed % 60
                    time_str = f"{minutes}分{seconds:.1f}秒"
                cost = model.last_chat_cost_usd
                cost_str = f"${cost:.4f}" if cost < 0.01 else f"${cost:.2f}"
                await reply.send(f"\n\n---\n{time_str} | ~{cost_str}")
            except Exception:
                pass
        try:
            await reply.flush()
        except Exception:
            pass

        if (interrupted or angel_failed) and buf:
            last = session.messages[-1] if session.messages else {}
            if last.get("role") != "assistant":
                session.messages.append({"role": "assistant", "content": buf})

        if angel_failed:
            session.response_status = "interrupted"
        else:
            session.response_status = "interrupted" if interrupted else "completed"
        if buf:
            elapsed = time.time() - start_time
            if elapsed < 60:
                t = f"{elapsed:.2f}秒"
            else:
                t = f"{int(elapsed // 60)}分{elapsed % 60:.1f}秒"
            c = model.last_chat_cost_usd
            cs = f"${c:.4f}" if c < 0.01 else f"${c:.2f}"
            logger.info("[派蒙·对话] [{}] 回复 ({} | {}):\n{}", session.id[:8], t, cs, buf)
        try:
            session_mgr.save_session(session)
        except Exception:
            pass

    if angel_failed:
        # 魔女会路径：跳过压缩/标题生成，把 AngelFailure 抛给 run_session_chat
        assert angel_failure_exc is not None
        raise angel_failure_exc

    if not interrupted:
        total_tokens, ratio = model.update_session_context_stats(
            session,
            context_window_tokens=cfg.context_window_tokens,
        )
        if ratio >= cfg.context_compress_threshold_pct:
            try:
                compressed = await model.compress_session_context(
                    session,
                    keep_recent_messages=max(cfg.context_keep_recent_messages, 0),
                )
            except Exception as e:
                compressed = False
                logger.warning("[派蒙·压缩] 会话{}上下文压缩失败: {}", session.id, e)
            if compressed:
                total_tokens, ratio = model.update_session_context_stats(
                    session,
                    context_window_tokens=cfg.context_window_tokens,
                )
                logger.info(
                    "[派蒙·压缩] 会话{}压缩后 {:.1f}% ({} tokens)",
                    session.id, ratio, total_tokens,
                )

        session_mgr.save_session(session)

    user_msgs = [m for m in session.messages if m.get("role") == "user"]
    if len(user_msgs) == 1 and session.name.startswith("s-"):
        logger.debug("[派蒙·对话] 自动生成标题 {}", session.id)
        title = await model.generate_title(user_msgs[0]["content"], session_id=session.id)
        if title:
            session.name = title
            session_mgr.save_session(session)
            logger.info("[派蒙·对话] 会话{}标题: {}", session.id, title)


def _build_system_prompt(skill_name: str = "") -> str:
    from pathlib import Path

    cfg = state.cfg
    if not cfg:
        return "你是派蒙，一个友好的AI助手。"

    template_path = Path(__file__).parent.parent.parent / "templates" / "paimon.t"
    if template_path.exists():
        base = template_path.read_text(encoding="utf-8")
    else:
        home_template = cfg.paimon_home / "paimon.t"
        if home_template.exists():
            base = home_template.read_text(encoding="utf-8")
        else:
            base = "你是派蒙，一个友好的AI助手。请用中文回复。"

    skill_registry = state.skill_registry

    if skill_name and skill_registry:
        skill = skill_registry.get(skill_name)
        if skill:
            return (
                f"{base}\n\n"
                f"---\n# 当前任务: Skill「{skill.name}」\n\n"
                f"{skill.body}\n\n"
                f"请严格按照以上 Skill 指令处理用户的请求。"
            )

    return base
