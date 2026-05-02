"""生执编排主流程：plan / _plan_initial / _plan_revise / _call_llm_for_plan。"""
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
from ._parser import _extract_items_from_obj, _items_to_subtasks, _salvage_from_raw_text, _strip_code_fence, _tolerant_json_parse
from .code_pipeline import _build_code_pipeline_dag, _classify_code_task, _is_code_pipeline_plan, _revise_code_pipeline


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


async def _plan_initial(
    task: TaskEdict, model: Model, irminsul: Irminsul,
) -> list[Subtask]:
    # 检测是否是"写代码"任务并按复杂度分档生成对应 DAG
    level = _classify_code_task(task)
    if level != "none":
        logger.info(
            "[生执] 写代码任务 {} 级 → {} 节点 DAG",
            level, {"trivial": 1, "simple": 2, "complex": 6}[level],
        )
        return _build_code_pipeline_dag(task.id, level=level)

    messages = [
        {"role": "system", "content": _INITIAL_PROMPT},
        {"role": "user", "content": f"请分解以下任务:\n\n{task.title}\n{task.description}"},
    ]
    items = await _call_llm_for_plan(messages, model, task, purpose="任务编排")
    return _items_to_subtasks(items, task.id, round=1)


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

    # 把 round N-1 已 completed 的保留节点注入新节点 deps 头部，
    # 让 asmoday.collect_prior_results 能拿到上轮产物作为 prior_results 喂给 archon。
    # 否则 LLM 在 deps 里写真实 id 会被 _items_to_subtasks 过滤掉（line 558 只
    # 识别本轮 LLM 临时 id），新节点拿不到上下文，从头重做——这就是 issue_log 里
    # round 2 草神看不到 round 1 风神 4299 字采集结果，反而从头开始搜索的根因。
    preserved_completed_ids = [
        s.id for s in preserved if s.status == "completed"
    ]
    if preserved_completed_ids:
        for ns in new_subs:
            existing = list(ns.deps or [])
            # 去重 + 顺序：先放上轮依赖保证上下文优先，再放 LLM 内部 deps
            ns.deps = preserved_completed_ids + [
                d for d in existing if d not in preserved_completed_ids
            ]
        logger.info(
            "[生执·revise] round {} 自动注入 {} 个 round {} 完成节点为 {} 个新节点的 deps",
            round, len(preserved_completed_ids), previous_plan.round, len(new_subs),
        )

    # 避免 id 冲突（理论上不会，新 plan 用新 uuid）
    return preserved + new_subs, preserved_ids


async def _call_llm_for_plan(
    messages: list[dict],
    model: Model,
    task: TaskEdict,
    *,
    purpose: str,
) -> list[dict]:
    """LLM 生成 plan JSON。三层兜底保证尽量保留 LLM 意图，不无脑改派草神。

    L1: 容错解析（tolerant_json_parse）—— 常见语法修复
    L2: LLM 重试一轮 —— 把原错误+原输出回喂让它重出
    L3: salvage_from_raw_text —— 正则从 raw 抢救 assignee+description
    """
    # 一次正常调用
    try:
        raw, usage = await model._stream_text(messages, component="生执", purpose=purpose)
        await model._record_primogem(task.session_id, "生执", usage, purpose=purpose)
    except Exception as e:
        logger.warning("[生执] LLM 调用异常，回退单节点草神: {}", e)
        return [{"id": "s1", "assignee": "草神",
                 "description": task.description, "deps": []}]

    raw = _strip_code_fence(raw or "")

    # L1: 容错解析
    obj, err = _tolerant_json_parse(raw)
    if obj is not None:
        items = _extract_items_from_obj(obj)
        if items:
            return items
        logger.warning("[生执] JSON 解析成功但 items 为空 → 进入 LLM 重试")

    # L2: 一次重试 —— 把原错误+原输出喂回让 LLM 纠正
    if err or obj is not None:
        logger.warning(
            "[生执] JSON 解析失败 err={} 原文前200={!r} → 重试一轮",
            err, raw[:200],
        )
        retry_messages = list(messages) + [
            {"role": "assistant", "content": raw},
            {"role": "user", "content": (
                f"上面的输出无法解析为合法 JSON（{err or 'items 为空'}）。"
                "请严格按照前面规定的 JSON 格式重新输出：\n"
                "1. 不要 markdown fence\n"
                "2. 不要任何解释文字\n"
                "3. description 字段内若需引用关键词，使用中文引号「」或转义 \\\" ，"
                "**禁止使用未转义的 ASCII 双引号**\n"
                "4. subtasks 至少 1 项"
            )},
        ]
        try:
            raw2, usage2 = await model._stream_text(
                retry_messages, component="生执", purpose=purpose + "·重试",
            )
            await model._record_primogem(
                task.session_id, "生执", usage2, purpose=purpose + "·重试",
            )
            raw2 = _strip_code_fence(raw2 or "")
            obj2, err2 = _tolerant_json_parse(raw2)
            if obj2 is not None:
                items2 = _extract_items_from_obj(obj2)
                if items2:
                    logger.info("[生执] 重试成功，获得 {} 个节点", len(items2))
                    return items2
            # 重试仍失败：把 raw2 作为 salvage 输入（比 raw 更可能含 LLM 修正过的结构）
            logger.warning(
                "[生执] 重试仍失败 err={} → 进入 salvage", err2 or "items 为空",
            )
            raw = raw2 or raw
        except Exception as e:
            logger.warning("[生执] 重试 LLM 调用异常: {} → 用原 raw 进入 salvage", e)

    # L3: salvage —— 正则抢救 assignee+description，不无脑改派草神
    return _salvage_from_raw_text(raw, task)
