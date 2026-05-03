from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any, Iterable

from loguru import logger

from paimon.config import Config
from paimon.llm.base import Provider, StreamChunk, ToolCallFragment


class AnthropicProvider(Provider):
    def __init__(self, cfg: Config):
        from anthropic import AsyncAnthropic

        # REL-012/013：限制 timeout + 降低 max_retries
        # 旧: max_retries=10 + 默认 timeout 600s → 单次失败可阻塞 chat-loop 半小时
        # 新: timeout 120s（read）+ max_retries=2，配合调用方层面 backoff 处理临时故障
        kwargs: dict[str, Any] = {
            "api_key": cfg.api_key,
            "max_retries": 2,
            "timeout": 120.0,
        }
        if cfg.api_base_url:
            kwargs["base_url"] = cfg.api_base_url

        self.client = AsyncAnthropic(**kwargs)
        self.model = cfg.model
        self.model_name = cfg.model
        self.max_tokens = cfg.max_tokens

    @classmethod
    def from_params(
        cls, *, api_key: str, base_url: str, model: str, max_tokens: int,
    ) -> AnthropicProvider:
        from anthropic import AsyncAnthropic

        instance = object.__new__(cls)
        kwargs: dict[str, Any] = {
            "api_key": api_key, "max_retries": 2, "timeout": 120.0,
        }
        if base_url:
            kwargs["base_url"] = base_url
        instance.client = AsyncAnthropic(**kwargs)
        instance.model = model
        instance.model_name = model
        instance.max_tokens = max_tokens
        return instance

    @staticmethod
    def _convert_tools(
        openai_tools: list[dict[str, Any]] | None,
    ) -> list[dict[str, Any]] | None:
        if not openai_tools:
            return None
        return [
            {
                "name": t["function"]["name"],
                "description": t["function"].get("description", ""),
                "input_schema": t["function"].get(
                    "parameters", {"type": "object", "properties": {}}
                ),
            }
            for t in openai_tools
        ]

    @staticmethod
    def _convert_messages(messages: Iterable[Any]) -> tuple[str, list[dict[str, Any]]]:
        system_parts: list[str] = []
        result: list[dict[str, Any]] = []

        for msg in messages:
            role = msg["role"]
            content = msg.get("content")

            if role == "system":
                system_parts.append(str(content))

            elif role == "user":
                result.append({"role": "user", "content": content or ""})

            elif role == "assistant":
                tool_calls = msg.get("tool_calls")
                if tool_calls:
                    blocks: list[dict[str, Any]] = []
                    if content:
                        blocks.append({"type": "text", "text": content})
                    for tc in tool_calls:
                        # REL-016：tool args 可能是上一轮 OpenAI 输出的残缺 JSON，
                        # 切换到 Anthropic 时直接 json.loads 会让整 tool-loop 崩
                        try:
                            tc_input = json.loads(
                                tc["function"]["arguments"] or "{}"
                            )
                        except (json.JSONDecodeError, ValueError) as e:
                            logger.warning(
                                "[神之心·anthropic] tool_use 参数 JSON 解析失败 "
                                "tool={} err={} → 用空 dict 占位",
                                tc["function"].get("name"), e,
                            )
                            tc_input = {}
                        blocks.append(
                            {
                                "type": "tool_use",
                                "id": tc["id"],
                                "name": tc["function"]["name"],
                                "input": tc_input,
                            }
                        )
                    result.append({"role": "assistant", "content": blocks})
                else:
                    result.append({"role": "assistant", "content": content or ""})

            elif role == "tool":
                block: dict[str, Any] = {
                    "type": "tool_result",
                    "tool_use_id": msg["tool_call_id"],
                    "content": str(content) if content else "",
                }
                if result and result[-1]["role"] == "user":
                    prev = result[-1]["content"]
                    if isinstance(prev, str):
                        result[-1]["content"] = [{"type": "text", "text": prev}, block]
                    else:
                        prev.append(block)
                else:
                    result.append({"role": "user", "content": [block]})

        return "\n".join(system_parts).strip(), result

    async def chat_stream(
        self,
        messages: Iterable[Any],
        tools: list[dict[str, Any]] | None = None,
    ) -> AsyncIterator[StreamChunk]:
        system, anthropic_messages = self._convert_messages(messages)
        anthropic_tools = self._convert_tools(tools)

        logger.debug("[神之心] 调用LLM，消息数={}", len(anthropic_messages))

        kwargs: dict[str, Any] = {
            "model": self.model,
            "max_tokens": self.max_tokens,
            "messages": anthropic_messages,
        }
        if system:
            kwargs["system"] = system
        if anthropic_tools:
            kwargs["tools"] = anthropic_tools

        from anthropic import APIStatusError

        try:
            async with self.client.messages.stream(**kwargs) as stream:
                async for event in stream:
                    event_type = getattr(event, "type", None)

                    if event_type == "content_block_start":
                        block = getattr(event, "content_block", None)
                        if block and getattr(block, "type", None) == "tool_use":
                            yield StreamChunk(
                                tool_calls=[
                                    ToolCallFragment(
                                        index=getattr(event, "index", 0),
                                        id=getattr(block, "id", ""),
                                        name=getattr(block, "name", ""),
                                    )
                                ]
                            )

                    elif event_type == "content_block_delta":
                        delta = getattr(event, "delta", None)
                        if delta is None:
                            continue
                        delta_type = getattr(delta, "type", None)
                        if delta_type == "text_delta":
                            yield StreamChunk(content=getattr(delta, "text", ""))
                        elif delta_type == "input_json_delta":
                            yield StreamChunk(
                                tool_calls=[
                                    ToolCallFragment(
                                        index=getattr(event, "index", 0),
                                        arguments=getattr(delta, "partial_json", ""),
                                    )
                                ]
                            )

                try:
                    final = await stream.get_final_message()
                    usage = final.usage
                    input_tokens = getattr(usage, "input_tokens", 0) or 0
                    output_tokens = getattr(usage, "output_tokens", 0) or 0
                    cache_creation = getattr(usage, "cache_creation_input_tokens", 0) or 0
                    cache_read = getattr(usage, "cache_read_input_tokens", 0) or 0
                    if input_tokens > 0 or output_tokens > 0:
                        cache_info = ""
                        if cache_creation or cache_read:
                            cache_info = f" 缓存写入={cache_creation} 缓存命中={cache_read}"
                        logger.debug(
                            "[神之心] token用量: 输入={} 输出={}{}",
                            input_tokens, output_tokens, cache_info,
                        )
                    yield StreamChunk(usage={
                        "input_tokens": input_tokens,
                        "output_tokens": output_tokens,
                        "cache_creation_tokens": cache_creation,
                        "cache_read_tokens": cache_read,
                    })
                except Exception as e:
                    logger.debug("[神之心] 获取最终消息失败: {}", e)
                    yield StreamChunk(usage={
                        "input_tokens": 0,
                        "output_tokens": 0,
                        "cache_creation_tokens": 0,
                        "cache_read_tokens": 0,
                    })
        except Exception as e:
            if isinstance(e, APIStatusError) and e.status_code == 529:
                logger.warning("[神之心] API过载(529)")
                raise RuntimeError("服务集群负载较高，请稍后重试") from e
            else:
                logger.error("[神之心] 流式调用异常: {}", e)
                raise
