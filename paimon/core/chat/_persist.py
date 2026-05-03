"""会话消息落盘：常规一回合 + 四影专用补录。

`_persist_turn` 三种 case 处理 user 占位 / 完整对 / 常规追加；
`_persist_shades_turn` 处理四影路径下 model.chat 是否已 append 过 user 的差异。
"""
from __future__ import annotations

from loguru import logger

from paimon.session import Session
from paimon.state import state


async def _persist_turn(
    channel_key: str, user_text: str, reply_text: str,
) -> None:
    """把一回合 (user + assistant) append 到当前绑定会话并落盘。

    三种情形：
    1. 最后两条已是同 (user, assistant) 对 → 完整去重跳过
    2. 最后一条已是同 user（入口已先 persist user 占位，现在补 assistant）
       → 只 append assistant，避免 user 重复
    3. 其他 → 常规 append user + assistant（reply_text 空时只 append user）

    四影流式路径下：
    - 入口 `_persist_turn(channel_key, text, "")` 立即存 user（让切 tab 回来能看到）
    - 任务完成后 `_persist_turn(channel_key, text, final)` 走 case 2 补 assistant
    """
    if not state.session_mgr or not user_text or not user_text.strip():
        return
    try:
        from paimon.channels.webui.channel import PUSH_SESSION_ID as _PUSH_ID
    except Exception:
        _PUSH_ID = None
    sess = state.session_mgr.get_current(channel_key)
    if not sess or sess.id == _PUSH_ID:
        return
    msgs = sess.messages

    # REL-009 加固：用 strip() 比较抹平尾部空格/换行差异
    # （旧实现严格相等，stream 处理偶发尾换行差异会让 case 1 不命中触发重复 append）
    user_text_n = (user_text or "").strip()
    reply_text_n = (reply_text or "").strip()

    def _eq(a: str | None, b: str) -> bool:
        return (a or "").strip() == b

    # case 1: 完整一对已存
    if (
        len(msgs) >= 2
        and msgs[-2].get("role") == "user"
        and _eq(msgs[-2].get("content"), user_text_n)
        and msgs[-1].get("role") == "assistant"
        and _eq(msgs[-1].get("content"), reply_text_n)
    ):
        return

    # case 2: user 已存但缺 assistant（入口占位 + 任务完成后补）
    if (
        msgs
        and msgs[-1].get("role") == "user"
        and _eq(msgs[-1].get("content"), user_text_n)
    ):
        if reply_text:
            sess.messages.append({"role": "assistant", "content": reply_text})
            try:
                await state.session_mgr.save_session_async(sess)
            except Exception as e:
                logger.warning("[派蒙·落盘] save 失败 (case 2): {}", e)
        return

    # case 3: 常规 append
    sess.messages.append({"role": "user", "content": user_text})
    if reply_text:
        sess.messages.append({"role": "assistant", "content": reply_text})
    try:
        await state.session_mgr.save_session_async(sess)
    except Exception as e:
        # REL-005 升级：原 debug 静默 → warning，落盘失败需 user 可观测
        logger.warning("[派蒙·落盘] save 失败 (case 3): {}", e)


def _persist_shades_turn(
    session: Session,
    user_text: str,
    assistant_text: str,
    ok: bool,
) -> None:
    """把四影一轮的 user/assistant 消息补进 session.messages。

    幂等：若最后一条已是当前 user_text（说明魔女会路径的 model.chat 已 append 过），
    就不重复 append user；assistant 则按需追加。
    """
    if not session.messages:
        # 极端情况：新会话还没被 handle_chat 处理过（纯 complex 直送）
        session.messages.append({"role": "user", "content": user_text})
    else:
        last = session.messages[-1]
        last_role = last.get("role")
        last_content = last.get("content") or ""
        # 情况 A：最后一条就是当前用户消息 → 不重复 append user
        if last_role == "user" and last_content == user_text:
            pass
        # 情况 B：最后一条是 assistant，说明 handle_chat 已闭环了一轮；
        # user 消息肯定在更早之前已 append（由 model.chat 做）。不再补 user。
        elif last_role == "assistant":
            pass
        # 情况 C：最后一条不是当前 user 也不是 assistant（或完全别的 session 结构）
        else:
            session.messages.append({"role": "user", "content": user_text})

    # 追加四影产物作为 assistant message
    if assistant_text:
        # 失败也记录，避免历史空洞；带 [四影失败] 前缀便于后续识别
        content = assistant_text if ok else f"[四影未完成] {assistant_text}"
        session.messages.append({"role": "assistant", "content": content})
