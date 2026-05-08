"""生执·simple_run — 纯 LLM tool-loop 的简单产物 stage。

stage = simple_code / exec / chat：不调 skill，直接 LLM tool-loop。
- simple_code：trivial 任务直接写代码到 workspace/code/ + 自检
- exec：跑 shell / 部署 / 重型工具（saga 补偿也用此 stage）
- chat：通用 LLM 推理 / 兜底

stage 归属：simple_code / exec / chat → 生执 simple_run（统一入口）
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from loguru import logger

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
    """三种简单 stage 的统一入口。stage ∈ {simple_code, exec, chat}。"""
    from paimon.session import Session

    cfg = SIMPLE_STAGES.get(stage) or SIMPLE_STAGES["chat"]
    system = cfg["prompt"]

    # simple_code 需要往 workspace/code/ 写产物
    if stage == "simple_code":
        from paimon.foundation.task_workspace import create_workspace
        workspace = create_workspace(task.id).resolve()
        code_dir = workspace / "code"
        code_dir.mkdir(parents=True, exist_ok=True)
        system += (
            f"\n\n## 当前任务\n{task.title}\n"
            f"\n## 你的子任务\n{subtask.description[:500]}\n"
            f"\n## 输出目录（必须）\n"
            f"代码必须用 file_ops write 写到 {code_dir}/\n"
            f"路径规则: {code_dir}/<相对路径> = 宿主项目对应文件\n"
            f"写完后用 exec 跑 py_compile/ruff/pytest 自检（错了继续修）\n"
        )
    else:
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

    result = extract_result(temp_session)

    # simple_code 路径跑同款 self_check
    if stage == "simple_code":
        from paimon.foundation.task_workspace import create_workspace, list_workspace_files
        from paimon.shades.jonova.self_check import run_self_check
        workspace = create_workspace(task.id).resolve()
        code_dir = workspace / "code"
        check_result = await run_self_check(workspace)
        files = [
            str(p.relative_to(code_dir))
            for p in list_workspace_files(workspace.name)
        ]
        ok = check_result.get("ok", False)
        return (
            f"code 已产出: {len(files)} 个文件到 {workspace}/code/\n"
            f"自检: {'✅ 全过' if ok else '⚠️ 未通过'} (详见 self-check.log)"
        )

    return result
