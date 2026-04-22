"""七神基类 — 所有 Archon 的公共接口和工具过滤"""
from __future__ import annotations

import abc
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from paimon.foundation.irminsul import Irminsul
    from paimon.foundation.irminsul.task import Subtask, TaskEdict
    from paimon.llm.model import Model
    from paimon.session import Session


class Archon(abc.ABC):
    name: str = ""
    description: str = ""
    allowed_tools: set[str] = set()

    @abc.abstractmethod
    async def execute(
        self,
        task: TaskEdict,
        subtask: Subtask,
        model: Model,
        irminsul: Irminsul,
        prior_results: list[str] | None = None,
    ) -> str:
        """执行子任务，返回结果文本。"""

    def _setup_tools(self, session: Session):
        from paimon.state import state
        if not state.tool_registry:
            return None, None

        from paimon.tools.base import ToolContext
        all_tools = state.tool_registry.to_openai_tools()
        if self.allowed_tools:
            tools = [t for t in all_tools if t["function"]["name"] in self.allowed_tools]
        else:
            tools = all_tools

        ctx = ToolContext(registry=state.tool_registry, channel=None, chat_id="", session=session)

        async def _executor(name: str, arguments: str) -> str:
            return await state.tool_registry.execute(name, arguments, ctx)

        return tools or None, _executor

    @staticmethod
    def _extract_result(session: Session) -> str:
        for msg in reversed(session.messages):
            if msg.get("role") == "assistant" and msg.get("content") and not msg.get("tool_calls"):
                return msg["content"]
        return ""

    @staticmethod
    def _project_root() -> str:
        from pathlib import Path
        return str(Path(__file__).resolve().parent.parent.parent)
