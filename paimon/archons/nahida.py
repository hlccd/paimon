"""草神 · Nahida — 智慧·文书

推理、知识整合、文书起草。当前唯一可用 Archon。
"""
from __future__ import annotations

from loguru import logger

from paimon.archons.base import Archon
from paimon.foundation.irminsul import Irminsul
from paimon.foundation.irminsul.task import Subtask, TaskEdict
from paimon.llm.model import Model
from paimon.session import Session

_SYSTEM_PROMPT = """\
你是草神·纳西妲，掌管智慧与知识。

重要规则：
1. 当前项目路径是 {project_root}，不要去互联网上找项目
2. 调用工具时不要输出任何文字，直接调用
3. 所有工具调用完成后，输出完整的结构化结果
4. 你的输出是最终交付给用户的内容，不是工作日志
"""


class NahidaArchon(Archon):
    name = "草神"
    description = "推理、知识整合、文书起草"

    async def execute(
        self,
        task: TaskEdict,
        subtask: Subtask,
        model: Model,
        irminsul: Irminsul,
        prior_results: list[str] | None = None,
    ) -> str:
        logger.info("[草神] 执行子任务: {}", subtask.description[:80])

        from pathlib import Path
        project_root = Path(__file__).resolve().parent.parent.parent

        system = _SYSTEM_PROMPT.format(project_root=project_root)
        system += f"\n\n## 当前任务\n{task.title}\n\n## 你的子任务\n{subtask.description}"

        if prior_results:
            system += "\n\n## 前序子任务的结果（供参考）\n"
            for i, pr in enumerate(prior_results, 1):
                system += f"\n### 子任务 {i} 结果\n{pr[:2000]}\n"

        temp_session = Session(id=f"nahida-{task.id[:8]}", name="草神执行")
        temp_session.messages.append({"role": "system", "content": system})

        from paimon.state import state
        tools = None
        tool_executor = None
        if state.tool_registry:
            tools = state.tool_registry.to_openai_tools()
            from paimon.tools.base import ToolContext
            tool_ctx = ToolContext(
                registry=state.tool_registry,
                channel=None,
                chat_id="",
                session=temp_session,
            )

            async def _exec(name: str, arguments: str) -> str:
                return await state.tool_registry.execute(name, arguments, tool_ctx)

            tool_executor = _exec

        async for chunk in model.chat(
            temp_session,
            subtask.description,
            tools=tools,
            tool_executor=tool_executor,
            component="草神",
            purpose="推理执行",
        ):
            pass

        result = ""
        for msg in reversed(temp_session.messages):
            if msg.get("role") == "assistant" and msg.get("content") and not msg.get("tool_calls"):
                result = msg["content"]
                break

        await irminsul.progress_append(
            task_id=task.id,
            agent="草神",
            progress_pct=100,
            message=result[:200],
            subtask_id=subtask.id,
            actor="草神",
        )

        logger.info("[草神] 子任务完成, 结果长度={}", len(result))
        return result
