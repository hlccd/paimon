"""水神 · Furina — 戏剧·评审

成品评审（方案/文档/代码/架构挑刺）。质量终审官。
专属工具：file_ops（只读，查看待审代码）。
"""
from __future__ import annotations

from loguru import logger

from paimon.archons.base import Archon
from paimon.foundation.irminsul import Irminsul
from paimon.foundation.irminsul.task import Subtask, TaskEdict
from paimon.llm.model import Model
from paimon.session import Session

_SYSTEM_PROMPT = """\
你是水神·芙宁娜，掌管戏剧与评审。你是质量终审官。

能力：
1. 严格评审方案/代码/文档/架构
2. 用 file_ops read 查看代码文件（只读，不修改）

规则：
1. 你的职责是审查和挑刺，不是生产内容
2. 指出问题要具体：位置、原因、改进建议
3. 评审结论分级：通过 / 有问题需修改 / 严重问题需重做
4. 不要客气，该挑刺就挑刺
5. 输出结构化评审报告
"""


class FurinaArchon(Archon):
    name = "水神"
    description = "评审、游戏信息"
    allowed_tools = {"file_ops"}

    async def execute(
        self, task: TaskEdict, subtask: Subtask, model: Model, irminsul: Irminsul,
        prior_results: list[str] | None = None,
    ) -> str:
        logger.info("[水神] 执行子任务: {}", subtask.description[:80])

        system = _SYSTEM_PROMPT
        system += f"\n\n## 当前任务\n{task.title}\n\n## 你的子任务\n{subtask.description}"
        if prior_results:
            system += "\n\n## 需要评审的内容\n"
            for i, pr in enumerate(prior_results, 1):
                system += f"\n### 子任务 {i} 产物\n{pr[:3000]}\n"

        temp_session = Session(id=f"furina-{task.id[:8]}", name="水神评审")
        temp_session.messages.append({"role": "system", "content": system})

        tools, executor = self._setup_tools(temp_session)
        async for _ in model.chat(
            temp_session, subtask.description,
            tools=tools, tool_executor=executor,
            component="水神", purpose="评审",
        ):
            pass

        result = self._extract_result(temp_session)
        await irminsul.progress_append(
            task_id=task.id, agent="水神", progress_pct=100,
            message=result[:200], subtask_id=subtask.id, actor="水神",
        )
        logger.info("[水神] 子任务完成, 结果长度={}", len(result))
        return result
