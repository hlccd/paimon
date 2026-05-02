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
    from paimon.foundation.model_router import ModelRouter

class Model:
    def __init__(
        self, provider: Provider,
        gnosis: Gnosis | None = None,
        router: "ModelRouter | None" = None,
    ):
        self.provider = provider          # .env 启动路径的兜底 provider
        self.gnosis = gnosis
        self.router = router              # M2：按 (component, purpose) 路由到 profile
        self.last_chat_cost_usd: float = 0.0
        # 上一次 chat 实际用的 model_name / 路由来源（聊天气泡尾巴展示用）
        # —— 按 _pick_provider(component, purpose) 的实际返回记录，不是默认 profile
        self.last_chat_model_name: str = ""
        self.last_chat_provider_source: str = ""

    async def _pick_provider(
        self, component: str, purpose: str,
    ) -> tuple[Provider, str]:
        """按路由选 provider；返回 (provider, source_tag) 供日志 / 故障上报用。

        优先级：router 精确命中 > 默认 profile > self.provider（.env 启动值）
        source_tag: "profile:{id}" / "default" / "env"
        路由命中同时写入 router._hits 供面板展示（命中记录不为 default/env
        path 查 profile_id，只记 model_name + source，节省 DB 查询）。
        """
        if self.router and self.gnosis:
            pid = self.router.resolve(component, purpose)
            if pid:
                prov = await self.gnosis.get_provider_by_profile_id(pid)
                if prov:
                    self.router.record_hit(
                        component, purpose,
                        profile_id=pid, model_name=prov.model_name,
                        provider_source=f"profile:{pid}",
                    )
                    return prov, f"profile:{pid}"
        if self.gnosis:
            default = await self.gnosis.get_default_provider()
            if default is not None:
                if self.router:
                    self.router.record_hit(
                        component, purpose,
                        profile_id="", model_name=default.model_name,
                        provider_source="default",
                    )
                return default, "default"
        if self.router:
            self.router.record_hit(
                component, purpose,
                profile_id="", model_name=self.provider.model_name,
                provider_source="env",
            )
        return self.provider, "env"

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
        self, messages: list[dict[str, Any]],
        *,
        component: str = "",
        purpose: str = "",
    ) -> tuple[str, dict[str, int]]:
        """提供 component/purpose 即走 router；不提供则用 self.provider（兜底兼容）。

        四影 / istaroth / intent / venti 等调用点应传入它们在 primogem.record
        里记的同一对值，以确保路由一致性。
        """
        if component or purpose:
            provider, _src = await self._pick_provider(component, purpose)
        else:
            provider = self.provider
        text = ""
        usage = self._empty_usage()
        async for chunk in provider.chat_stream(messages):
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

    @staticmethod
    def _normalize_reasoning_passthrough(messages: list[dict[str, Any]]) -> None:
        """DeepSeek thinking 硬约束：带 tool_calls 的 assistant 消息必须带
        reasoning_content（可空），否则 400。

        场景：用户在非 thinking provider（如 Claude）聊天触发过 tool 调用，
        session.messages 留下了没 reasoning_content 的 assistant 消息，之后
        切到 DeepSeek thinking 模式就炸。规范化补空串即可——OpenAI / Claude
        对未知/空字段都容忍，只有 DeepSeek 强制此字段存在。
        """
        for msg in messages:
            if (msg.get("role") == "assistant"
                    and "reasoning_content" not in msg):
                msg["reasoning_content"] = ""

    def _build_runtime_messages(self, session: Session) -> list[dict[str, Any]]:
        msgs = list(session.messages)
        self._normalize_reasoning_passthrough(msgs)
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
        """对外入口 → _chat_loop.chat_impl；行为详见该文件 docstring。"""
        from ._chat_loop import chat_impl
        async for txt in chat_impl(
            self, session, user_input,
            tools=tools, tool_executor=tool_executor,
            component=component, purpose=purpose,
        ):
            yield txt


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
            title, usage = await self._stream_text(msgs, component="title", purpose="标题生成")
            await self._record_primogem(session_id, "title", usage, purpose="标题生成")
            return title.strip().strip('"').strip("'")
        except Exception as e:
            logger.error("[神之心·模型] 标题生成失败: {}", e)
            return ""
