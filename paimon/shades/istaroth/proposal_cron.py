"""时执 · 自进化提案 cron 维护：

1. `skill_proposal_prune`（周一 03:30）—— 清 30 天前 rejected 提案，避免表膨胀
2. `skill_evolve_monthly`（每月 1 日 04:00）—— 跑一次"扫近 30 天会话凝练 skill"

两个 cron 注册到 task_types registry，由三月调度触发；时执负责实际收尾逻辑
（跟时执的会话压缩 / skill 热重载 / 生命周期清扫等同源，都是任务尾声的事）。
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
            logger.warning("[时执·提案 prune] irminsul 未就绪，跳过")
            return
        before_ts = time.time() - PRUNE_TTL_SECONDS
        n = await state.irminsul.skill_proposal_prune(
            before_ts=before_ts, statuses=("rejected",), actor="时执",
        )
        logger.info("[时执·提案 prune] 清理 {} 条 30 天前 rejected 提案", n)

    task_types.register(task_types.TaskTypeMeta(
        task_type="skill_proposal_prune",
        display_label="自进化·提案 prune",
        manager_panel="/plugins",
        archon="istaroth",
        icon="trash",
        description_builder=_desc_prune,
        anchor_builder=None,
        dispatcher=_dispatch_prune,
    ))

    async def _desc_monthly(_sid, _irm) -> str:
        return "月度自进化扫描（凝练近 30 天会话的 skill）"

    async def _dispatch_monthly(task, state) -> None:
        if not state.irminsul or not state.model:
            logger.warning("[时执·月度自进化] irminsul / model 未就绪，跳过")
            return
        await _run_monthly_evolve_scan(state.irminsul, state.model)

    task_types.register(task_types.TaskTypeMeta(
        task_type="skill_evolve_monthly",
        display_label="自进化·月度扫描",
        manager_panel="/plugins",
        archon="istaroth",
        icon="search",
        description_builder=_desc_monthly,
        anchor_builder=None,
        dispatcher=_dispatch_monthly,
    ))


async def _run_monthly_evolve_scan(irminsul, model) -> None:
    """月度扫描：清旧 pending → 拿近 30 天会话拼摘要 → propose+review 链。"""
    from paimon.shades.istaroth._propose_trigger import run_propose_review_chain

    # 0. 先清 30 天前未落盘提案（pending）：用户一个月没处理 = 大概率不需要了。
    #    approved 不清——那已经过了用户决策门，apply 失败属技术问题，让用户手动重试。
    try:
        before_ts = time.time() - 30 * 86400
        n_pruned = await irminsul.skill_proposal_prune(
            before_ts=before_ts, statuses=("pending",), actor="时执·月度",
        )
        logger.info(
            "[时执·月度自进化] 清理 30 天前未落盘 pending 提案 {} 条", n_pruned,
        )
    except Exception as e:
        logger.warning("[时执·月度自进化] 清理旧 pending 异常（不阻塞扫描）: {}", e)

    # 拿近 30 天活跃会话（按 updated_at 倒序拿前 50 个）
    cutoff = time.time() - 30 * 86400
    try:
        all_sessions = await irminsul.session_list_all_full()
    except Exception as e:
        logger.warning("[时执·月度自进化] 拉会话列表失败: {}", e)
        return

    recent = [s for s in all_sessions if s.updated_at >= cutoff]
    if not recent:
        logger.info("[时执·月度自进化] 近 30 天无活跃会话，跳过")
        return
    recent.sort(key=lambda s: s.updated_at, reverse=True)
    sample = recent[:10]

    # 拼汇总 context
    summary_lines = [f"## 近期会话汇总（共 {len(recent)} 个）\n"]
    for i, s in enumerate(sample, 1):
        summary_lines.append(f"{i}. **{s.name}** — 共 {len(s.messages)} 条消息")
    if len(recent) > 10:
        summary_lines.append(f"\n（仅展示前 10，共 {len(recent)} 个）")
    description = "\n".join(summary_lines)

    logger.info(
        "[时执·月度自进化] 触发提案产出（候选 {} 个会话，展示前 {} 个）",
        len(recent), len(sample),
    )
    try:
        await run_propose_review_chain(
            title="月度自进化扫描",
            description=description,
            session_id="",
            origin_id=uuid.uuid4().hex,
            irminsul=irminsul,
            model=model,
        )
    except Exception as e:
        logger.warning("[时执·月度自进化] 提案产出异常：{}", e)
