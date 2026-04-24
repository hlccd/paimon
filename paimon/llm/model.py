from __future__ import annotations

import json
import time
from collections.abc import AsyncIterator
from typing import TYPE_CHECKING, Any

from loguru import logger

from paimon.llm.base import Provider
from paimon.session import Session

if TYPE_CHECKING:
    from paimon.foundation.gnosis import Gnosis

from paimon.llm.base import ToolCallFragment


class _ToolCallAccumulator:
    def __init__(self):
        self._calls: dict[int, dict[str, str]] = {}

    def update(self, frag: ToolCallFragment) -> None:
        idx = frag.index
        if idx not in self._calls:
            self._calls[idx] = {"id": "", "name": "", "arguments": ""}
        if frag.id:
            self._calls[idx]["id"] = frag.id
        if frag.name:
            self._calls[idx]["name"] = frag.name
        if frag.arguments:
            self._calls[idx]["arguments"] += frag.arguments

    def get_tool_calls(self) -> list[dict]:
        if not self._calls:
            return []
        return [
            {
                "id": v["id"],
                "type": "function",
                "function": {"name": v["name"], "arguments": v["arguments"]},
            }
            for _, v in sorted(self._calls.items())
            if v["name"]
        ]


class Model:
    def __init__(self, provider: Provider, gnosis: Gnosis | None = None):
        self.provider = provider
        self.gnosis = gnosis
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
    def _empty_usage() -> dict[str, int]:
        return {
            "input_tokens": 0,
            "output_tokens": 0,
            "cache_creation_tokens": 0,
            "cache_read_tokens": 0,
        }

    @staticmethod
    def _merge_usage(target: dict[str, int], source: dict[str, Any]) -> None:
        for key in ("input_tokens", "output_tokens", "cache_creation_tokens", "cache_read_tokens"):
            target[key] = target.get(key, 0) + (source.get(key, 0) or 0)

    async def _stream_text(
        self, messages: list[dict[str, Any]]
    ) -> tuple[str, dict[str, int]]:
        text = ""
        usage = self._empty_usage()
        async for chunk in self.provider.chat_stream(messages):
            if chunk.usage:
                self._merge_usage(usage, chunk.usage)
                continue
            if chunk.content:
                text += chunk.content
        if usage["input_tokens"] == 0 and usage["output_tokens"] == 0:
            usage["input_tokens"] = self.estimate_messages_tokens(messages)
            usage["output_tokens"] = max(1, (len(text) + 3) // 4)
        return text, usage

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

    @staticmethod
    def _sanitize_session_messages(messages: list[dict[str, Any]]) -> None:
        while messages:
            last = messages[-1]
            if last.get("role") == "tool":
                messages.pop()
            elif last.get("role") == "assistant" and last.get("tool_calls"):
                messages.pop()
            else:
                break

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

    async def chat(
        self,
        session: Session,
        user_input: str,
        tools: list[dict] | None = None,
        tool_executor: Any = None,
        component: str = "chat",
        purpose: str = "闲聊",
    ) -> AsyncIterator[str]:
        self.last_chat_cost_usd = 0.0
        total_usage = self._empty_usage()
        self._sanitize_session_messages(session.messages)
        session.messages.append({"role": "user", "content": user_input})

        max_rounds = 15
        for round_idx in range(max_rounds):
            runtime_messages = self._build_runtime_messages(session)
            text_buf = ""
            usage = self._empty_usage()
            tc_acc = _ToolCallAccumulator()

            active_provider = self.provider
            try:
                stream_iter = active_provider.chat_stream(runtime_messages, tools=tools)
            except Exception as e:
                if self.gnosis:
                    self.gnosis.report_failure(active_provider.model_name)
                    fallback = self.gnosis.get_provider("shallow")
                    if fallback is not active_provider:
                        logger.warning("[神之心·故障切换] chat 切换到备用 provider")
                        active_provider = fallback
                        try:
                            stream_iter = active_provider.chat_stream(runtime_messages, tools=tools)
                        except Exception as e2:
                            logger.error("[神之心·模型] 备用也失败: {}", e2)
                            if round_idx == 0:
                                session.messages.pop()
                            yield f"\n\n> [错误] {e2}"
                            return
                    else:
                        logger.error("[神之心·模型] 流式初始化失败: {}", e)
                        if round_idx == 0:
                            session.messages.pop()
                        yield f"\n\n> [错误] {e}"
                        return
                else:
                    logger.error("[神之心·模型] 流式初始化失败: {}", e)
                    if round_idx == 0:
                        session.messages.pop()
                    yield f"\n\n> [错误] {e}"
                    return

            # 推理 token 流聚合：LLM 思考过程是运行时重要信号（INFO 级），
            # 但按 token 逐片打日志会刷屏 → 累积到"切产出 / 流结束"时一次性 flush。
            # 超长（>800 字）只留首尾，中间省略（多为重复推理步骤）。
            reasoning_buf = ""

            def _flush_reasoning():
                nonlocal reasoning_buf
                if not reasoning_buf:
                    return
                n = len(reasoning_buf)
                if n > 800:
                    shown = (
                        reasoning_buf[:400].rstrip()
                        + f"\n... [省略中间 {n - 600} 字] ...\n"
                        + reasoning_buf[-200:].lstrip()
                    )
                else:
                    shown = reasoning_buf
                logger.info("[神之心·模型] 推理 ({} 字):\n{}", n, shown)
                reasoning_buf = ""

            try:
                async for chunk in stream_iter:
                    if chunk.usage:
                        self._merge_usage(usage, chunk.usage)
                        continue
                    if chunk.reasoning_content:
                        reasoning_buf += chunk.reasoning_content
                    # 切到产出阶段（tool_call 或 content）→ flush 先前推理
                    if chunk.tool_calls or chunk.content:
                        _flush_reasoning()
                    if chunk.tool_calls:
                        for frag in chunk.tool_calls:
                            tc_acc.update(frag)
                    if chunk.content:
                        text_buf += chunk.content
                        yield chunk.content
                # 流正常结束后可能还有未 flush 的推理（没 content / tool_call 的情况）
                _flush_reasoning()
            except Exception as e:
                _flush_reasoning()  # 异常也不要丢推理日志
                logger.error("[神之心·模型] 流式传输异常: {}", e)
                if text_buf:
                    session.messages.append({"role": "assistant", "content": text_buf})
                elif round_idx == 0:
                    session.messages.pop()
                yield f"\n\n> [错误] {e}"
                return

            if self.gnosis:
                self.gnosis.report_success(active_provider.model_name)
            self._merge_usage(total_usage, usage)

            tool_calls = tc_acc.get_tool_calls()

            if not tool_calls:
                session.messages.append({"role": "assistant", "content": text_buf})
                break

            assistant_msg: dict[str, Any] = {"role": "assistant", "tool_calls": tool_calls}
            if text_buf:
                assistant_msg["content"] = text_buf
            session.messages.append(assistant_msg)

            if not tool_executor:
                logger.warning("[神之心·模型] 有 tool_calls 但无 executor")
                break

            for tc in tool_calls:
                fn = tc["function"]
                tc_id = tc["id"]
                logger.debug("[天使·工具调用] {}({})", fn["name"], fn["arguments"][:100])
                try:
                    result = await tool_executor(fn["name"], fn["arguments"])
                except Exception as e:
                    # 魔女会信号：让 AngelFailure 穿过 tool-call 异常兜底，
                    # 由 run_session_chat 接住并转交四影。
                    from paimon.angels.nicole import AngelFailure
                    if isinstance(e, AngelFailure):
                        raise
                    result = f"工具执行错误: {e}"
                    logger.error("[天使·工具调用] {} 失败: {}", fn["name"], e)
                session.messages.append({
                    "role": "tool",
                    "tool_call_id": tc_id,
                    "content": str(result),
                })
                logger.debug("[天使·工具结果] {} -> {}字符", fn["name"], len(str(result)))

        if total_usage["input_tokens"] == 0 and total_usage["output_tokens"] == 0:
            runtime_messages = self._build_runtime_messages(session)
            total_usage["input_tokens"] = self.estimate_messages_tokens(runtime_messages)
            total_usage["output_tokens"] = max(1, (len(text_buf) + 3) // 4)

        total = total_usage["input_tokens"] + total_usage["output_tokens"]
        cost = await self._compute_and_record(session.id, component, total_usage, purpose=purpose)
        self.last_chat_cost_usd = cost
        cache_info = ""
        cw, cr = total_usage["cache_creation_tokens"], total_usage["cache_read_tokens"]
        if cw or cr:
            cache_info = f" 缓存写入={cw} 缓存命中={cr}"
        logger.info(
            "[神之心·模型] token统计: 输入={} 输出={} 总计={}{} 模型={}",
            total_usage["input_tokens"], total_usage["output_tokens"], total,
            cache_info, active_provider.model_name,
        )

    async def _compute_and_record(
        self,
        session_id: str,
        component: str,
        usage: dict[str, int],
        purpose: str = "",
    ) -> float:
        from paimon.state import state
        from paimon.foundation.primogem import Primogem

        cost = Primogem.compute_cost(
            self.provider.model_name,
            usage["input_tokens"],
            usage["output_tokens"],
            usage.get("cache_creation_tokens", 0),
            usage.get("cache_read_tokens", 0),
        )
        primogem = state.primogem
        if primogem:
            await primogem.record(
                session_id=session_id,
                component=component,
                model_name=self.provider.model_name,
                input_tokens=usage["input_tokens"],
                output_tokens=usage["output_tokens"],
                cost_usd=cost,
                cache_creation_tokens=usage.get("cache_creation_tokens", 0),
                cache_read_tokens=usage.get("cache_read_tokens", 0),
                purpose=purpose,
            )
        return cost

    async def _record_primogem(
        self,
        session_id: str,
        component: str,
        usage: dict[str, int],
        purpose: str = "",
    ) -> None:
        await self._compute_and_record(session_id, component, usage, purpose=purpose)

    async def generate_title(self, user_input: str, session_id: str = "") -> str:
        prompt = (
            "请根据以下用户输入，总结一个 3 到 5 个词的简短标题。"
            "你的回答必须只有标题，不要有任何其他修饰语或标点符号。\n\n"
            f"用户输入: {user_input}"
        )
        msgs = [{"role": "user", "content": prompt}]
        try:
            title, usage = await self._stream_text(msgs)
            await self._record_primogem(session_id, "title", usage, purpose="标题生成")
            return title.strip().strip('"').strip("'")
        except Exception as e:
            logger.error("[神之心·模型] 标题生成失败: {}", e)
            return ""
