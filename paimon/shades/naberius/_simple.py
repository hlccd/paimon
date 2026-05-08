"""生执·simple_run — 纯 LLM tool-loop 的简单产物 stage。

stage = exec / chat：不调 skill，直接 LLM tool-loop。
- exec：跑 shell / 部署 / 重型工具（saga 补偿也用此 stage）
- chat：通用 LLM 推理 / 兜底（管线异常 / 未知 stage 也回退到此）

stage 归属：exec / chat → 生执 simple_run（统一入口）

历史：v8 之前还有 simple_code（trivial 写代码任务），自进化定位后写代码完全废弃。
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from paimon.shades._helpers.runner_helpers import (
    extract_result,
    load_feedback_memories_block,
    setup_tools,
)
from paimon.shades._helpers.stages import FINAL_OUTPUT_RULE, SIMPLE_STAGES

if TYPE_CHECKING:
    from paimon.foundation.irminsul import Irminsul
    from paimon.foundation.irminsul.task import Subtask, TaskEdict
    from paimon.llm.model import Model


async def simple_run(
    stage: str,
    task: "TaskEdict",
    subtask: "Subtask",
    model: "Model",
    irminsul: "Irminsul",
    prior_results: list[str] | None,
) -> str:
    """两种简单 stage 的统一入口。stage ∈ {exec, chat}。未知 stage 回退 chat。"""
    from paimon.session import Session

    cfg = SIMPLE_STAGES.get(stage) or SIMPLE_STAGES["chat"]
    system = cfg["prompt"]

    system += f"\n\n## 当前任务\n{task.title}\n\n## 你的子任务\n{subtask.description}"

    if prior_results:
        system += "\n\n## 前序子任务结果\n"
        for i, pr in enumerate(prior_results, 1):
            system += f"\n### 子任务 {i}\n{pr[:2000]}\n"
    system += await load_feedback_memories_block(irminsul)
    system += FINAL_OUTPUT_RULE

    temp_session = Session(
        id=f"shades-{stage}-{task.id[:8]}", name=cfg["display_name"],
    )
    temp_session.messages.append({"role": "system", "content": system})

    tools, executor = setup_tools(temp_session, allowed_tools=cfg["allowed_tools"])
    async for _ in model.chat(
        temp_session, subtask.description,
        tools=tools, tool_executor=executor,
        component="生执", purpose=cfg["purpose"],
    ):
        pass

    return extract_result(temp_session)
