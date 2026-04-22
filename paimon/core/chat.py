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
    from paimon.core.commands import dispatch_command

    reply_text = await dispatch_command(msg, channel)
    if reply_text is not None:
        await msg.reply(reply_text)
        return

    cfg, session_mgr, model = _require_runtime()

    channel_key = msg.channel_key
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

    try:
        await task
    except asyncio.CancelledError:
        raise
    finally:
        async with lock:
            if state.session_tasks.get(session.id) is task:
                del state.session_tasks[session.id]


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


async def run_shades_pipeline(msg: IncomingMessage, channel: Channel, session: Session):
    cfg, session_mgr, model = _require_runtime()

    logger.info("[派蒙·四影] [{}] 复杂任务: {}", session.id[:8], msg.text)

    reply = await channel.make_reply(msg)

    try:
        from paimon.shades.pipeline import ShadesPipeline
        pipeline = ShadesPipeline(model, state.irminsul)

        result = await pipeline.run(msg.text, session_id=session.id)

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

    if state.tool_registry:
        from paimon.tools.base import ToolContext
        tool_ctx = ToolContext(
            registry=state.tool_registry,
            channel=channel,
            chat_id=msg.chat_id,
            session=session,
        )

        async def _execute_tool(name: str, arguments: str) -> str:
            return await state.tool_registry.execute(name, arguments, tool_ctx)

        tool_executor = _execute_tool

        if skill_name:
            tools = state.tool_registry.to_openai_tools()
        else:
            _CHAT_TOOLS = {"schedule"}
            tools = [
                t for t in state.tool_registry.to_openai_tools()
                if t["function"]["name"] in _CHAT_TOOLS
            ] or None

    reply = await channel.make_reply(msg)
    buf = ""
    any_text_sent = False
    interrupted = False

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
    finally:
        if not interrupted:
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
        else:
            try:
                await reply.flush()
            except Exception:
                pass

        if interrupted and buf:
            last = session.messages[-1] if session.messages else {}
            if last.get("role") != "assistant":
                session.messages.append({"role": "assistant", "content": buf})

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
