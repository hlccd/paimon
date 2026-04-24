"""生执 · Naberius — 任务编排

管线第二步。将复杂任务分解为子任务 DAG，支持多轮修订。

本模块负责：
  - 初始编排（round 1）：LLM 产出 DAG（节点 + deps）
  - 修订编排（round 2+）：基于水神 verdict 修订失败/不通过的节点
  - 依赖环检测（Kahn/DFS）；检出后降级为线性链 + 审计
  - 过滤无效 deps（LLM 可能引用不存在的临时 id）
"""
from __future__ import annotations

import json
import time
from uuid import uuid4

from loguru import logger

from paimon.core.authz.sensitive_tools import derive_sensitivity
from paimon.foundation.irminsul import Irminsul
from paimon.foundation.irminsul.task import Subtask, TaskEdict
from paimon.llm.model import Model

from ._plan import Plan, detect_cycle, filter_invalid_deps, linearize
from ._verdict import ReviewVerdict, LEVEL_REDO, LEVEL_REVISE


_SEVEN_ARCHONS_DESC = """\
当前可用的执行者（七神）：
- 草神 (tools: knowledge/memory/exec): 推理、知识整合、文书起草、方案分析
- 雷神 (tools: file_ops/exec): 写代码（含自检）、代码生成、重构
- 水神 (tools: file_ops): 评审挑刺（方案/代码/文档/架构），质量终审
- 火神 (tools: exec): Shell/代码执行、部署，仅在用户明确要求执行时使用
- 风神 (tools: web_fetch/exec): 新闻采集、舆情分析、信息整理
- 岩神 (tools: exec): 理财分析、红利股、资产管理
- 冰神 (tools: skill_manage/exec): Skill 生态管理、扫描评估
"""

_INITIAL_PROMPT = f"""\
你是任务编排官·纳贝里士。你的职责是把复杂任务拆分为 DAG（子任务有向无环图）。

{_SEVEN_ARCHONS_DESC}

编排规则：
1. 每个子任务必须有唯一的临时编号 id（如 "s1", "s2"）
2. deps 是字符串数组，列出前置节点 id。无依赖则 deps=[]
3. assignee 填中文名："草神"/"雷神"/"水神"/"火神"/"风神"/"岩神"/"冰神"
4. description 要具体、可执行
5. 独立的子任务（如调研 + 起草）deps 应为空，以便并发
6. 写代码流程：先雷神写，再水神审；草水雷可多轮（本轮先拆一版）
7. **水神节点的位置**：若有水神评审节点，它应该是**最后一个节点**，依赖前面的产出
8. 简单任务 1 个节点；复杂任务 2-6 个节点
9. 每个子任务可声明 sensitive_ops（数组，预计调用的敏感工具名，如 ["exec","Write"]），用于权限预告；不确定时填 []
10. **saga 补偿**（可选）：只在节点有**副作用**（写文件、修改数据库、注册定时任务、部署等）时填 compensate
    字段，用自然语言描述如何**反向还原**（如"删除 /tmp/output.json"、"撤销 schedule id=xxx"）。
    纯查询 / 纯推理任务 compensate 留空字符串。
11. **不要**把"归档到知识库 / 整理入库 / 存档 / 总结归档"作为子任务 — 归档是系统职责（由时执·
    istaroth 自动做），不占节点。最终**回答用户的内容**必须由**业务节点**直接产出，别让管线停
    在"已整理完毕"这种空洞收尾上。

只输出 JSON 对象，格式严格如下（不要 markdown fence，不要解释）：
{{
  "subtasks": [
    {{"id": "s1", "assignee": "草神", "description": "...", "deps": [], "sensitive_ops": [], "compensate": ""}},
    {{"id": "s2", "assignee": "雷神", "description": "...", "deps": ["s1"], "sensitive_ops": ["Write"], "compensate": "删除生成的 xxx.py"}}
  ]
}}
"""


_REVISE_PROMPT = f"""\
你是任务编排官·纳贝里士。上一轮子任务已执行，但水神评审提出了修改意见，
或出现了节点失败。请**仅修订有问题的节点**，保留其余节点不变。

{_SEVEN_ARCHONS_DESC}

修订规则：
1. 对每个需要改的原节点，新建一个修订节点（新 id，描述中体现改进点）
2. 新节点的 deps 保持与原节点一致
3. 修订后的水神节点仍放最后，依赖新修订的产出
4. 如果水神给出 level=redo，意味整体重拆，本轮可大改
5. **失败节点改派**：若原节点被标记为 status=failed，说明原 assignee 无法胜任。
   请**更换 assignee**（如代码生成失败 → 草神先出方案再给雷神；执行类失败可换火神）。
6. 失败节点的下游节点若已被标 skipped，需重新纳入修订
7. 字段要求与初始编排一致：id / assignee / description / deps / sensitive_ops / compensate

只输出 JSON 对象，不要任何额外文字。
"""


async def plan(
    task: TaskEdict,
    model: Model,
    irminsul: Irminsul,
    *,
    previous_plan: Plan | None = None,
    verdict: ReviewVerdict | None = None,
    round: int = 1,
) -> Plan:
    """编排入口。

    round=1:             初始编排
    round>1 + verdict:   基于水神 verdict 修订（revise/redo）

    失败策略：
      - LLM 异常 / JSON 损坏 → 回退为"单节点委派草神"
      - 依赖环 → 线性化降级 + 审计
      - round>1 仍出环 → 抛 RuntimeError（由 pipeline 捕获进失败归档）
    """
    # 持久化时要区分"真正新增"和"上一轮保留的节点"——保留节点已经在 DB 里，
    # 再 INSERT 会 UNIQUE 冲突。用 preserved_ids 标记后，持久化环节按此跳过。
    preserved_ids: set[str] = set()

    if round == 1 or previous_plan is None or verdict is None:
        subtasks = await _plan_initial(task, model, irminsul)
        plan_obj = Plan(task_id=task.id, round=1, subtasks=subtasks, reason="")
    elif _is_code_pipeline_plan(previous_plan):
        # 三阶段写代码 DAG 专用 revise：保留已 pass 阶段，重派失败阶段生产节点 + 下游
        subtasks, preserved_ids = _revise_code_pipeline(
            task, previous_plan, verdict, round,
        )
        plan_obj = Plan(
            task_id=task.id, round=round, subtasks=subtasks,
            reason=f"[三阶段 revise] {verdict.summary[:180]}",
        )
    else:
        subtasks, preserved_ids = await _plan_revise(
            task, model, irminsul, previous_plan, verdict, round,
        )
        plan_obj = Plan(
            task_id=task.id, round=round, subtasks=subtasks,
            reason=verdict.summary[:200],
        )

    # 过滤无效 deps
    cleaned = filter_invalid_deps(plan_obj.subtasks)
    if cleaned:
        logger.warning("[生执] 清洗无效 deps {} 条", cleaned)
        await irminsul.audit_append(
            event_type="plan_invalid_deps_cleaned",
            payload={"cleaned": cleaned, "round": round},
            task_id=task.id, session_id=task.session_id, actor="生执",
        )

    # 环检测
    cycle = detect_cycle(plan_obj.subtasks)
    if cycle:
        await irminsul.audit_append(
            event_type="plan_cycle_detected",
            payload={"cycle": cycle, "round": round},
            task_id=task.id, session_id=task.session_id, actor="生执",
        )
        if round > 1:
            # 第二轮还出环，硬失败
            raise RuntimeError(f"生执第 {round} 轮仍出现依赖环 {cycle}，放弃本次任务")
        plan_obj.subtasks = linearize(plan_obj.subtasks, cycle_nodes=cycle)

    # 持久化到世界树（保留节点已在 DB 中，跳过避免 UNIQUE 冲突）
    for sub in plan_obj.subtasks:
        if sub.id in preserved_ids:
            continue
        await irminsul.subtask_create(sub, actor="生执")

    await irminsul.flow_append(
        task_id=task.id,
        from_agent="水神" if round > 1 else "死执",
        to_agent="生执",
        action=f"plan_round_{round}",
        payload={
            "subtask_count": len(plan_obj.subtasks),
            "verdict_level": verdict.level if verdict else None,
            "reason": plan_obj.reason,
        },
        actor="生执",
    )

    logger.info(
        "[生执] round {} 编排 {} 个子任务（{}）",
        round, len(plan_obj.subtasks),
        "初始" if round == 1 else f"修订 ← {verdict.level if verdict else '?'}",
    )
    return plan_obj


# ---------------- internal ----------------

async def _plan_initial(
    task: TaskEdict, model: Model, irminsul: Irminsul,
) -> list[Subtask]:
    # 检测是否是"写代码"任务 → 生成固定三阶段 6 节点 DAG（spec/design/code × 生产+水神）
    if _is_code_task(task):
        logger.info("[生执] 检测为写代码任务 → 三阶段 DAG")
        return _build_code_pipeline_dag(task.id)

    messages = [
        {"role": "system", "content": _INITIAL_PROMPT},
        {"role": "user", "content": f"请分解以下任务:\n\n{task.title}\n{task.description}"},
    ]
    items = await _call_llm_for_plan(messages, model, task, purpose="任务编排")
    return _items_to_subtasks(items, task.id, round=1)


# 写代码任务识别关键词（命中即走三阶段 DAG）
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


def _is_code_task(task: TaskEdict) -> bool:
    """简单关键词规则识别写代码任务。未来可加 LLM 兜底。"""
    text = (task.title + "\n" + task.description).lower()
    return any(k in text or k.lower() in text for k in _CODE_TASK_KEYWORDS)


def _is_code_pipeline_plan(plan: "Plan | None") -> bool:
    """判断给定 plan 是否是三阶段写代码 DAG（靠节点 description 前缀识别）。"""
    if plan is None or not plan.subtasks:
        return False
    return any(
        s.description.startswith("[STAGE:") for s in plan.subtasks
    )


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
    # 按 description 提取 stage
    def _stage_of(s: Subtask) -> str:
        d = s.description
        if d.startswith("[STAGE:spec]"): return "spec"
        if d.startswith("[STAGE:review_spec]"): return "review_spec"
        if d.startswith("[STAGE:design]"): return "design"
        if d.startswith("[STAGE:review_design]"): return "review_design"
        if d.startswith("[STAGE:code]"): return "code"
        if d.startswith("[STAGE:review_code]"): return "review_code"
        return "unknown"

    # 被审节点 id 集合（来自 verdict.issues）
    failed_ids = {
        it.get("subtask_id") for it in (verdict.issues or [])
        if it.get("subtask_id")
    }

    # 识别被挑的阶段（spec / design / code）
    failed_stage: str | None = None
    for s in ordered:
        if s.id in failed_ids:
            st = _stage_of(s)
            if st in ("spec", "design", "code"):
                failed_stage = st
                break
    # fallback：末尾 review 节点的 deps[0] stage 即生产节点
    if failed_stage is None:
        # 若 level=redo，按 review 节点识别被审阶段：review_code redo 回 design 阶段
        last_review = next(
            (s for s in reversed(ordered) if _stage_of(s).startswith("review_")),
            None,
        )
        if last_review:
            rs = _stage_of(last_review)
            failed_stage = {
                "review_spec": "spec",
                "review_design": "design",
                "review_code": "code",
            }.get(rs, "code")
        else:
            failed_stage = "code"

    # redo 降级一层：code→design, design→spec, spec→spec（没得降）
    if verdict.level == "redo":
        failed_stage = {"code": "design", "design": "spec", "spec": "spec"}[failed_stage]

    # 阶段排序 → 确定要重派的节点 = 从 failed_stage 起所有后续阶段
    stage_order = ["spec", "review_spec", "design", "review_design", "code", "review_code"]
    redo_from = stage_order.index(failed_stage)
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
            description=f"[STAGE:{stage}] {desc}",
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

    stage_meta = [
        ("spec", "草神", "产出产品方案 spec.md（revise 轮）"),
        ("review_spec", "水神", "审查 spec.md"),
        ("design", "雷神", "产出技术方案 design.md（revise 轮）"),
        ("review_design", "水神", "审查 design.md"),
        ("code", "雷神", "产出代码（revise 轮，增量修改）"),
        ("review_code", "水神", "审查 code"),
    ]

    # verdict.issues 嵌到**第一个被 redo 的生产节点** description 里——
    # revise 轮时，上一轮水神 review 节点在新 plan 里被替换，deps 机制拿不到
    # 其 result；用 description 内嵌作为确定性反馈通道，archon 分派时优先读。
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


def _build_code_pipeline_dag(task_id: str) -> list[Subtask]:
    """生成写代码三阶段 6 节点 DAG。

    description 前缀 `[STAGE:xxx]` 用于各 archon execute() 分派到对应方法。
    deps 形成流水线：每个水神节点依赖对应生产节点。
    """
    import time
    import uuid

    now = time.time()

    def _mk(assignee: str, stage: str, desc: str, deps: list[str]) -> Subtask:
        return Subtask(
            id=uuid.uuid4().hex[:12],
            task_id=task_id,
            parent_id=None,
            assignee=assignee,
            description=f"[STAGE:{stage}] {desc}",
            status="pending",
            result="",
            created_at=now,
            updated_at=now,
            deps=deps,
            round=1,
            sensitive_ops=[],
            verdict_status="",
            compensate="",
        )

    n1 = _mk("草神", "spec", "产出产品方案 spec.md（调 requirement-spec skill）", [])
    n2 = _mk("水神", "review_spec", "审查 spec.md（调 check skill spec 模式）", [n1.id])
    n3 = _mk("雷神", "design", "产出技术方案 design.md（调 architecture-design skill）", [n2.id])
    n4 = _mk("水神", "review_design", "审查 design.md（调 check skill 对齐 spec）", [n3.id])
    n5 = _mk("雷神", "code", "产出代码到 code/ 目录（调 code-implementation skill + 自检）", [n4.id])
    n6 = _mk("水神", "review_code", "审查 code（调 check skill 对齐 design）", [n5.id])

    return [n1, n2, n3, n4, n5, n6]


async def _plan_revise(
    task: TaskEdict,
    model: Model,
    irminsul: Irminsul,
    previous_plan: Plan,
    verdict: ReviewVerdict,
    round: int,
) -> tuple[list[Subtask], set[str]]:
    """修订：基于水神意见改出新节点。返回 (all_subtasks, preserved_ids)。

    preserved_ids 标识"从上一轮继承到本轮"的节点（已经存在于 DB 中，不需要再 INSERT）。
    未被标出的节点保留；水神 / 失败 / 跳过 / 有 issue 的节点作废重出。
    """
    prev_lines = []
    failed_lines = []
    for s in previous_plan.subtasks:
        base = (
            f"- [{s.assignee}] id={s.id} status={s.status} "
            f"verdict={s.verdict_status or '-'} desc={s.description[:80]}"
        )
        prev_lines.append(base)
        if s.status == "failed" and s.result:
            failed_lines.append(
                f"- 失败节点 {s.id} ({s.assignee}): {s.result[:200]}"
            )
    prev_block = "\n".join(prev_lines)
    failed_block = (
        "\n".join(failed_lines) if failed_lines
        else "(本轮无节点失败)"
    )

    issues_lines = []
    for issue in verdict.issues or []:
        issues_lines.append(
            f"- subtask={issue.get('subtask_id','?')} 原因={issue.get('reason','')} "
            f"建议={issue.get('suggestion','')}"
        )
    issues_block = "\n".join(issues_lines) or "(水神未给出具体子任务的问题)"

    user_msg = (
        f"## 原任务\n{task.title}\n{task.description}\n\n"
        f"## 上一轮 plan（round {previous_plan.round}）\n{prev_block}\n\n"
        f"## 失败节点详情\n{failed_block}\n\n"
        f"## 水神 verdict\n"
        f"level={verdict.level}\n"
        f"summary={verdict.summary}\n"
        f"issues:\n{issues_block}\n\n"
        f"## 当前轮次\nround={round}\n"
        f"请按修订规则产出本轮 plan。"
    )

    messages = [
        {"role": "system", "content": _REVISE_PROMPT},
        {"role": "user", "content": user_msg},
    ]
    items = await _call_llm_for_plan(messages, model, task, purpose="任务修订编排")

    # 水神 level=redo：完全采用 LLM 新 plan（不保留任何旧节点）
    if verdict.level == LEVEL_REDO:
        return _items_to_subtasks(items, task.id, round=round), set()

    # level=revise：LLM 产出的节点 + 未受影响的旧节点（按 id 去重）
    problem_ids = {i.get("subtask_id") for i in (verdict.issues or [])}
    new_subs = _items_to_subtasks(items, task.id, round=round)
    # 把未被水神标出的原节点保留（但 deps 可能指向已失效的节点，过滤时会清）
    preserved = []
    preserved_ids: set[str] = set()
    for s in previous_plan.subtasks:
        if s.id in problem_ids:
            continue
        if s.status in ("failed", "skipped"):  # 失败/被跳过的节点要重做
            continue
        if s.assignee == "水神":  # 水神由新 plan 重出
            continue
        preserved.append(s)
        preserved_ids.add(s.id)

    # 避免 id 冲突（理论上不会，新 plan 用新 uuid）
    return preserved + new_subs, preserved_ids


async def _call_llm_for_plan(
    messages: list[dict],
    model: Model,
    task: TaskEdict,
    *,
    purpose: str,
) -> list[dict]:
    try:
        raw, usage = await model._stream_text(messages)
        await model._record_primogem(task.session_id, "生执", usage, purpose=purpose)
    except Exception as e:
        logger.warning("[生执] LLM 调用异常，回退单节点草神: {}", e)
        return [{"id": "s1", "assignee": "草神", "description": task.description, "deps": []}]

    raw = (raw or "").strip()
    if raw.startswith("```"):
        lines = raw.splitlines()
        raw = "\n".join(lines[1:-1]) if len(lines) > 2 else raw

    try:
        obj = json.loads(raw)
    except Exception as e:
        logger.warning("[生执] JSON 解析失败，回退单节点草神: {} 原文={}", e, raw[:200])
        return [{"id": "s1", "assignee": "草神", "description": task.description, "deps": []}]

    # 兼容两种格式：{"subtasks":[...]} 或 直接 [...]
    if isinstance(obj, dict) and "subtasks" in obj:
        items = obj["subtasks"]
    elif isinstance(obj, list):
        items = obj
    else:
        items = []

    if not isinstance(items, list) or not items:
        return [{"id": "s1", "assignee": "草神", "description": task.description, "deps": []}]
    return items


def _items_to_subtasks(items: list[dict], task_id: str, round: int) -> list[Subtask]:
    """LLM 临时 id → 真实 uuid 映射；生成 Subtask 列表。"""
    now = time.time()
    tmp_to_real: dict[str, str] = {}
    # 第一遍：分配真实 id
    for i, item in enumerate(items):
        tmp = str(item.get("id") or f"s{i+1}")
        tmp_to_real[tmp] = uuid4().hex[:12]

    subtasks: list[Subtask] = []
    for i, item in enumerate(items):
        tmp = str(item.get("id") or f"s{i+1}")
        real_id = tmp_to_real[tmp]
        raw_deps = item.get("deps") or []
        if not isinstance(raw_deps, list):
            raw_deps = []
        real_deps = [tmp_to_real[str(d)] for d in raw_deps if str(d) in tmp_to_real]

        assignee = item.get("assignee", "草神")
        description = item.get("description", "").strip()
        sensitive_ops = item.get("sensitive_ops") or []
        if not isinstance(sensitive_ops, list):
            sensitive_ops = []
        # 若 LLM 没标 sensitive_ops，尝试从 assignee 的 allowed_tools 推断
        if not sensitive_ops:
            inferred = _infer_sensitive_ops(assignee)
            sensitive_ops = inferred
        compensate = str(item.get("compensate") or "").strip()

        subtasks.append(Subtask(
            id=real_id, task_id=task_id, parent_id=None,
            assignee=assignee, description=description,
            status="pending",
            created_at=now + i * 0.001,  # 保序
            updated_at=now + i * 0.001,
            deps=real_deps, round=round,
            sensitive_ops=sensitive_ops, verdict_status="",
            compensate=compensate,
        ))
    return subtasks


# 按 assignee 名字推断其 allowed_tools 里的敏感工具
# 与 paimon/archons/*.py 的 allowed_tools 声明对齐
_ARCHON_TOOL_MAP = {
    "草神": ["knowledge", "memory", "exec"],
    "雷神": ["file_ops", "exec"],
    "水神": ["file_ops"],
    "火神": ["exec"],
    "风神": ["web_fetch", "exec"],
    "岩神": ["exec"],
    "冰神": ["skill_manage", "exec"],
}


def _infer_sensitive_ops(assignee: str) -> list[str]:
    tools = _ARCHON_TOOL_MAP.get(assignee, [])
    _, hits = derive_sensitivity(tools)
    return hits
