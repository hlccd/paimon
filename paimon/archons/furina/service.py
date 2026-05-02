"""水神 · Furina — 戏剧·评审

成品评审（方案/文档/代码/架构挑刺）。质量终审官。
专属工具：file_ops（只读）、use_skill（调 check skill 做严格审查）。

四影管线 review 阶段入口：
- `review_spec()` — 调 check skill 审 spec.md（spec 模式）
- `review_design()` — 调 check 对齐 spec ↔ design
- `review_code()` — 调 check 对齐 design ↔ code

按产物体量分档：小产物走**轻量 review**（一次 LLM 调用，不跑 check skill）；
大产物走**check skill 严格审查**（原路径）。阈值由 _LIGHT_REVIEW_* 常量控制。
"""
from __future__ import annotations

import json
from pathlib import Path

from loguru import logger

from paimon.archons.base import Archon
from paimon.foundation.irminsul import Irminsul
from paimon.foundation.irminsul.task import Subtask, TaskEdict
from paimon.llm.model import Model
from paimon.session import Session


# 轻量 review 阈值 / 测量 helper / _LIGHT_REVIEW_SYSTEM prompt 全部移到 _review.py
# （只 _review.py 用得到，service.py 现仅保留 _SYSTEM_PROMPT 给 execute()）


_SYSTEM_PROMPT = """\
你是水神·芙宁娜，掌管戏剧与评审。你是质量终审官。

能力：
1. 严格评审方案/代码/文档/架构
2. 用 file_ops read 查看代码文件（只读，不修改）

评审规则：
1. 你的职责是审查和挑刺，不是生产内容
2. 指出问题要具体：位置、原因、改进建议
3. 不要客气，该挑刺就挑刺

**输出格式（硬性要求）**：
先简要说明评审过程（可选，≤200 字），然后在最后输出一个 JSON 对象作为终审结论。
JSON 必须严格按以下字段：

```json
{
  "level": "pass | revise | redo",
  "issues": [
    {"subtask_id": "xxx", "reason": "具体问题", "suggestion": "改进建议"}
  ],
  "summary": "总体评价（一句话）"
}
```

- level=pass: 没有明显问题，可以交付
- level=revise: 有问题但方向正确，局部修改即可（在 issues 里列出具体 subtask）
- level=redo: 严重问题/方向错误，需要整体重做
- issues 为空数组时仍需保留字段
- subtask_id 从"需要评审的内容"段落里对应节点的 id 提取；若无法归因到具体节点，留空字符串

只允许输出一段正文 + 一个 JSON 代码块；禁止多个 JSON。
"""


from ._review import _ReviewMixin


class FurinaArchon(_ReviewMixin, Archon):
    """水神·芙宁娜：评审 archon，按 stage 分派 review_spec/design/code（_ReviewMixin）。"""

    name = "水神"
    description = "评审、游戏信息"
    allowed_tools = {"file_ops"}

    async def execute(
        self, task: TaskEdict, subtask: Subtask, model: Model, irminsul: Irminsul,
        prior_results: list[str] | None = None,
    ) -> str:
        logger.info("[水神] 执行子任务: {}", subtask.description[:80])

        # 四影管线 review 阶段分派（调 check skill）
        desc = subtask.description
        if desc.startswith(("[STAGE:review_spec]", "[STAGE:review_design]", "[STAGE:review_code]")):
            from paimon.foundation.task_workspace import get_workspace_path, create_workspace
            import json as _json
            workspace = create_workspace(task.id)
            spec_path = workspace / "spec.md"
            design_path = workspace / "design.md"
            code_dir = workspace / "code"

            # subtask_id 应指向被审的"生产节点"（deps[0]）而不是 review 节点自己，
            # 这样 issues 反映"生产节点 X 被挑出问题"，pipeline 回炉时 _plan_revise
            # 才能正确定位要重派的生产节点。
            reviewed_id = (subtask.deps or [None])[0] if subtask.deps else subtask.id

            if desc.startswith("[STAGE:review_spec]"):
                verdict = await self.review_spec(
                    spec_path=spec_path, workspace=workspace, model=model,
                    subtask_id=reviewed_id,
                )
            elif desc.startswith("[STAGE:review_design]"):
                verdict = await self.review_design(
                    spec_path=spec_path, design_path=design_path,
                    workspace=workspace, model=model, subtask_id=reviewed_id,
                )
            else:  # review_code
                verdict = await self.review_code(
                    design_path=design_path, code_dir=code_dir,
                    workspace=workspace, model=model, subtask_id=reviewed_id,
                    # simple/trivial DAG 无 design 阶段，传 task.description 作 prior 基准
                    fallback_requirement=task.description,
                )

            # 产物：文本 + 末尾 JSON（pipeline 的 _resolve_verdict 按 find_last_verdict_producer 解析）
            verdict_obj = {
                "level": verdict.level,
                "issues": verdict.issues,
                "summary": verdict.summary,
            }
            result = (
                f"{verdict.summary}\n\n"
                f"```json\n{_json.dumps(verdict_obj, ensure_ascii=False, indent=2)}\n```"
            )
            await irminsul.progress_append(
                task_id=task.id, agent="水神", progress_pct=100,
                message=verdict.summary[:200], subtask_id=subtask.id, actor="水神",
            )
            return result

        from paimon.archons.base import FINAL_OUTPUT_RULE
        system = _SYSTEM_PROMPT
        system += f"\n\n## 当前任务\n{task.title}\n\n## 你的子任务\n{subtask.description}"
        if prior_results:
            system += "\n\n## 需要评审的内容\n"
            for i, pr in enumerate(prior_results, 1):
                system += f"\n### 子任务 {i} 产物\n{pr[:3000]}\n"
        system += await self._load_feedback_memories_block(irminsul)
        system += FINAL_OUTPUT_RULE

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
