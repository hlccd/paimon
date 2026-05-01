"""冰神 · Tsaritsa — 反抗·联合

Skill 生态管理：发现 + 注册世界树 + 评估。
专属工具：skill_manage（扫描/列表/查看）、exec（补充）。
"""
from __future__ import annotations

from loguru import logger

from paimon.archons.base import Archon
from paimon.foundation.irminsul import Irminsul
from paimon.foundation.irminsul.task import Subtask, TaskEdict
from paimon.llm.model import Model
from paimon.session import Session

_SYSTEM_PROMPT = """\
你是冰神·冰之女皇，掌管反抗与联合。你的职责是 Skill 生态管理。

能力：
1. 用 skill_manage 工具扫描、查看、评估已有 skill
2. 用 exec 工具查看 skill 文件内容
3. 规划新 skill 的设计方案

规则：
1. 当前项目路径是 {project_root}，skills 在 skills/ 目录下
2. 每个 skill 由 SKILL.md 定义（YAML frontmatter + Markdown body）
3. 优先用 skill_manage 工具获取 skill 信息
4. 调用工具时不要输出过程描述，只输出最终结果
"""


class TsaritsaArchon(Archon):
    name = "冰神"
    description = "Skill 生态管理、AI 自举"
    allowed_tools = {"skill_manage", "exec"}

    async def execute(
        self, task: TaskEdict, subtask: Subtask, model: Model, irminsul: Irminsul,
        prior_results: list[str] | None = None,
    ) -> str:
        logger.info("[冰神] 执行子任务: {}", subtask.description[:80])

        from paimon.archons.base import FINAL_OUTPUT_RULE
        system = _SYSTEM_PROMPT.format(project_root=self._project_root())
        system += f"\n\n## 当前任务\n{task.title}\n\n## 你的子任务\n{subtask.description}"
        if prior_results:
            system += "\n\n## 前序子任务结果\n"
            for i, pr in enumerate(prior_results, 1):
                system += f"\n### 子任务 {i}\n{pr[:2000]}\n"
        system += await self._load_feedback_memories_block(irminsul)
        system += FINAL_OUTPUT_RULE

        temp_session = Session(id=f"tsaritsa-{task.id[:8]}", name="冰神管理")
        temp_session.messages.append({"role": "system", "content": system})

        tools, executor = self._setup_tools(temp_session)
        async for _ in model.chat(
            temp_session, subtask.description,
            tools=tools, tool_executor=executor,
            component="冰神", purpose="Skill 汇总",
        ):
            pass

        result = self._extract_result(temp_session)
        await irminsul.progress_append(
            task_id=task.id, agent="冰神", progress_pct=100,
            message=result[:200], subtask_id=subtask.id, actor="冰神",
        )
        logger.info("[冰神] 子任务完成, 结果长度={}", len(result))
        return result
