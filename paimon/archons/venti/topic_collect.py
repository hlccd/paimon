"""风神 · topic 调研订阅 collector：走 LLM 综合输出三段 markdown。

binding_kind='topic_research' 的订阅走这里：
- 调 invoke_skill_workflow 跑 topic skill（含 LLM 综合）
- LLM 按 SKILL.md 标准输出契约写「情绪分析 → 各源讨论重点 → 综合 Top」
- 覆盖式 upsert 到 feed_topic_research 表（每订阅一条最新，不累加）
- 不走 push_archive / 不走 ring_event（前端进面板时主动拉表展示）

时间预算：topic 子进程 30-60s + LLM 综合 20-40s ≈ 1-2 分钟。
"""
from __future__ import annotations

import time

from loguru import logger


async def run_topic_research_collect(sub, state) -> None:
    """topic 调研订阅 cron 入口。

    sub.query 直接作为 topic skill 的 user_message；sub.binding_id 不用。
    """
    if not state.irminsul:
        logger.error("[风神·topic] state.irminsul 未就绪 sub={}", sub.id)
        return
    if not state.model:
        logger.error("[风神·topic] state.model 未就绪 sub={}", sub.id)
        return
    if not sub.enabled:
        logger.info("[风神·topic] 订阅已禁用 sub={}", sub.id)
        return

    irminsul = state.irminsul
    query = (sub.query or "").strip()
    if not query:
        logger.warning("[风神·topic] query 为空 sub={}", sub.id)
        await irminsul.subscription_update(
            sub.id, actor="风神", last_run_at=time.time(),
            last_error="query 为空",
        )
        return

    logger.info("[风神·topic] 开始采集 sub={} query={!r}", sub.id, query)
    t0 = time.time()
    try:
        from paimon.shades._helpers.runner_helpers import invoke_skill_workflow
        markdown = await invoke_skill_workflow(
            skill_name="topic",
            user_message=query,
            model=state.model,
            session_name=f"venti-topic-{sub.id[:8]}-{int(t0)}",
            component="topic",
            purpose="topic",
            allowed_tools={"exec"},
        )
    except Exception as e:
        logger.error("[风神·topic] skill 调用失败 sub={} err={}", sub.id, e)
        await irminsul.subscription_update(
            sub.id, actor="风神", last_run_at=time.time(),
            last_error=str(e)[:500],
        )
        return

    duration_s = int(time.time() - t0)
    markdown = (markdown or "").strip()
    if not markdown:
        logger.warning("[风神·topic] LLM 返回空 sub={} query={!r}", sub.id, query)
        await irminsul.subscription_update(
            sub.id, actor="风神", last_run_at=time.time(),
            last_error="LLM 返回空内容",
        )
        return

    try:
        await irminsul.feed_topic_research_upsert(
            sub.id, query=query, markdown=markdown, duration_s=duration_s,
        )
    except Exception as e:
        logger.error("[风神·topic] 落库失败 sub={} err={}", sub.id, e)
        await irminsul.subscription_update(
            sub.id, actor="风神", last_run_at=time.time(),
            last_error=f"落库失败: {e}"[:500],
        )
        return

    await irminsul.subscription_update(
        sub.id, actor="风神", last_run_at=time.time(), last_error="",
    )
    logger.info(
        "[风神·topic] 完成 sub={} markdown={} chars duration={}s",
        sub.id, len(markdown), duration_s,
    )
