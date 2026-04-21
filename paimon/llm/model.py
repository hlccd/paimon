from __future__ import annotations

import json
import time
from collections.abc import AsyncIterator
from typing import Any

from loguru import logger

from paimon.llm.base import Provider
from paimon.session import Session


class Model:
    def __init__(self, provider: Provider):
        self.provider = provider
        self.last_chat_cost_usd: float = 0.0

    @staticmethod
    def _estimate_obj_tokens(obj: Any) -> int:
        if obj is None:
            return 0
        text = obj if isinstance(obj, str) else json.dumps(obj, ensure_ascii=False)
        if not text:
            return 0
        return max(1, (len(text) + 3) // 4)

    @classmethod
    def estimate_messages_tokens(cls, messages: list[dict]) -> int:
        total = 0
        for msg in messages:
            total += 4
            total += cls._estimate_obj_tokens(msg.get("role", ""))
            total += cls._estimate_obj_tokens(msg.get("content", ""))
            if "tool_calls" in msg:
                total += cls._estimate_obj_tokens(msg.get("tool_calls"))
            if "tool_call_id" in msg:
                total += cls._estimate_obj_tokens(msg.get("tool_call_id"))
        return total + 2

    @staticmethod
    def _strip_code_fence(text: str) -> str:
        s = text.strip()
        if not s.startswith("```"):
            return s
        lines = s.splitlines()
        if len(lines) >= 2 and lines[-1].strip() == "```":
            return "\n".join(lines[1:-1]).strip()
        return s

    async def _stream_text(self, messages: list[dict[str, Any]]) -> str:
        text = ""
        async for chunk in self.provider.chat_stream(messages):
            if chunk.content:
                text += chunk.content
        return text

    def _build_memory_prompt(
        self,
        session: Session,
        max_blocks: int = 3,
    ) -> str:
        memories = [m.strip() for m in session.session_memory if m.strip()]
        if not memories:
            return ""

        selected = memories[-max_blocks:]
        parts = [
            "[会话记忆]",
            "以下是历史会话压缩记忆，请把它作为当前会话的长期上下文。",
        ]
        for idx, memory in enumerate(selected, start=1):
            parts.append(f"{idx}. {memory}")

        return "\n".join(parts)

    def _build_runtime_messages(self, session: Session) -> list[dict[str, Any]]:
        msgs = list(session.messages)
        memory_prompt = self._build_memory_prompt(session)
        if not memory_prompt:
            return msgs

        memory_msg: dict[str, Any] = {"role": "system", "content": memory_prompt}
        if msgs and msgs[0].get("role") == "system":
            return [msgs[0], memory_msg, *msgs[1:]]
        return [memory_msg, *msgs]

    def update_session_context_stats(
        self,
        session: Session,
        context_window_tokens: int,
    ) -> tuple[int, float]:
        runtime_messages = self._build_runtime_messages(session)
        total = self.estimate_messages_tokens(runtime_messages)
        ratio = 0.0
        if context_window_tokens > 0:
            ratio = (total / context_window_tokens) * 100
        session.last_context_tokens = total
        session.last_context_ratio = ratio
        return total, ratio

    async def compress_session_context(
        self,
        session: Session,
        keep_recent_messages: int,
    ) -> bool:
        if not session.messages:
            return False

        non_system_start = 1 if session.messages[0].get("role") == "system" else 0
        non_system_count = len(session.messages) - non_system_start
        if non_system_count <= max(keep_recent_messages, 0):
            return False

        tentative_start = max(non_system_start, len(session.messages) - max(keep_recent_messages, 0))
        keep_start = tentative_start

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

        if keep_start <= non_system_start:
            return False

        archived = session.messages[non_system_start:keep_start]
        if not archived:
            return False

        summary = await self._build_memory_block(
            archived,
            existing_memories=session.session_memory,
        )
        if summary not in session.session_memory:
            session.session_memory.append(summary)

        session.messages = session.messages[:non_system_start] + session.messages[keep_start:]
        session.last_compressed_at = time.time()
        session.compressed_rounds += 1
        logger.info("[派蒙·压缩] 上下文压缩完成，第{}轮", session.compressed_rounds)
        return True

    async def _build_memory_block(
        self,
        archived_messages: list[dict],
        existing_memories: list[str],
    ) -> str:
        transcript = [
            {"role": msg.get("role", ""), "content": msg.get("content")}
            for msg in archived_messages
            if msg.get("content")
        ]
        memory_hints = [m for m in existing_memories[-4:] if m.strip()]

        prompt = (
            "你是会话记忆压缩器。请基于给定对话片段输出一段中文记忆文本。"
            "这不是泛化总结，必须保留后续对话必需信息。"
            "重点例如：目标、关键事实、约束、已决策事项、待办、关键工具结论。"
            "输出要求：只输出一段纯文本，不要分点，不要 JSON，不要 markdown 代码块。"
        )

        user_payload = {
            "archived_messages": transcript,
            "existing_recent_memories": memory_hints,
        }

        messages = [
            {"role": "system", "content": prompt},
            {
                "role": "user",
                "content": json.dumps(user_payload, ensure_ascii=False, indent=2),
            },
        ]

        last_error = "unknown"
        for attempt in range(1, 4):
            try:
                raw = await self._stream_text(messages)
            except Exception as e:
                last_error = f"模型调用失败: {e}"
                logger.warning(
                    "[派蒙·压缩] 记忆生成第{}/3次尝试失败: {}",
                    attempt, e,
                )
                continue

            summary = self._strip_code_fence(raw)
            if not summary:
                last_error = "模型输出为空"
                logger.warning("[派蒙·压缩] 记忆生成第{}/3次结果为空", attempt)
                continue
            return summary

        raise RuntimeError(f"记忆生成3次尝试均失败: {last_error}")

    async def chat(
        self,
        session: Session,
        user_input: str,
    ) -> AsyncIterator[str]:
        self.last_chat_cost_usd = 0.0
        session.messages.append({"role": "user", "content": user_input})
        runtime_messages = self._build_runtime_messages(session)

        text_buf = ""
        round_input_tokens = 0
        round_output_tokens = 0

        try:
            stream_iter = self.provider.chat_stream(runtime_messages)
        except Exception as e:
            logger.error("[神之心·模型] 流式初始化失败: {}", e)
            session.messages.pop()
            yield f"\n\n> [错误] {e}"
            return

        try:
            async for chunk in stream_iter:
                if chunk.usage:
                    round_input_tokens += chunk.usage.get("input_tokens", 0)
                    round_output_tokens += chunk.usage.get("output_tokens", 0)
                    continue

                if chunk.reasoning_content:
                    logger.trace("[神之心·模型] 推理: {}", chunk.reasoning_content[:100])

                if chunk.content:
                    text_buf += chunk.content
                    yield chunk.content
        except Exception as e:
            logger.error("[神之心·模型] 流式传输异常: {}", e)
            if text_buf:
                session.messages.append({"role": "assistant", "content": text_buf})
            else:
                session.messages.pop()
            yield f"\n\n> [错误] {e}"
            return

        session.messages.append({"role": "assistant", "content": text_buf})

        if round_input_tokens == 0 and round_output_tokens == 0:
            round_input_tokens = self.estimate_messages_tokens(runtime_messages)
            round_output_tokens = max(1, (len(text_buf) + 3) // 4)

        total = round_input_tokens + round_output_tokens
        cost = round_input_tokens * 0.000003 + round_output_tokens * 0.000015
        self.last_chat_cost_usd = cost
        logger.info(
            "[神之心·模型] token统计: 输入={} 输出={} 总计={} 模型={}",
            round_input_tokens, round_output_tokens, total, self.provider.model_name,
        )

    async def generate_title(self, user_input: str) -> str:
        prompt = (
            "请根据以下用户输入，总结一个 3 到 5 个词的简短标题。"
            "你的回答必须只有标题，不要有任何其他修饰语或标点符号。\n\n"
            f"用户输入: {user_input}"
        )
        msgs = [{"role": "user", "content": prompt}]
        try:
            title = await self._stream_text(msgs)
            return title.strip().strip('"').strip("'")
        except Exception as e:
            logger.error("[神之心·模型] 标题生成失败: {}", e)
            return ""
