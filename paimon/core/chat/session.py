"""会话级 chat 任务调度：单会话单任务 + 锁去抖 + 总超时升级魔女会 + 强制中止。

`run_session_chat` 是"启动一个新对话回合"的入口（异步任务把 handle_chat 调起）；
`stop_session_task` 给 /stop 命令 + 切会话强制取消用。
"""
from __future__ import annotations

import asyncio

from loguru import logger

from paimon.channels.base import Channel, IncomingMessage
from paimon.session import Session
from paimon.state import state

from ._handler import handle_chat
from ._persist import _persist_turn


async def run_session_chat(
    msg: IncomingMessage, channel: Channel, session: Session,
    skill_name: str = "",
):
    """启动一次对话回合：取消旧任务 → 锁内创建新 task → 套总超时 → 失败转魔女会。"""
    # 天使路径权限闸（docs/aimon.md §2.4）：敏感 skill 需询问用户
    if skill_name and state.authz_decision is not None:
        from paimon.core.authz import Verdict
        verdict, hint = await state.authz_decision.check_skill(
            skill_name, channel=channel, chat_id=msg.chat_id, session=session,
        )
        if verdict == Verdict.DENY:
            if hint:
                await msg.reply(hint)
            await _persist_turn(msg.channel_key, msg.text, hint or "（skill 权限被拒绝）")
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
    """强制取消会话当前对话任务；返回是否真的取消了（False = 没在跑）。"""
    lock = state.session_task_locks.setdefault(session_id, asyncio.Lock())
    async with lock:
        task = state.session_tasks.get(session_id)
        if not task or task.done():
            return False
        # 防自我 cancel + await 死锁：SSE handler 自身被 connection 断
        # 触发 CancelledError 进 except 后调 stop_session_task，注册的就是
        # current_task（_entry_task）。await task 会死锁。仅 cancel 不 await。
        cur = asyncio.current_task()
        task.cancel()
        if task is cur:
            return True
    try:
        await task
    except asyncio.CancelledError:
        pass
    except Exception as e:
        logger.debug("[派蒙·对话] 会话{}停止任务: {}", session_id, e)
    return True
