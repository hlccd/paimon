"""草神 · Nahida — 智慧·文书

推理、知识整合、文书起草、偏好管理。
专属工具：knowledge（知识库）、memory（记忆）、exec（通用）。
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

能力：
1. 深度推理和分析
2. 通过 knowledge 工具读写知识库（按 category/topic 组织的结构化知识）
3. 通过 memory 工具管理跨会话记忆（用户偏好、项目事实、行为反馈等）
4. 通过 exec 执行命令获取信息

规则：
1. 当前项目路径是 {project_root}
2. 需要持久化的知识用 knowledge 工具写入，不要用 exec 写文件
3. 需要记住的用户偏好/反馈用 memory 工具写入
4. **写入 memory 前先用 memory list / search 看看已有记录，避免重复或覆盖**
5. 调用工具时不要输出过程描述，只输出最终结果
"""


class NahidaArchon(Archon):
    name = "草神"
    description = "推理、知识整合、文书起草"
    allowed_tools = {"knowledge", "memory", "exec"}

    async def execute(
        self, task: TaskEdict, subtask: Subtask, model: Model, irminsul: Irminsul,
        prior_results: list[str] | None = None,
    ) -> str:
        logger.info("[草神] 执行子任务: {}", subtask.description[:80])

        system = _SYSTEM_PROMPT.format(project_root=self._project_root())
        system += f"\n\n## 当前任务\n{task.title}\n\n## 你的子任务\n{subtask.description}"
        if prior_results:
            system += "\n\n## 前序子任务结果\n"
            for i, pr in enumerate(prior_results, 1):
                system += f"\n### 子任务 {i}\n{pr[:2000]}\n"

        temp_session = Session(id=f"nahida-{task.id[:8]}", name="草神执行")
        temp_session.messages.append({"role": "system", "content": system})

        tools, executor = self._setup_tools(temp_session)
        async for _ in model.chat(
            temp_session, subtask.description,
            tools=tools, tool_executor=executor,
            component="草神", purpose="推理执行",
        ):
            pass

        result = self._extract_result(temp_session)
        await irminsul.progress_append(
            task_id=task.id, agent="草神", progress_pct=100,
            message=result[:200], subtask_id=subtask.id, actor="草神",
        )
        logger.info("[草神] 子任务完成, 结果长度={}", len(result))
        return result
