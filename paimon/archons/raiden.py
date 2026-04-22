"""雷神 · Raiden — 永恒·造物

写代码（含自检）。专属工具：file_ops（结构化文件读写）、exec（跑测试/lint）。
"""
from __future__ import annotations

from loguru import logger

from paimon.archons.base import Archon
from paimon.foundation.irminsul import Irminsul
from paimon.foundation.irminsul.task import Subtask, TaskEdict
from paimon.llm.model import Model
from paimon.session import Session

_SYSTEM_PROMPT = """\
你是雷神·巴尔泽布，掌管永恒与造物。你的职责是写代码。

能力：
1. 用 file_ops 工具读写文件（read/write/list/exists）
2. 用 exec 工具运行测试、lint 验证代码
3. 写完代码后必须自检

规则：
1. 当前项目路径是 {project_root}
2. 用 file_ops write 写文件，不要用 exec echo
3. 写完后用 exec 跑测试或检查语法
4. 输出结构化结果：文件路径 + 代码要点 + 自检结论
5. 调用工具时不要输出过程描述，只输出最终结果
"""


class RaidenArchon(Archon):
    name = "雷神"
    description = "代码生成、自检"
    allowed_tools = {"file_ops", "exec"}

    async def execute(
        self, task: TaskEdict, subtask: Subtask, model: Model, irminsul: Irminsul,
        prior_results: list[str] | None = None,
    ) -> str:
        logger.info("[雷神] 执行子任务: {}", subtask.description[:80])

        system = _SYSTEM_PROMPT.format(project_root=self._project_root())
        system += f"\n\n## 当前任务\n{task.title}\n\n## 你的子任务\n{subtask.description}"
        if prior_results:
            system += "\n\n## 前序子任务结果\n"
            for i, pr in enumerate(prior_results, 1):
                system += f"\n### 子任务 {i}\n{pr[:2000]}\n"

        temp_session = Session(id=f"raiden-{task.id[:8]}", name="雷神执行")
        temp_session.messages.append({"role": "system", "content": system})

        tools, executor = self._setup_tools(temp_session)
        async for _ in model.chat(
            temp_session, subtask.description,
            tools=tools, tool_executor=executor,
            component="雷神", purpose="代码生成",
        ):
            pass

        result = self._extract_result(temp_session)
        await irminsul.progress_append(
            task_id=task.id, agent="雷神", progress_pct=100,
            message=result[:200], subtask_id=subtask.id, actor="雷神",
        )
        logger.info("[雷神] 子任务完成, 结果长度={}", len(result))
        return result
