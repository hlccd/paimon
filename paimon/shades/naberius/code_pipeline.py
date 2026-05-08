"""代码任务专用 pipeline：spec → design+code → review_* 三段式（v6 全 stage 化）。"""
from __future__ import annotations

import json
import re
import time
from uuid import uuid4
from loguru import logger
from paimon.core.authz.sensitive_tools import derive_sensitivity
from paimon.foundation.irminsul import Irminsul
from paimon.foundation.irminsul.task import Subtask, TaskEdict
from paimon.llm.model import Model
from .._plan import Plan, detect_cycle, filter_invalid_deps, linearize
from .._verdict import ReviewVerdict, LEVEL_REDO, LEVEL_REVISE


_CODE_TASK_KEYWORDS = (
    "写代码", "写个", "写一个", "写一段",
    "实现", "开发", "编写", "新增", "加一个", "加上", "加个",
    "修改", "修复", "fix", "改 bug", "改个",
    "重构", "refactor",
    "新建", "创建文件", "建个模块", "建一个",
    "补全", "补丁",
    ".py", ".ts", ".js", ".go", "函数", "类", "模块",
    "tests/", "测试", "单元测试",
)
_TRIVIAL_CHAR_THRESHOLD = 12
_SIMPLE_CHAR_THRESHOLD = 40
_COMPLEX_SIGNAL_KEYWORDS = (
    "系统", "框架", "架构", "服务", "模块", "组件",
    "接入", "集成", "重构", "迁移", "redesign",
    "完整的", "整套", "一整个",
)
_SIMPLE_SIGNAL_KEYWORDS = (
    "函数", "脚本", "文件", "工具", "小工具",
    "script", "snippet",
)


def _is_code_task(task: TaskEdict) -> bool:
    """简单关键词规则识别写代码任务。未来可加 LLM 兜底。"""
    text = (task.title + "\n" + task.description).lower()
    return any(k in text or k.lower() in text for k in _CODE_TASK_KEYWORDS)


def _classify_code_task(task: TaskEdict) -> str:
    """返回 "none" / "trivial" / "simple" / "complex"。

    不是写代码任务 → "none"。
    否则按 task.description 长度粗分 + 关键词升降档：
      - complex 关键词命中 → complex
      - simple 关键词命中且初判 trivial → 升到 simple
      - 否则按长度：<12 trivial / <40 simple / 其他 complex
    用户输入越详细，越可能是复杂任务；"系统/框架"等词直接走 complex。
    """
    if not _is_code_task(task):
        return "none"
    desc = task.description.strip()
    n = len(desc)

    # 关键词升档：含架构/系统信号 → 直接 complex
    if any(k in desc for k in _COMPLEX_SIGNAL_KEYWORDS):
        return "complex"

    # 长度初判
    if n < _TRIVIAL_CHAR_THRESHOLD:
        base = "trivial"
    elif n < _SIMPLE_CHAR_THRESHOLD:
        base = "simple"
    else:
        base = "complex"

    # 关键词微调：命中 simple 关键词且初判 trivial → 升到 simple
    if base == "trivial" and any(k in desc for k in _SIMPLE_SIGNAL_KEYWORDS):
        return "simple"
    return base


_CODE_PIPELINE_STAGES = {
    "spec", "review_spec", "design", "review_design", "code", "review_code",
    "simple_code",
}


def _is_code_pipeline_plan(plan: "Plan | None") -> bool:
    """判断给定 plan 是否是写代码 DAG（靠节点 assignee = code-pipeline stage 识别）。"""
    if plan is None or not plan.subtasks:
        return False
    return any(s.assignee in _CODE_PIPELINE_STAGES for s in plan.subtasks)


def _revise_code_pipeline(
    task: TaskEdict, previous_plan: "Plan", verdict: "ReviewVerdict", round: int,
) -> tuple[list[Subtask], set[str]]:
    """三阶段 DAG 专用 revise 逻辑（固定模板，不调 LLM）。

    策略：
    - verdict.issues 指向"被审生产节点"（spec/design/code 其中之一）
    - redo → 回退一级：被审阶段及之后重派
    - revise → 重派被审阶段的生产节点 + 该阶段 review + 之后所有节点

    保留 issues 未涉及的**前面**阶段的节点（status=completed）。
    """
    import time
    import uuid

    # 收集所有节点按 stage 分组（保持原顺序）
    ordered = list(previous_plan.subtasks)
    # assignee 直接就是 stage 名（v6 解耦后）
    def _stage_of(s: Subtask) -> str:
        return s.assignee if s.assignee in _CODE_PIPELINE_STAGES else "unknown"

    # 被审节点 id 集合（来自 verdict.issues）
    failed_ids = {
        it.get("subtask_id") for it in (verdict.issues or [])
        if it.get("subtask_id")
    }

    # 关键：按**当前 plan 实际存在**的阶段工作，不硬编码 6 阶段。
    # 这样 simple (code+review_code) / trivial (code only) DAG 在 revise 时
    # 不会被升级为 complex 6 节点，保持用户原本选的复杂度档位。
    full_stage_order = ["spec", "review_spec", "design", "review_design", "code", "review_code"]
    present_stages = {_stage_of(s) for s in ordered if _stage_of(s) != "unknown"}
    stage_order = [s for s in full_stage_order if s in present_stages]
    if not stage_order:
        # 完全没识别出任何 stage（异常），降级到整套 6 节点
        stage_order = full_stage_order

    # 识别被挑的阶段（只考虑 plan 里真实存在的生产阶段）
    production_in_plan = [s for s in stage_order if not s.startswith("review_")]
    failed_stage: str | None = None
    for s in ordered:
        if s.id in failed_ids:
            st = _stage_of(s)
            if st in production_in_plan:
                failed_stage = st
                break
    # fallback：末尾 review 节点的对应生产阶段
    if failed_stage is None:
        last_review = next(
            (s for s in reversed(ordered) if _stage_of(s).startswith("review_")),
            None,
        )
        if last_review:
            rs = _stage_of(last_review)
            mapped = {
                "review_spec": "spec",
                "review_design": "design",
                "review_code": "code",
            }.get(rs)
            # 映射后的 stage 必须在 plan 里（simple DAG 没有 spec）
            if mapped and mapped in production_in_plan:
                failed_stage = mapped
        if failed_stage is None:
            # 兜底：取 plan 里最后一个生产阶段
            failed_stage = production_in_plan[-1] if production_in_plan else "code"

    # redo 降级一层：只在降级后的阶段在 plan 里才降；否则留原地
    if verdict.level == "redo":
        downgrade = {"code": "design", "design": "spec", "spec": "spec"}.get(failed_stage, failed_stage)
        if downgrade in production_in_plan:
            failed_stage = downgrade
        # 否则保持 failed_stage 不变（simple/trivial 没有上游阶段可降）

    # 阶段排序 → 要重派的节点 = 从 failed_stage 起所有后续阶段（限在 present_stages 内）
    try:
        redo_from = stage_order.index(failed_stage)
    except ValueError:
        redo_from = 0  # failed_stage 不在 stage_order（异常），从头重派
    redo_stages = set(stage_order[redo_from:])

    # 保留前面阶段（同 stage 但非 review 的生产节点；且 status=completed）
    preserved: list[Subtask] = []
    preserved_ids: set[str] = set()
    for s in ordered:
        if _stage_of(s) not in redo_stages and s.status == "completed":
            # deps 保留（指向前轮节点的 deps 保持；LLM 不再生）
            preserved.append(s)
            preserved_ids.add(s.id)

    # 生成新节点（需要 redo 的阶段）；维持同一流水线 deps 链
    now = time.time()
    new_nodes: list[Subtask] = []
    # 找"最后一个 preserved 节点"的 id，作为第一个新节点的 dep
    last_preserved_id = preserved[-1].id if preserved else None

    def _mk(assignee: str, stage: str, desc: str, deps: list[str]) -> Subtask:
        return Subtask(
            id=uuid.uuid4().hex[:12],
            task_id=task.id,
            parent_id=None,
            assignee=assignee,
            description=desc,
            status="pending",
            result="",
            created_at=now,
            updated_at=now,
            deps=deps,
            round=round,
            sensitive_ops=[],
            verdict_status="",
            compensate="",
        )

    # stage_meta 只保留当前 plan 里实际存在的 stage，避免 simple/trivial revise
    # 被升级成 complex 6 节点。assignee 字段值 = stage 名（v6 解耦后的统一格式）
    _full_stage_meta = [
        ("spec", "spec", "产出产品方案 spec.md（revise 轮）"),
        ("review_spec", "review_spec", "审查 spec.md"),
        ("design", "design", "产出技术方案 design.md（revise 轮）"),
        ("review_design", "review_design", "审查 design.md"),
        ("code", "code", "产出代码（revise 轮，增量修改）"),
        ("review_code", "review_code", "审查 code"),
    ]
    stage_meta = [m for m in _full_stage_meta if m[0] in present_stages]

    # verdict.issues 嵌到**第一个被 redo 的生产节点** description 里——
    # revise 轮时，上一轮 review 节点在新 plan 里被替换，deps 机制拿不到
    # 其 result；用 description 内嵌作为确定性反馈通道，四影 stage 优先读。
    import json as _json
    issues_blob = ""
    if verdict.issues:
        try:
            issues_blob = (
                "\n\n[REVISE_FEEDBACK_JSON]"
                + _json.dumps(
                    {"level": verdict.level, "issues": verdict.issues[:20],
                     "summary": verdict.summary},
                    ensure_ascii=False,
                )
                + "[/REVISE_FEEDBACK_JSON]"
            )
        except (TypeError, ValueError):
            issues_blob = ""

    prev_id = last_preserved_id
    first_production_node_injected = False
    for stage, assignee, desc in stage_meta[redo_from:]:
        full_desc = desc
        # 只在第一个被 redo 的生产节点嵌 issues（下游 code/review 通过自己逻辑链路拿）
        if (
            not first_production_node_injected
            and stage in ("spec", "design", "code")
            and issues_blob
        ):
            full_desc = desc + issues_blob
            first_production_node_injected = True
        new = _mk(assignee, stage, full_desc, deps=[prev_id] if prev_id else [])
        new_nodes.append(new)
        prev_id = new.id

    logger.info(
        "[生执·三阶段 revise] round={} level={} failed_stage={} preserved={} new={}",
        round, verdict.level, failed_stage, len(preserved), len(new_nodes),
    )

    return preserved + new_nodes, preserved_ids


def _mk_code_node(
    task_id: str, assignee: str, stage: str, desc: str,
    deps: list[str], *, round: int = 1,
) -> Subtask:
    """统一构造写代码 DAG 节点的 Subtask。assignee 即 stage 名，asmoday 据此派 worker。"""
    import time
    import uuid
    now = time.time()
    return Subtask(
        id=uuid.uuid4().hex[:12],
        task_id=task_id,
        parent_id=None,
        assignee=assignee,
        description=desc,
        status="pending",
        result="",
        created_at=now,
        updated_at=now,
        deps=deps,
        round=round,
        sensitive_ops=[],
        verdict_status="",
        compensate="",
    )


def _build_code_pipeline_dag(task_id: str, level: str = "complex") -> list[Subtask]:
    """按复杂度生成写代码 DAG。assignee 字段即 stage 名（asmoday 通过 _STAGE_ROUTER 派各影）。

    - trivial: 1 节点（simple_code），如"写个 hello.py"
    - simple:  2 节点（code → review_code），单文件级改动
    - complex: 6 节点（spec → review_spec → design → review_design → code → review_code），
              涉及架构决策的任务
    """
    if level == "trivial":
        return [_mk_code_node(
            task_id, "simple_code", "simple_code",
            "产出代码到 code/ 目录（trivial：直接 LLM 写 + 自检）", [],
        )]

    if level == "simple":
        n1 = _mk_code_node(
            task_id, "code", "code",
            "产出代码到 code/ 目录（调 code-implementation skill + 自检）", [],
        )
        n2 = _mk_code_node(
            task_id, "review_code", "review_code",
            "审查 code（对齐原始需求）", [n1.id],
        )
        return [n1, n2]

    # complex: 完整三阶段 6 节点
    n1 = _mk_code_node(task_id, "spec", "spec",
                       "产出产品方案 spec.md（调 requirement-spec skill）", [])
    n2 = _mk_code_node(task_id, "review_spec", "review_spec",
                       "审查 spec.md（调 check skill spec 模式）", [n1.id])
    n3 = _mk_code_node(task_id, "design", "design",
                       "产出技术方案 design.md（调 architecture-design skill）", [n2.id])
    n4 = _mk_code_node(task_id, "review_design", "review_design",
                       "审查 design.md（调 check skill 对齐 spec）", [n3.id])
    n5 = _mk_code_node(task_id, "code", "code",
                       "产出代码到 code/ 目录（调 code-implementation skill + 自检）", [n4.id])
    n6 = _mk_code_node(task_id, "review_code", "review_code",
                       "审查 code（调 check skill 对齐 design）", [n5.id])
    return [n1, n2, n3, n4, n5, n6]
