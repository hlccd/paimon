from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any, Iterable

from loguru import logger
from openai import AsyncOpenAI

from paimon.config import Config
from paimon.llm.base import Provider, StreamChunk, ToolCallFragment


class OpenAIProvider(Provider):
    def __init__(self, cfg: Config):
        self.client = AsyncOpenAI(api_key=cfg.api_key, base_url=cfg.api_base_url)
        self.model = cfg.model
        self.model_name = cfg.model

    @classmethod
    def from_params(
        cls, *, api_key: str, base_url: str, model: str,
    ) -> OpenAIProvider:
        instance = object.__new__(cls)
        instance.client = AsyncOpenAI(api_key=api_key, base_url=base_url)
        instance.model = model
        instance.model_name = model
        return instance

    async def chat_stream(
        self,
        messages: Iterable[Any],
        tools: list[dict[str, Any]] | None = None,
    ) -> AsyncIterator[StreamChunk]:
        msgs = list(messages)
        logger.info("[神之心] 调用LLM，消息数={}", len(msgs))
        kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": msgs,
            "stream": True,
            "stream_options": {"include_usage": True},
        }
        if tools:
            kwargs["tools"] = tools

        resp = await self.client.chat.completions.create(**kwargs)
        async for chunk in resp:
            if hasattr(chunk, "usage") and chunk.usage is not None:
                input_tokens = getattr(chunk.usage, "prompt_tokens", 0) or 0
                output_tokens = getattr(chunk.usage, "completion_tokens", 0) or 0
                cache_read = 0
                details = getattr(chunk.usage, "prompt_tokens_details", None)
                if details:
                    cache_read = getattr(details, "cached_tokens", 0) or 0
                yield StreamChunk(usage={
                    "input_tokens": input_tokens,
                    "output_tokens": output_tokens,
                    "cache_creation_tokens": 0,
                    "cache_read_tokens": cache_read,
                })
                continue

            if not chunk.choices:
                continue
            delta = chunk.choices[0].delta
            tcs = None
            if delta.tool_calls:
                tcs = []
                for tc in delta.tool_calls:
                    tcs.append(
                        ToolCallFragment(
                            index=tc.index,
                            id=tc.id or "",
                            name=(
                                tc.function.name
                                if tc.function and tc.function.name
                                else ""
                            ),
                            arguments=(
                                tc.function.arguments
                                if tc.function and tc.function.arguments
                                else ""
                            ),
                        )
                    )
            yield StreamChunk(
                content=delta.content or "",
                reasoning_content=getattr(delta, "reasoning_content", "") or "",
                tool_calls=tcs,
            )
