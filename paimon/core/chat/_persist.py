"""会话消息落盘：常规一回合 + 四影专用补录。

`_persist_turn` 三种 case 处理 user 占位 / 完整对 / 常规追加；
`_persist_shades_turn` 处理四影路径下 model.chat 是否已 append 过 user 的差异。
"""
from __future__ import annotations

from loguru import logger

from paimon.session import Session
from paimon.state import state


# session.messages 里的 LLM 标准角色集合；其他 role（如 'notice'）是扩展条目，
# 持久化展示用，不进 LLM 上下文 + 也不参与 _persist_turn 的 case 检查。
_LLM_ROLES = frozenset({"system", "user", "assistant", "tool"})


def _meaningful_tail(msgs: list[dict], k: int) -> list[dict]:
    """从尾部取最后 k 条 LLM 标准 role 的消息（跳过 notice 等扩展 role）。"""
    out: list[dict] = []
    for m in reversed(msgs):
        if m.get("role") in _LLM_ROLES:
            out.append(m)
            if len(out) >= k:
                break
    return list(reversed(out))


async def _persist_turn(
    channel_key: str, user_text: str, reply_text: str,
) -> None:
    """把一回合 (user + assistant) append 到当前绑定会话并落盘。

    两种情形：
    1. 最后一条已是同 user（入口已先 persist user 占位，现在补 assistant）
       → 只 append assistant，避免 user 重复
    2. 其他 → 常规 append user + assistant（reply_text 空时只 append user）

    四影流式路径下：
    - 入口 `_persist_turn(channel_key, text, "")` 立即存 user（让切 tab 回来能看到）
    - 任务完成后 `_persist_turn(channel_key, text, final)` 走 case 1 补 assistant

    历史：曾有 case "user+assistant 完整一对已存 → 全跳过"，本意防御同回合
    race 重复调用，但 grep 全仓主流路径只调一次 _persist_turn，case 1/case 2
    已覆盖；旧 case 反而把"用户真正第二次发同命令"误判为 race 跳过落盘 →
    inline 显示但 session.messages 不记 → 切走切回历史丢失。2026-05 移除。
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

    def _eq(a: str | None, b: str) -> bool:
        return (a or "").strip() == b

    # 取最后一条 LLM 标准 role 消息做 case 检查 —— 中间夹的 notice 不影响判断
    tail = _meaningful_tail(msgs, 1)

    # case 1: user 已存但缺 assistant（入口占位 + 任务完成后补）
    if (
        tail
        and tail[-1].get("role") == "user"
        and _eq(tail[-1].get("content"), user_text_n)
    ):
        if reply_text:
            sess.messages.append({"role": "assistant", "content": reply_text})
            try:
                await state.session_mgr.save_session_async(sess)
            except Exception as e:
                logger.warning("[派蒙·落盘] save 失败 (case 1): {}", e)
        return

    # case 2: 常规 append
    sess.messages.append({"role": "user", "content": user_text})
    if reply_text:
        sess.messages.append({"role": "assistant", "content": reply_text})
    try:
        await state.session_mgr.save_session_async(sess)
    except Exception as e:
        # REL-005 升级：原 debug 静默 → warning，落盘失败需 user 可观测
        logger.warning("[派蒙·落盘] save 失败 (case 2): {}", e)
