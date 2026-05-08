"""生执·produce — 产出工程产物（spec / design / code 三段式）。

调对应 skill（requirement-spec / architecture-design / code-implementation）产 spec.md /
design.md / workspace/code/。produce_code 内部跑一次自检（py_compile/ruff/pytest）确保
self-check.log 存在；死执 review_code 时再独立判定。

revise 路径：通过 `prior_issues` 参数把上轮评审 issues 注入 user_message YAML 块。

stage 归属：spec / design / code → 生执 produce_*
"""
from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from loguru import logger

from paimon.shades._helpers.runner_helpers import (
    invoke_skill_workflow,
    project_root_repr,
)
from paimon.shades._helpers.revise_helpers import fmt_issue_yaml
from paimon.shades._helpers.stages import SKILL_STAGES

if TYPE_CHECKING:
    from paimon.foundation.irminsul import Irminsul
    from paimon.foundation.irminsul.task import Subtask, TaskEdict
    from paimon.llm.model import Model


async def produce_spec(
    task: "TaskEdict",
    subtask: "Subtask",
    model: "Model",
    irminsul: "Irminsul",
    prior_results: list[str] | None,
) -> str:
    """spec stage：调 requirement-spec skill 产 spec.md。"""
    from paimon.foundation.task_workspace import create_workspace
    workspace = create_workspace(task.id).resolve()
    spec_path = workspace / "spec.md"

    prior_issues = _extract_prior_issues(subtask, prior_results)
    cfg = SKILL_STAGES["spec"]
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
        component="生执",
        purpose=cfg["purpose"],
        allowed_tools=cfg["allowed_tools"],
        framing=(
            f"【四影管线·spec 阶段】workspace={workspace}/\n"
            f"产物必须写到: {spec_path}\n"
            "只用 file_ops 工具（read/write）；不要 exec。"
        ),
    )

    if not spec_path.exists():
        logger.warning("[生执·spec] LLM 未产出 spec.md，写兜底占位")
        spec_path.write_text(
            f"# spec\n\n## 背景\n需求：{(task.title or '')[:200]}\n\n"
            "（LLM 未产出完整 spec，此为兜底占位）\n",
            encoding="utf-8",
        )
    size_kb = spec_path.stat().st_size / 1024 if spec_path.exists() else 0
    return f"spec 已产出: {spec_path}（{size_kb:.1f} KB）"


async def produce_design(
    task: "TaskEdict",
    subtask: "Subtask",
    model: "Model",
    irminsul: "Irminsul",
    prior_results: list[str] | None,
) -> str:
    """design stage：调 architecture-design skill 产 design.md（基于 spec.md）。"""
    from paimon.foundation.task_workspace import create_workspace
    workspace = create_workspace(task.id).resolve()
    spec_path = workspace / "spec.md"
    design_path = workspace / "design.md"

    prior_issues = _extract_prior_issues(subtask, prior_results)
    cfg = SKILL_STAGES["design"]

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
        component="生执",
        purpose=cfg["purpose"],
        allowed_tools=cfg["allowed_tools"],
        framing=(
            f"【四影管线·design 阶段】\n产物写到: {design_path}\n"
            f"读 spec: {spec_path}\n"
            f"project_root: {project_root_repr()}/（只读参考，不要写）"
        ),
    )

    if not design_path.exists():
        logger.warning("[生执·design] LLM 未产出 design.md，写兜底占位")
        design_path.write_text(
            "# 技术方案\n\n（LLM 未产出 design.md，此为兜底占位）\n",
            encoding="utf-8",
        )
    size_kb = design_path.stat().st_size / 1024 if design_path.exists() else 0
    return f"design 已产出: {design_path}（{size_kb:.1f} KB）"


async def produce_code(
    task: "TaskEdict",
    subtask: "Subtask",
    model: "Model",
    irminsul: "Irminsul",
    prior_results: list[str] | None,
) -> str:
    """code stage：调 code-implementation skill 产代码到 workspace/code/ + 自检。

    spec/design 缺失时降级走 simple_run stage 兜底。
    """
    from paimon.foundation.task_workspace import create_workspace, list_workspace_files
    workspace = create_workspace(task.id).resolve()
    spec_path = workspace / "spec.md"
    design_path = workspace / "design.md"
    code_dir = workspace / "code"
    code_dir.mkdir(parents=True, exist_ok=True)

    # spec/design 都有 → complex DAG 路径，调 skill workflow
    # 否则降级 simple_run（trivial / simple DAG）
    if not (spec_path.exists() and design_path.exists()):
        from ._simple import simple_run
        logger.info("[生执·code] spec/design 缺失，降级 simple_run")
        return await simple_run("simple_code", task, subtask, model, irminsul, prior_results)

    prior_issues = _extract_prior_issues(subtask, prior_results)
    cfg = SKILL_STAGES["code"]

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
        component="生执",
        purpose=cfg["purpose"],
        allowed_tools=cfg["allowed_tools"],
        framing=(
            f"【四影管线·code 阶段】\n产物写到: {code_dir}/\n"
            f"路径规则: workspace/code/{{相对路径}} = 宿主项目对应文件路径\n"
            f"读参考: {project_root_repr()}/\n"
            "写完后必须自检三件套（py_compile/ruff/pytest），失败继续修。"
        ),
    )

    # 生执侧兜底再跑一次自检（确保 self-check.log 存在；死执 review_code 时再独立判定）
    from paimon.shades.jonova.self_check import run_self_check
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


# ─────────────────────────────────────────────────────────────────────────────
# 内部 helper
# ─────────────────────────────────────────────────────────────────────────────

def _extract_prior_issues(subtask, prior_results: list[str] | None) -> list[dict]:
    """revise 路径优先用 description 内嵌 issues，否则从 prior_results 抽。"""
    from paimon.shades._helpers.revise_helpers import (
        extract_issues_from_description, extract_prior_issues,
    )
    return (
        extract_issues_from_description(subtask.description)
        or extract_prior_issues(prior_results)
    )
