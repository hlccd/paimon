"""四影闭环 · Saga 补偿

失败回滚采用轻量 saga 模式（不做状态快照）：
  - 每个 Subtask 可声明 `compensate` 字段（自然语言描述反向动作）
  - pipeline 失败时，对**已成功节点**按反序执行补偿
  - 补偿交工人 stage="exec" 执行（大多数补偿是 shell/文件操作）
  - 补偿本身失败不递归，只写审计标 `compensate_failed`
  - 无 compensate 的节点直接跳过（大多数纯推理任务无副作用）

docs/migration.md C-Q1 的技术选型决议：选 saga 而非快照。
"""
from __future__ import annotations

from loguru import logger

from paimon.foundation.irminsul import Irminsul
from paimon.foundation.irminsul.task import Subtask, TaskEdict
from paimon.llm.model import Model

from .worker import run_stage


async def run_compensations(
    task: TaskEdict,
    subtasks: list[Subtask],
    completed_ids: set[str],
    model: Model,
    irminsul: Irminsul,
    *,
    trigger_reason: str = "",
) -> list[dict]:
    """反向执行补偿。

    Args:
        task: 顶层任务
        subtasks: 本次管线所有子任务（含各轮次）
        completed_ids: 已完成的节点 id 集合（只对它们执行补偿）
        model: LLM 句柄（工人 exec stage 执行补偿时用）
        irminsul: 世界树
        trigger_reason: 触发回滚的根因（写入审计）

    Returns:
        list of {subtask_id, compensate, outcome: 'done'|'failed'|'skipped'}
    """
    # 有补偿描述且已完成的节点才参与；按执行顺序反序
    candidates = [
        s for s in subtasks
        if s.id in completed_ids and (s.compensate or "").strip()
    ]
    if not candidates:
        logger.info("[四影·saga] 无需补偿（无 compensate 声明或无已完成节点）")
        return []

    # 按 updated_at 降序（最后完成的最先补偿）
    candidates.sort(key=lambda s: s.updated_at, reverse=True)

    logger.warning(
        "[四影·saga] 开始回滚 task={} trigger={} 待补偿={}",
        task.id, trigger_reason[:80], len(candidates),
    )

    await irminsul.audit_append(
        event_type="saga_rollback_started",
        payload={
            "trigger": trigger_reason[:400],
            "candidates": [s.id for s in candidates],
        },
        task_id=task.id, session_id=task.session_id, actor="四影·saga",
    )

    outcomes: list[dict] = []
    for sub in candidates:
        outcome = await _compensate_one(sub, task, model, irminsul)
        outcomes.append(outcome)

    done = sum(1 for o in outcomes if o["outcome"] == "done")
    failed = sum(1 for o in outcomes if o["outcome"] == "failed")
    logger.warning(
        "[四影·saga] 回滚完成 task={} ({} 成功 / {} 失败 / {} 总)",
        task.id, done, failed, len(outcomes),
    )

    await irminsul.audit_append(
        event_type="saga_rollback_finished",
        payload={"outcomes": outcomes},
        task_id=task.id, session_id=task.session_id, actor="四影·saga",
    )

    return outcomes


async def _compensate_one(
    sub: Subtask,
    task: TaskEdict,
    model: Model,
    irminsul: Irminsul,
) -> dict:
    """执行单个节点的补偿动作（v6 解耦后：工人 exec stage）。"""
    compensate_desc = (sub.compensate or "").strip()
    logger.warning(
        "[四影·saga] 补偿 {} ({}) → {}",
        sub.id, sub.assignee, compensate_desc[:100],
    )

    try:
        # 构一个专用的补偿 subtask 喂给工人 stage=exec
        synthetic = Subtask(
            id=f"compensate-{sub.id}",
            task_id=task.id,
            parent_id=sub.id,
            assignee="exec",
            description=(
                f"【Saga 补偿】回滚以下动作的副作用。\n"
                f"原节点: {sub.assignee} - {sub.description[:200]}\n"
                f"补偿动作: {compensate_desc}\n\n"
                f"请严格只做补偿动作，不要做额外操作。成功后简短确认。"
            ),
            status="running",
            created_at=sub.created_at,
            updated_at=sub.updated_at,
            deps=[], round=sub.round,
        )
        result = await run_stage("exec", task, synthetic, model, irminsul)
        await irminsul.audit_append(
            event_type="saga_compensate_done",
            payload={
                "subtask_id": sub.id,
                "compensate": compensate_desc[:400],
                "result_preview": (result or "")[:300],
            },
            task_id=task.id, session_id=task.session_id, actor="工人·saga",
        )
        return {"subtask_id": sub.id, "compensate": compensate_desc, "outcome": "done"}

    except Exception as e:
        logger.error("[四影·saga] 补偿失败 {}: {}", sub.id, e)
        await irminsul.audit_append(
            event_type="saga_compensate_failed",
            payload={
                "subtask_id": sub.id,
                "compensate": compensate_desc[:400],
                "error": str(e)[:400],
            },
            task_id=task.id, session_id=task.session_id, actor="工人·saga",
        )
        return {"subtask_id": sub.id, "compensate": compensate_desc, "outcome": "failed"}
