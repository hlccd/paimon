from __future__ import annotations

import abc
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any, Iterable


@dataclass
class ToolCallFragment:
    index: int
    id: str = ""
    name: str = ""
    arguments: str = ""


@dataclass
class StreamChunk:
    content: str = ""
    reasoning_content: str = ""
    tool_calls: list[ToolCallFragment] | None = None
    usage: dict | None = None


class Provider(abc.ABC):
    model_name: str = ""

    @abc.abstractmethod
    def __init__(self, **kwargs: Any):
        pass

    @abc.abstractmethod
    def chat_stream(
        self,
        messages: Iterable[Any],
        tools: list[dict[str, Any]] | None = None,
    ) -> AsyncIterator[StreamChunk]:
        pass
