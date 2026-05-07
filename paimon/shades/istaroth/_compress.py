"""时执 · Istaroth — 活跃会话上下文压缩：tool pair 对齐 + 4 段 prompt + 熔断。"""
from __future__ import annotations

import json
import time
from typing import TYPE_CHECKING

from loguru import logger

from paimon.foundation.irminsul import Irminsul
from paimon.session import Session

if TYPE_CHECKING:
    from paimon.llm.model import Model


# 连续失败触发熔断的阈值
MAX_CONSECUTIVE_COMPACT_FAILURES = 3



# ==================== 活跃会话上下文压缩 ====================


def _is_tool_related(msg: dict) -> bool:
    """判断一条消息是否属于 tool-use 交互（需整组一起切分）。"""
    role = msg.get("role", "")
    if role == "tool":
        return True
    if role == "assistant" and msg.get("tool_calls"):
        return True
    return False


def _adjust_keep_start_for_tool_pairs(
    messages: list[dict],
    keep_start: int,
    non_system_start: int,
) -> int:
    """保留段 tool pair 对齐（改进 2）。

    如果 messages[keep_start] 是 tool 或 assistant(tool_calls) 的后半截，
    继续向前扫到第一条"非 tool 相关"的消息（通常是 user 或 assistant 纯文本）。
    这样保证保留段不会切在 tool-use 中间。
    """
    adjusted = keep_start
    while adjusted > non_system_start and _is_tool_related(messages[adjusted]):
        adjusted -= 1
    # 如果落在 assistant 纯文本但**下一条**是 tool，继续前移
    while (
        adjusted > non_system_start
        and messages[adjusted].get("role") == "assistant"
        and not messages[adjusted].get("tool_calls")
        and adjusted + 1 < len(messages)
        and messages[adjusted + 1].get("role") == "tool"
    ):
        adjusted -= 1
    return adjusted

async def compress(
    session: Session,
    *,
    model: "Model",
    keep_recent_messages: int,
    irminsul: Irminsul | None = None,
) -> bool:
    """活跃会话上下文压缩。

    搬自 Model.compress_session_context，日志节点换为 [时执·压缩]，
    新增 4 项改进（见模块 docstring）。

    返回 True 表示执行并成功；False 表示本次跳过（无需压缩 / 熔断禁用 / 无可压缩段）。
    """
    # 改进 4：熔断
    if getattr(session, "auto_compact_disabled", False):
        logger.debug(
            "[时执·压缩] 会话 {} 已熔断 auto-compact，跳过",
            session.id[:8],
        )
        return False

    if not session.messages:
        return False

    non_system_start = 1 if session.messages[0].get("role") == "system" else 0
    non_system_count = len(session.messages) - non_system_start
    if non_system_count <= max(keep_recent_messages, 0):
        return False

    tentative_start = max(
        non_system_start,
        len(session.messages) - max(keep_recent_messages, 0),
    )
    keep_start = tentative_start

    # 原逻辑：往后扫第一个 user 消息作边界
    for idx in range(tentative_start, len(session.messages)):
        if session.messages[idx].get("role") == "user":
            keep_start = idx
            break
    else:
        if keep_start > non_system_start:
            for idx in range(keep_start - 1, non_system_start - 1, -1):
                if session.messages[idx].get("role") == "user":
                    keep_start = idx
                    break

    # 改进 2：回溯到不割裂 tool pair 的位置
    keep_start = _adjust_keep_start_for_tool_pairs(
        session.messages, keep_start, non_system_start,
    )

    if keep_start <= non_system_start:
        return False

    # 拆分压缩段：meta.skip_llm 条目（天使 skill 调用产生的「指令记录」）只用于 UI 展示，
    # 不进 LLM 上下文 / 不进 summary —— 压缩时拣出保留，正常对话条目才喂 LLM 生成 summary
    raw_archived = session.messages[non_system_start:keep_start]
    archived = [
        m for m in raw_archived
        if not (m.get("meta") or {}).get("skip_llm")
    ]
    preserved_skill_msgs = [
        m for m in raw_archived
        if (m.get("meta") or {}).get("skip_llm")
    ]
    if not archived:
        return False

    try:
        summary = await _build_memory_block(
            model=model,
            archived_messages=archived,
            existing_memories=session.session_memory,
            session_id=session.id,
        )
    except Exception as e:
        # 改进 4：熔断计数
        session.compression_failures = getattr(session, "compression_failures", 0) + 1
        logger.warning(
            "[时执·压缩] 记忆生成失败（第 {}/{} 次）：{}",
            session.compression_failures, MAX_CONSECUTIVE_COMPACT_FAILURES, e,
        )
        if session.compression_failures >= MAX_CONSECUTIVE_COMPACT_FAILURES:
            session.auto_compact_disabled = True
            logger.error(
                "[时执·压缩] 会话 {} 连续 {} 次压缩失败，熔断 auto-compact",
                session.id[:8], session.compression_failures,
            )
        return False

    # 成功路径：清零计数
    session.compression_failures = 0

    if summary not in session.session_memory:
        session.session_memory.append(summary)

    # 重组 messages：system + 保留下来的 skill 指令记录条目（UI 时序显示）+ keep 段
    # 指令记录被集中塞到压缩边界后，时序略有偏差但 UI 渲染按列表顺序、LLM 又看不到，可接受
    session.messages = (
        session.messages[:non_system_start]
        + preserved_skill_msgs
        + session.messages[keep_start:]
    )
    session.last_compressed_at = time.time()
    session.compressed_rounds += 1
    logger.info(
        "[时执·压缩] 会话 {} 上下文压缩完成，第 {} 轮",
        session.id[:8], session.compressed_rounds,
    )

    # L1 记忆经验提取：从 summary 里挑出"跨会话值得记住"的条目写入 memory_index
    # 失败不影响压缩主路径（已归档、已清 messages），仅记 warning
    if irminsul is not None:
        try:
            n = await extract_experience(
                session, model=model, irminsul=irminsul,
                archived_summary=summary,
            )
            if n > 0:
                logger.info(
                    "[时执·提取] 会话 {} 写入 {} 条跨会话记忆",
                    session.id[:8], n,
                )
        except Exception as e:
            logger.warning(
                "[时执·提取] 会话 {} 经验提取失败（压缩仍成功）: {}",
                session.id[:8], e,
            )

    return True

# 改进 3：Prompt 4 章节 + NO_TOOLS 约束
_COMPRESS_PROMPT = """你是会话记忆压缩器。严格约束：

1. **只输出纯文本**，不要调用任何工具，不要返回 JSON 或 markdown 代码块。
2. 输出必须按以下 4 段结构，段与段之间空一行分隔，段首保留中文方括号标题：
   【用户目标】—— 用户想达成什么，关键上下文、约束、偏好
   【关键决策与事实】—— 已经选定的方案、重要数据、API 返回的核心结论
   【当前待办 / 阻塞】—— 未完成的任务、等待的前置条件、卡住的地方
   【工具 / 文件状态】—— 已经操作过的文件路径、已执行的关键工具调用结果
3. 段内不使用列表符号，只用自然语句。
4. 必须**保留**用户原话里的关键词、数字、文件名、URL —— 后续对话仍可能引用。
5. 不是每段都要有内容。若某段确实为空，写"（无）"占位。
"""


async def _build_memory_block(
    *,
    model: "Model",
    archived_messages: list[dict],
    existing_memories: list[str],
    session_id: str = "",
) -> str:
    """把归档消息压缩成一段结构化记忆文本。

    搬自 Model._build_memory_block + Prompt 升级（改进 3）。
    失败时抛异常，由调用方 compress() 做熔断处理。
    """
    transcript = [
        {"role": msg.get("role", ""), "content": msg.get("content")}
        for msg in archived_messages
        if msg.get("content")
    ]
    memory_hints = [m for m in existing_memories[-4:] if m.strip()]

    user_payload = {
        "archived_messages": transcript,
        "existing_recent_memories": memory_hints,
    }

    messages = [
        {"role": "system", "content": _COMPRESS_PROMPT},
        {
            "role": "user",
            "content": json.dumps(user_payload, ensure_ascii=False, indent=2),
        },
    ]

    last_error = "unknown"
    for attempt in range(1, 4):
        try:
            raw, usage = await model._stream_text(messages, component="时执", purpose="上下文压缩")
        except Exception as e:
            last_error = f"模型调用失败: {e}"
            logger.warning(
                "[时执·压缩] 记忆生成第 {}/3 次尝试失败: {}",
                attempt, e,
            )
            # REL-013：retry 加指数 backoff（防 LLM 限流瞬时失败立即重试再失败）
            if attempt < 3:
                import asyncio as _asyncio
                await _asyncio.sleep(min(2 ** attempt, 10))
            continue

        summary = _strip_code_fence(raw)
        if not summary:
            last_error = "模型输出为空"
            logger.warning("[时执·压缩] 记忆生成第 {}/3 次结果为空", attempt)
            if attempt < 3:
                import asyncio as _asyncio
                await _asyncio.sleep(min(2 ** attempt, 10))
            continue
        await model._record_primogem(
            session_id, "时执", usage, purpose="上下文压缩",
        )
        return summary

    raise RuntimeError(f"记忆生成 3 次尝试均失败: {last_error}")


def _strip_code_fence(text: str) -> str:
    """剥 markdown 代码围栏（LLM 偶尔违反 Prompt 裹一层 ```）。"""
    s = text.strip()
    if not s.startswith("```"):
        return s
    lines = s.splitlines()
    if len(lines) >= 2 and lines[-1].strip() == "```":
        return "\n".join(lines[1:-1]).strip()
    return s
