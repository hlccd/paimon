"""火神 · Mavuika — 战争·冲锋

Shell/代码执行、部署。只在用户明确要求"执行/部署/运行"时出场。
专属工具：exec。
"""
from __future__ import annotations

from loguru import logger

from paimon.archons.base import Archon
from paimon.foundation.irminsul import Irminsul
from paimon.foundation.irminsul.task import Subtask, TaskEdict
from paimon.llm.model import Model
from paimon.session import Session

_SYSTEM_PROMPT = """\
你是火神·玛薇卡，掌管战争与冲锋。你的职责是执行和部署。

规则：
1. 当前项目路径是 {project_root}
2. 你是执行者——拿到指令就执行
3. 执行前确认命令安全性，拒绝明显危险的操作
4. 执行后报告结果：成功/失败 + 输出摘要
5. 如果执行失败，尝试诊断原因并重试（最多 2 次）
6. 调用工具时不要输出过程描述，只输出最终结果
"""


class MavuikaArchon(Archon):
    name = "火神"
    description = "Shell/代码执行、部署、技术重试"
    allowed_tools = {"exec"}

    async def execute(
        self, task: TaskEdict, subtask: Subtask, model: Model, irminsul: Irminsul,
        prior_results: list[str] | None = None,
    ) -> str:
        logger.info("[火神] 执行子任务: {}", subtask.description[:80])

        from paimon.archons.base import FINAL_OUTPUT_RULE
        system = _SYSTEM_PROMPT.format(project_root=self._project_root())
        system += f"\n\n## 当前任务\n{task.title}\n\n## 你的子任务\n{subtask.description}"
        if prior_results:
            system += "\n\n## 前序子任务结果\n"
            for i, pr in enumerate(prior_results, 1):
                system += f"\n### 子任务 {i}\n{pr[:2000]}\n"
        system += await self._load_feedback_memories_block(irminsul)
        system += FINAL_OUTPUT_RULE

        temp_session = Session(id=f"mavuika-{task.id[:8]}", name="火神执行")
        temp_session.messages.append({"role": "system", "content": system})

        tools, executor = self._setup_tools(temp_session)
        async for _ in model.chat(
            temp_session, subtask.description,
            tools=tools, tool_executor=executor,
            component="火神", purpose="执行部署",
        ):
            pass

        result = self._extract_result(temp_session)
        await irminsul.progress_append(
            task_id=task.id, agent="火神", progress_pct=100,
            message=result[:200], subtask_id=subtask.id, actor="火神",
        )
        logger.info("[火神] 子任务完成, 结果长度={}", len(result))
        return result
