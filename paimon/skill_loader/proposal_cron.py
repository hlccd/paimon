"""自进化提案表的 cron 维护：

1. `skill_proposal_prune`（周一 03:30）—— 清 30 天前 rejected 提案，避免表膨胀
2. `skill_evolve_monthly`（每月 1 日 04:00）—— 跑一次"扫上月任务凝练 skill"

两个都接到三月 task_types registry 上，跟 memory_hygiene / kb_hygiene 同款风格。
"""
from __future__ import annotations

import time
import uuid

from loguru import logger

PRUNE_TTL_SECONDS = 30 * 86400


def register_task_types() -> None:
    """启动期注册：skill_proposal_prune + skill_evolve_monthly 两个 task_type。"""
    from paimon.foundation import task_types

    async def _desc_prune(_sid, _irm) -> str:
        return "自进化提案表清理（30 天前 rejected）"

    async def _dispatch_prune(task, state) -> None:
        if not state.irminsul:
            logger.warning("[三月·提案 prune] irminsul 未就绪，跳过")
            return
        before_ts = time.time() - PRUNE_TTL_SECONDS
        n = await state.irminsul.skill_proposal_prune(
            before_ts=before_ts, statuses=("rejected",), actor="三月",
        )
        logger.info("[三月·提案 prune] 清理 {} 条 30 天前 rejected 提案", n)

    task_types.register(task_types.TaskTypeMeta(
        task_type="skill_proposal_prune",
        display_label="自进化·提案 prune",
        manager_panel="/plugins",
        archon="tsaritsa",
        icon="trash",
        description_builder=_desc_prune,
        anchor_builder=None,
        dispatcher=_dispatch_prune,
    ))

    async def _desc_monthly(_sid, _irm) -> str:
        return "月度自进化扫描（凝练近 30 天任务的 skill）"

    async def _dispatch_monthly(task, state) -> None:
        """跑"扫近 30 天任务凝练 skill"流程。

        实现：拿近期已归档 task 的执行摘要拼一段 context 给 propose+review 链。
        借鉴 archive hook 但 context 是多 task 汇总而非单 task。
        """
        if not state.irminsul or not state.model:
            logger.warning("[三月·月度自进化] irminsul / model 未就绪，跳过")
            return
        await _run_monthly_evolve_scan(state.irminsul, state.model)

    task_types.register(task_types.TaskTypeMeta(
        task_type="skill_evolve_monthly",
        display_label="自进化·月度扫描",
        manager_panel="/plugins",
        archon="tsaritsa",
        icon="search",
        description_builder=_desc_monthly,
        anchor_builder=None,
        dispatcher=_dispatch_monthly,
    ))


async def _run_monthly_evolve_scan(irminsul, model) -> None:
    """月度扫描：拿近 30 天高活跃 task 拼摘要 → propose+review 链。"""
    from paimon.foundation.irminsul.task import Subtask, TaskEdict
    from paimon.shades.istaroth._propose_trigger import (
        PROPOSE_TRIGGER_MARKER,
        _run_propose_review_chain,
    )

    # 拿近 30 天 archived task（lifecycle_stage=cold + status=completed）
    tasks = await irminsul.task_list(status="completed", limit=50)
    if not tasks:
        logger.info("[三月·月度自进化] 近期无 completed task，跳过")
        return

    cutoff = time.time() - 30 * 86400
    recent = [
        t for t in tasks
        if t.created_at >= cutoff
        and PROPOSE_TRIGGER_MARKER not in t.description  # 排除自进化触发产生的 task
    ]
    if not recent:
        logger.info("[三月·月度自进化] 近 30 天无符合条件 task，跳过")
        return

    # 拼汇总 context（最多 10 个 task title + 描述前 100 字）
    sample = recent[:10]
    summary_lines = [f"## 近期任务汇总（共 {len(recent)} 个）\n"]
    for i, t in enumerate(sample, 1):
        summary_lines.append(
            f"{i}. **{t.title}** — {t.description[:120]}（{t.id[:8]}）"
        )
    if len(recent) > 10:
        summary_lines.append(f"\n（仅展示前 10，共 {len(recent)} 个）")
    context = "\n".join(summary_lines)

    # 用合成 origin_task 调 propose+review 链
    now = time.time()
    syn_origin = TaskEdict(
        id=uuid.uuid4().hex,
        title="月度自进化扫描",
        description="不参与判定，仅作 origin task 占位",
        creator="三月",
        status="completed",
        session_id="",
        created_at=now, updated_at=now,
    )

    logger.info(
        "[三月·月度自进化] 触发提案产出（候选 {} 个 task，展示前 {} 个）",
        len(recent), len(sample),
    )
    try:
        await _run_propose_review_chain(
            origin_task=syn_origin,
            context=context,
            trigger_reason=f"月度扫描{len(recent)}个近期任务",
            irminsul=irminsul,
            model=model,
        )
    except Exception as e:
        logger.warning("[三月·月度自进化] 提案产出异常：{}", e)
