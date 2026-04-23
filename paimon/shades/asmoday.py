"""空执 · Asmoday — 动态路由

管线第三步。按 DAG 拓扑分层把子任务路由到对应七神：
  - 层内节点并发（asyncio.gather）
  - 节点失败 → 传递性标记下游 skipped
  - 未知 assignee → 回退草神
"""
from __future__ import annotations

import asyncio

from loguru import logger

from paimon.archons.base import Archon
from paimon.archons.furina import FurinaArchon
from paimon.archons.mavuika import MavuikaArchon
from paimon.archons.nahida import NahidaArchon
from paimon.archons.raiden import RaidenArchon
from paimon.archons.tsaritsa import TsaritsaArchon
from paimon.archons.venti import VentiArchon
from paimon.archons.zhongli import ZhongliArchon
from paimon.foundation.irminsul import Irminsul
from paimon.foundation.irminsul.task import Subtask, TaskEdict
from paimon.llm.model import Model

from ._plan import (
    Plan,
    collect_prior_results,
    mark_downstream_skipped,
    topological_layers,
)


_ARCHON_REGISTRY: dict[str, Archon] = {
    "草神": NahidaArchon(),
    "雷神": RaidenArchon(),
    "水神": FurinaArchon(),
    "火神": MavuikaArchon(),
    "风神": VentiArchon(),
    "岩神": ZhongliArchon(),
    "冰神": TsaritsaArchon(),
}


async def dispatch(
    task: TaskEdict,
    plan: Plan,
    model: Model,
    irminsul: Irminsul,
) -> dict[str, str]:
    """按拓扑分层并发执行。返回 {subtask_id: result_text}。

    失败处理：
      - 单节点 exception → 标 failed，产物为错误文本
      - 下游依赖该节点的节点 → 标 skipped
      - 返回 dict 中失败/跳过节点的 result 都是具可读性的文本
    """
    layers = topological_layers(plan.subtasks)
    by_id = plan.by_id
    results: dict[str, str] = {}
    statuses: dict[str, str] = {s.id: s.status for s in plan.subtasks}

    # 预灌：revise 轮里 preserved 节点 status="completed" 且 result 已有，
    # 不再重跑，但必须把它们的产物注入 results 供下游 prior 使用。
    preserved_done = 0
    for s in plan.subtasks:
        if s.status == "completed" and s.result:
            results[s.id] = s.result
            preserved_done += 1
    if preserved_done:
        logger.info(
            "[空执] round {} 继承已完成节点 {} 个（跳过重跑）",
            plan.round, preserved_done,
        )

    logger.info(
        "[空执] round {} 分层 dispatch: {} 层 / 共 {} 节点",
        plan.round, len(layers), len(plan.subtasks),
    )

    for layer_idx, layer in enumerate(layers):
        # 过滤：跳过 skipped（同轮上游失败）和 completed（上轮已完成的 preserved 节点）
        active = [
            s for s in layer
            if statuses.get(s.id) not in ("skipped", "completed")
        ]
        if not active:
            continue

        logger.info(
            "[空执] 第 {}/{} 层，{} 节点并发",
            layer_idx + 1, len(layers), len(active),
        )

        coros = [
            _run_one(s, task, model, irminsul, results, by_id)
            for s in active
        ]
        layer_results = await asyncio.gather(*coros, return_exceptions=True)

        for sub, outcome in zip(active, layer_results):
            if isinstance(outcome, Exception):
                err = f"[{sub.assignee}] 执行失败: {outcome}"
                logger.error("[空执] 子任务 {} 失败: {}", sub.id, outcome)
                await irminsul.subtask_update_status(
                    sub.id, status="failed", result=err[:2000], actor=sub.assignee,
                )
                statuses[sub.id] = "failed"
                # 同步 in-memory Subtask（naberius 修订路径依赖这个）
                sub.status = "failed"
                sub.result = err[:2000]
                results[sub.id] = err
                # 传递性标记下游 skipped
                skipped_ids = mark_downstream_skipped(sub.id, plan.subtasks, results)
                for sid in skipped_ids:
                    if statuses.get(sid) == "skipped":
                        continue
                    statuses[sid] = "skipped"
                    skip_msg = f"[跳过] 上游节点 {sub.id} 失败"
                    await irminsul.subtask_update_status(
                        sid, status="skipped", result=skip_msg, actor="空执",
                    )
                    # 同步 in-memory
                    target = by_id.get(sid)
                    if target is not None:
                        target.status = "skipped"
                        target.result = skip_msg
                    results[sid] = skip_msg
                await irminsul.audit_append(
                    event_type="subtask_failed_propagated",
                    payload={
                        "failed_id": sub.id,
                        "error": str(outcome)[:400],
                        "skipped_downstream": skipped_ids,
                    },
                    task_id=task.id, session_id=task.session_id, actor="空执",
                )
            else:
                results[sub.id] = outcome or ""
                statuses[sub.id] = "completed"
                # 同步 in-memory（_run_one 已写 DB，但没动 in-memory 对象）
                sub.status = "completed"
                sub.result = (outcome or "")[:2000]

    return results


async def _run_one(
    sub: Subtask,
    task: TaskEdict,
    model: Model,
    irminsul: Irminsul,
    results_so_far: dict[str, str],
    by_id: dict[str, Subtask],
    *,
    max_attempts: int = 2,  # 首次 + 1 次重试
) -> str:
    """执行单个子任务。

    首次失败立即重试 1 次（临时故障容忍，如网络抖动 / LLM 偶发拒答）。
    两次都失败时抛异常交由 dispatch 处理（标 failed + 传递 skip + 审计）。
    """
    archon = _ARCHON_REGISTRY.get(sub.assignee)
    if not archon:
        logger.warning("[空执] 未知执行者 '{}', 回退到草神", sub.assignee)
        archon = _ARCHON_REGISTRY["草神"]

    await irminsul.flow_append(
        task_id=task.id,
        from_agent="空执",
        to_agent=sub.assignee,
        action="dispatch",
        payload={"subtask_id": sub.id, "round": sub.round},
        actor="空执",
    )
    await irminsul.subtask_update_status(sub.id, status="running", actor="空执")
    logger.info(
        "[空执] 执行 {} (round {}) → {}",
        sub.id, sub.round, sub.assignee,
    )

    prior = collect_prior_results(sub, results_so_far, by_id)

    last_err: Exception | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            result = await archon.execute(
                task, sub, model, irminsul,
                prior_results=prior if prior else None,
            )
            await irminsul.subtask_update_status(
                sub.id, status="completed",
                result=(result or "")[:2000], actor=sub.assignee,
            )
            if attempt > 1:
                logger.info(
                    "[空执] 子任务 {} 第 {} 次尝试成功",
                    sub.id, attempt,
                )
                await irminsul.audit_append(
                    event_type="subtask_retry_success",
                    payload={"subtask_id": sub.id, "attempts": attempt},
                    task_id=task.id, session_id=task.session_id, actor="空执",
                )
            return result or ""
        except Exception as e:
            last_err = e
            if attempt < max_attempts:
                logger.warning(
                    "[空执] 子任务 {} 第 {}/{} 次失败，重试: {}",
                    sub.id, attempt, max_attempts, e,
                )
                await irminsul.audit_append(
                    event_type="subtask_retry",
                    payload={
                        "subtask_id": sub.id,
                        "attempt": attempt,
                        "error": str(e)[:400],
                    },
                    task_id=task.id, session_id=task.session_id, actor="空执",
                )

    # 重试用尽
    assert last_err is not None
    raise last_err
