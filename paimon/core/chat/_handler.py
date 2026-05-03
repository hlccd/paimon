"""派蒙主对话 handler：构造 prompt → model.chat 流式输出 → 工具调用 → 压缩 / 标题。

`handle_chat` 是天使路径 + 闲聊路径共用的入口；run_session_chat 通过 asyncio.create_task
拉它起来。包含天使工具超时阈值 + 二次超时升级到魔女会的逻辑。
"""
from __future__ import annotations

import asyncio
import time

from loguru import logger

from paimon.channels.base import Channel, IncomingMessage
from paimon.session import Session
from paimon.state import state

from ._prompt import _build_system_prompt, _load_l1_memories  # noqa: F401  (_load_l1_memories 经 _prompt 重导出便于 patch 测试)
from ._runtime import _effective_compress_threshold_pct, _require_runtime


async def handle_chat(
    msg: IncomingMessage,
    channel: Channel,
    session: Session,
    skill_name: str = "",
):
    """派蒙主对话循环：装 system prompt + 工具集 → model.chat 流式 → 压缩+标题收尾。"""
    from paimon.angels.nicole import AngelFailure

    start_time = time.time()
    cfg, session_mgr, model = _require_runtime()

    sp = await _build_system_prompt(skill_name=skill_name, irminsul=state.irminsul)
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

        _SLOW_TOOLS = {"web_fetch", "video_process", "audio_process", "subscribe"}

        async def _execute_tool(name: str, arguments: str) -> str:
            """单工具调用包装器：慢工具发 notice + 单调用超时 + 第 2 次超时升级 AngelFailure。"""
            nonlocal angel_tool_timeouts
            # 慢工具在调用前推一条 tool notice，避免静默超过 watchdog 阈值
            # QQ 上此类 notice 会被渠道层丢弃（seq 不值当），Web 上渲染为浅灰小字
            if name in _SLOW_TOOLS:
                try:
                    await reply.notice(f"🔧 正在调用 {name}…", kind="tool")
                except Exception:
                    pass
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
                "subscribe",      # 话题订阅（写订阅+定时任务，同一级别）
                "dividend",       # 红利股追踪（读世界树 dividend 域 / 触发岩神采集）
                "web_fetch",      # 抓取 URL（只读外部）
                "knowledge",      # 知识库读写(写的是用户自己的域）
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
    except Exception as e:
        # OBS-002：旧版 except: pass 静默吞，落盘失败 user 完全不可知
        logger.warning("[派蒙·会话] generating 状态保存失败: {}", e)

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
                model_name = getattr(model, "last_chat_model_name", "") or "?"
                await reply.send(f"\n\n---\n{time_str} | ~{cost_str} · 🧠 {model_name}")
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
        except Exception as e:
            # OBS-002：旧版静默吞，回复完成态保存失败 user 不可知（下次进会话状态错乱）
            logger.warning("[派蒙·会话] 回复完成态保存失败: {}", e)

    if angel_failed:
        # 魔女会路径：跳过压缩/标题生成，把 AngelFailure 抛给 run_session_chat
        assert angel_failure_exc is not None
        raise angel_failure_exc

    if not interrupted:
        total_tokens, ratio = model.update_session_context_stats(
            session,
            context_window_tokens=cfg.context_window_tokens,
        )
        if ratio >= _effective_compress_threshold_pct(cfg):
            from paimon.shades import istaroth
            try:
                compressed = await istaroth.compress(
                    session,
                    model=model,
                    keep_recent_messages=max(cfg.context_keep_recent_messages, 0),
                    irminsul=state.irminsul,
                )
            except Exception as e:
                compressed = False
                logger.warning("[时执·压缩] 会话{}上下文压缩调用异常: {}", session.id, e)
            if compressed:
                total_tokens, ratio = model.update_session_context_stats(
                    session,
                    context_window_tokens=cfg.context_window_tokens,
                )
                logger.info(
                    "[时执·压缩] 会话{}压缩后 {:.1f}% ({} tokens)",
                    session.id, ratio, total_tokens,
                )

        session_mgr.save_session(session)

    user_msgs = [m for m in session.messages if m.get("role") == "user"]
    if len(user_msgs) == 1 and session.name.startswith("s-"):
        logger.debug("[派蒙·对话] 自动生成标题 {}（后台）", session.id)
        # fire-and-forget：title 生成 LLM 调用 10-20s，若 await 会阻塞 SSE 'done'
        # 帧 → 浏览器 fetch streaming 不结束 → 用户切会话发新消息会被 lock。
        # 改为 bg 后台跑，主响应立即返回，标题完成后再写入 session.name。
        user_text = user_msgs[0]["content"]

        async def _generate_title_bg() -> None:
            """后台生成会话标题；race 防护：会话被 /delete 后不复活。"""
            try:
                t = await model.generate_title(user_text, session_id=session.id)
            except Exception as e:
                logger.warning("[派蒙·对话] 标题生成失败 {}: {}", session.id[:8], e)
                return
            if not t:
                return
            # race 防护：用户可能在标题生成期间 /delete 该会话；
            # 不能让 bg 路径"复活"已删除的会话条目。
            if session.id not in session_mgr.sessions:
                logger.debug("[派蒙·对话] 标题生成完但会话已删 {}", session.id[:8])
                return
            session.name = t
            session_mgr.save_session(session)
            logger.info("[派蒙·对话] 会话{}标题: {}", session.id, t)

        from paimon.foundation.bg import bg
        bg(_generate_title_bg(), label=f"chat·title·{session.id[:8]}")
