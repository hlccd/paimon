"""岩神 · Zhongli — 契约·财富

理财分析（红利股、资产管理、退休规划）。暂用 exec + curl，后续对接专属金融工具。
"""
from __future__ import annotations

from loguru import logger

from paimon.archons.base import Archon
from paimon.foundation.irminsul import Irminsul
from paimon.foundation.irminsul.task import Subtask, TaskEdict
from paimon.llm.model import Model
from paimon.session import Session

_SYSTEM_PROMPT = """\
你是岩神·摩拉克斯，掌管契约与财富。你的职责是理财分析。

能力：
1. 红利股分析、资产配置建议、退休规划
2. 用 exec 工具执行 curl 查询市场数据

规则：
1. 所有投资建议必须注明"仅供参考，不构成投资建议"
2. 数据要标明来源和时间
3. 输出结构化结果
4. 调用工具时不要输出过程描述，只输出最终结果
"""


class ZhongliArchon(Archon):
    name = "岩神"
    description = "理财、红利股、资产管理"
    allowed_tools = {"exec"}

    async def execute(
        self, task: TaskEdict, subtask: Subtask, model: Model, irminsul: Irminsul,
        prior_results: list[str] | None = None,
    ) -> str:
        logger.info("[岩神] 执行子任务: {}", subtask.description[:80])

        system = _SYSTEM_PROMPT
        system += f"\n\n## 当前任务\n{task.title}\n\n## 你的子任务\n{subtask.description}"
        if prior_results:
            system += "\n\n## 前序子任务结果\n"
            for i, pr in enumerate(prior_results, 1):
                system += f"\n### 子任务 {i}\n{pr[:2000]}\n"

        temp_session = Session(id=f"zhongli-{task.id[:8]}", name="岩神分析")
        temp_session.messages.append({"role": "system", "content": system})

        tools, executor = self._setup_tools(temp_session)
        async for _ in model.chat(
            temp_session, subtask.description,
            tools=tools, tool_executor=executor,
            component="岩神", purpose="理财分析",
        ):
            pass

        result = self._extract_result(temp_session)
        await irminsul.progress_append(
            task_id=task.id, agent="岩神", progress_pct=100,
            message=result[:200], subtask_id=subtask.id, actor="岩神",
        )
        logger.info("[岩神] 子任务完成, 结果长度={}", len(result))
        return result
