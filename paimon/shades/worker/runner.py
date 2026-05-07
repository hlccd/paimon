"""run_stage 主入口：按 stage tag 路由到具体处理函数。

这是 asmoday.dispatch 调用的唯一接口；替代原 archon.execute 的角色。
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from loguru import logger

from . import _review
from ._revise_helpers import (
    extract_issues_from_description,
    extract_prior_issues,
    fmt_issue_yaml,
)
from ._runner_helpers import (
    extract_result,
    invoke_skill_workflow,
    load_feedback_memories_block,
    project_root_repr,
    setup_tools,
)
from ._self_check import run_self_check
from ._stages import (
    ALL_STAGES,
    FINAL_OUTPUT_RULE,
    REVIEW_STAGES,
    SIMPLE_STAGES,
    SKILL_STAGES,
    get_display_name,
)

if TYPE_CHECKING:
    from paimon.foundation.irminsul import Irminsul
    from paimon.foundation.irminsul.task import Subtask, TaskEdict
    from paimon.llm.model import Model


async def run_stage(
    stage: str,
    task: "TaskEdict",
    subtask: "Subtask",
    model: "Model",
    irminsul: "Irminsul",
    prior_results: list[str] | None = None,
) -> str:
    """按 stage 路由到具体工人处理函数；返结果文本（asmoday 写 subtask.result）。"""
    if stage not in ALL_STAGES:
        logger.warning("[工人·{}] 未知 stage，回退 chat", stage)
        stage = "chat"

    display = get_display_name(stage)
    logger.info("[{}] 执行子任务: {}", display, subtask.description[:80])

    # 路由
    if stage in SKILL_STAGES:
        result = await _run_skill_stage(stage, task, subtask, model, irminsul, prior_results)
    elif stage in REVIEW_STAGES:
        result = await _run_review_stage(stage, task, subtask, model, irminsul, prior_results)
    elif stage in SIMPLE_STAGES:
        result = await _run_simple_stage(stage, task, subtask, model, irminsul, prior_results)
    else:
        # 已 fallback 到 chat 但兜底仍走 simple
        result = await _run_simple_stage("chat", task, subtask, model, irminsul, prior_results)

    # 进度落盘（统一）
    try:
        await irminsul.progress_append(
            task_id=task.id, agent=display, progress_pct=100,
            message=(result or "")[:200], subtask_id=subtask.id, actor=display,
        )
    except Exception as e:
        logger.debug("[{}] progress_append 失败: {}", display, e)

    logger.info("[{}] 子任务完成, 结果长度={}", display, len(result or ""))
    return result or ""


# ─────────────────────────────────────────────────────────────────────────────
# Skill 驱动 stage：spec / design / code
# ─────────────────────────────────────────────────────────────────────────────

async def _run_skill_stage(
    stage: str,
    task: "TaskEdict",
    subtask: "Subtask",
    model: "Model",
    irminsul: "Irminsul",
    prior_results: list[str] | None,
) -> str:
    """spec / design / code stage：调对应 skill 产出文件。"""
    cfg = SKILL_STAGES[stage]
    from paimon.foundation.task_workspace import create_workspace
    workspace = create_workspace(task.id).resolve()

    # revise 路径优先用 description 内嵌 issues
    prior_issues = (
        extract_issues_from_description(subtask.description)
        or extract_prior_issues(prior_results)
    )

    if stage == "spec":
        return await _do_spec(task, workspace, model, prior_issues, cfg)
    if stage == "design":
        return await _do_design(task, workspace, model, prior_issues, cfg)
    if stage == "code":
        return await _do_code(task, subtask, workspace, model, irminsul, prior_results, prior_issues, cfg)
    return f"[stage={stage}] 未实现"


async def _do_spec(task, workspace, model, prior_issues, cfg) -> str:
    spec_path = workspace / "spec.md"
    requirement = f"{task.title}\n{task.description}"

    user_parts = [
        "调用 requirement-spec skill，按它的规范产出 spec.md。\n",
        "```yaml",
        f"requirement: |\n  {requirement.replace(chr(10), chr(10) + '  ')}",
        f"workspace: {workspace}/",
    ]
    if prior_issues:
        user_parts.append("prior_issues:")
        for it in prior_issues[:20]:
            user_parts.append(fmt_issue_yaml(it))
    user_parts.append("```")
    user_msg = "\n".join(user_parts)

    await invoke_skill_workflow(
        skill_name=cfg["skill"],
        user_message=user_msg,
        model=model,
        session_name=workspace.name,
        component="工人",
        purpose=cfg["purpose"],
        allowed_tools=cfg["allowed_tools"],
        framing=(
            f"【四影管线·spec 阶段】workspace={workspace}/\n"
            f"产物必须写到: {spec_path}\n"
            "只用 file_ops 工具（read/write）；不要 exec。"
        ),
    )

    if not spec_path.exists():
        logger.warning("[工人·spec] LLM 未产出 spec.md，写兜底占位")
        spec_path.write_text(
            f"# spec\n\n## 背景\n需求：{(task.title or '')[:200]}\n\n"
            "（LLM 未产出完整 spec，此为兜底占位）\n",
            encoding="utf-8",
        )
    size_kb = spec_path.stat().st_size / 1024 if spec_path.exists() else 0
    return f"spec 已产出: {spec_path}（{size_kb:.1f} KB）"


async def _do_design(task, workspace, model, prior_issues, cfg) -> str:
    spec_path = workspace / "spec.md"
    design_path = workspace / "design.md"

    user_parts = [
        "调用 architecture-design skill，按它的规范产出 design.md。\n",
        "```yaml",
        f"spec_path: {spec_path}",
        f"workspace: {workspace}/",
        f"project_root: {project_root_repr()}/",
    ]
    if prior_issues:
        user_parts.append("prior_issues:")
        for it in prior_issues[:20]:
            user_parts.append(fmt_issue_yaml(it))
    user_parts.append("```")
    user_msg = "\n".join(user_parts)

    await invoke_skill_workflow(
        skill_name=cfg["skill"],
        user_message=user_msg,
        model=model,
        session_name=workspace.name,
        component="工人",
        purpose=cfg["purpose"],
        allowed_tools=cfg["allowed_tools"],
        framing=(
            f"【四影管线·design 阶段】\n产物写到: {design_path}\n"
            f"读 spec: {spec_path}\n"
            f"project_root: {project_root_repr()}/（只读参考，不要写）"
        ),
    )

    if not design_path.exists():
        logger.warning("[工人·design] LLM 未产出 design.md，写兜底占位")
        design_path.write_text(
            "# 技术方案\n\n（LLM 未产出 design.md，此为兜底占位）\n",
            encoding="utf-8",
        )
    size_kb = design_path.stat().st_size / 1024 if design_path.exists() else 0
    return f"design 已产出: {design_path}（{size_kb:.1f} KB）"


async def _do_code(task, subtask, workspace, model, irminsul, prior_results, prior_issues, cfg) -> str:
    spec_path = workspace / "spec.md"
    design_path = workspace / "design.md"
    code_dir = workspace / "code"
    code_dir.mkdir(parents=True, exist_ok=True)

    # spec/design 都有 → complex DAG，调 skill workflow
    # 否则走 simple_code stage（不调 skill 直接 LLM）
    if spec_path.exists() and design_path.exists():
        user_parts = [
            "调用 code-implementation skill，按它的规范产出代码到 workspace/code/。\n",
            "```yaml",
            f"spec_path: {spec_path}",
            f"design_path: {design_path}",
            f"workspace: {workspace}/",
            f"project_root: {project_root_repr()}/",
        ]
        if prior_issues:
            user_parts.append("prior_issues:")
            for it in prior_issues[:20]:
                user_parts.append(fmt_issue_yaml(it))
        user_parts.append("```")
        user_msg = "\n".join(user_parts)

        await invoke_skill_workflow(
            skill_name=cfg["skill"],
            user_message=user_msg,
            model=model,
            session_name=workspace.name,
            component="工人",
            purpose=cfg["purpose"],
            allowed_tools=cfg["allowed_tools"],
            framing=(
                f"【四影管线·code 阶段】\n产物写到: {code_dir}/\n"
                f"路径规则: workspace/code/{{相对路径}} = 宿主项目对应文件路径\n"
                f"读参考: {project_root_repr()}/\n"
                "写完后必须自检三件套（py_compile/ruff/pytest），失败继续修。"
            ),
        )

        # 工人侧兜底再跑一次自检（确保 self-check.log 存在）
        check_result = await run_self_check(workspace)

        from paimon.foundation.task_workspace import list_workspace_files
        files = [
            str(p.relative_to(code_dir))
            for p in list_workspace_files(workspace.name)
        ]
        ok = check_result.get("ok", False)
        return (
            f"code 已产出: {len(files)} 个文件到 {workspace}/code/\n"
            f"自检: {'✅ 全过' if ok else '⚠️ 未通过'} (详见 self-check.log)"
        )

    # spec/design 缺 → simple/trivial 路径，走 simple_code stage 兜底
    logger.info(
        "[工人·code] simple/trivial 路径（spec/design 不存在），走 simple_code stage 兜底",
    )
    return await _run_simple_stage(
        "simple_code", task, subtask, model, irminsul, prior_results,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Review stage：review_spec / review_design / review_code
# ─────────────────────────────────────────────────────────────────────────────

async def _run_review_stage(
    stage: str,
    task: "TaskEdict",
    subtask: "Subtask",
    model: "Model",
    irminsul: "Irminsul",
    prior_results: list[str] | None,
) -> str:
    """review_* stage：调 _review.py 内的 light/check skill 双路径。

    返回 result 文本（含 verdict JSON 让 pipeline _resolve_verdict 解析）。
    """
    from paimon.foundation.task_workspace import create_workspace
    workspace = create_workspace(task.id).resolve()
    spec_path = workspace / "spec.md"
    design_path = workspace / "design.md"
    code_dir = workspace / "code"

    if stage == "review_spec":
        verdict = await _review.run_review_spec(
            spec_path=spec_path, workspace=workspace, model=model,
            subtask_id=subtask.id,
        )
    elif stage == "review_design":
        verdict = await _review.run_review_design(
            spec_path=spec_path, design_path=design_path, workspace=workspace,
            model=model, subtask_id=subtask.id,
        )
    elif stage == "review_code":
        # simple/trivial 无 design 时，用 task.description 作 fallback_requirement
        fallback = "" if design_path.is_file() else (task.description or "")
        verdict = await _review.run_review_code(
            design_path=design_path, code_dir=code_dir, workspace=workspace,
            model=model, subtask_id=subtask.id,
            fallback_requirement=fallback,
        )
    else:
        return f"[review·{stage}] 未实现"

    # 把 ReviewVerdict 序列化到 result 文本（pipeline _resolve_verdict 读 JSON）
    import json
    verdict_dict = {
        "level": verdict.level,
        "issues": verdict.issues,
        "summary": verdict.summary,
    }
    return f"{verdict.summary}\n\n```json\n{json.dumps(verdict_dict, ensure_ascii=False, indent=2)}\n```"


# ─────────────────────────────────────────────────────────────────────────────
# 纯 LLM tool-loop stage：simple_code / exec / chat
# ─────────────────────────────────────────────────────────────────────────────

async def _run_simple_stage(
    stage: str,
    task: "TaskEdict",
    subtask: "Subtask",
    model: "Model",
    irminsul: "Irminsul",
    prior_results: list[str] | None,
) -> str:
    """simple_code / exec / chat stage：纯 LLM tool-loop（不调 skill）。"""
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
        id=f"worker-{stage}-{task.id[:8]}", name=cfg["display_name"],
    )
    temp_session.messages.append({"role": "system", "content": system})

    tools, executor = setup_tools(temp_session, allowed_tools=cfg["allowed_tools"])
    async for _ in model.chat(
        temp_session, subtask.description,
        tools=tools, tool_executor=executor,
        component="工人", purpose=cfg["purpose"],
    ):
        pass

    result = extract_result(temp_session)

    # simple_code 路径跑同款 self_check
    if stage == "simple_code":
        from paimon.foundation.task_workspace import create_workspace, list_workspace_files
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
