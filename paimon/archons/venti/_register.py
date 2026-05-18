"""风神模块级注册（task_types / subscription_types）。"""
from __future__ import annotations

from loguru import logger


def register_task_types() -> None:
    """注册风神名下的周期任务类型（方案 D）。由 bootstrap 启动时调一次。

    目前仅 `feed_collect`（话题订阅采集）；未来若风神再加新周期任务在此继续追加。
    """
    from paimon.foundation import task_types

    async def _desc(sub_id: str, irminsul: "Irminsul") -> str:
        try:
            sub = await irminsul.subscription_get(sub_id)
        except Exception as e:
            return f"（查询订阅失败：{e}）"
        if not sub:
            return f"订阅已删除（{sub_id[:8]}）"
        return sub.query or "未命名订阅"

    async def _dispatch(task, state) -> None:
        if not state.venti:
            logger.error(
                "[风神·订阅] archon 未就绪，跳过 sub={}", task.source_entity_id,
            )
            return
        sub_id = task.source_entity_id
        try:
            await state.venti.collect_subscription(
                sub_id,
                irminsul=state.irminsul,
                model=state.model,
                march=state.march,
            )
        except Exception as e:
            logger.exception("[风神·订阅] 采集异常 sub={}: {}", sub_id, e)
            if state.irminsul:
                try:
                    await state.irminsul.subscription_update(
                        sub_id, actor="风神", last_error=str(e)[:500],
                    )
                except Exception:
                    pass

    task_types.register(task_types.TaskTypeMeta(
        task_type="feed_collect",
        display_label="风神订阅",
        manager_panel="/feed",
        archon="venti",
        icon="rss",
        description_builder=_desc,
        anchor_builder=lambda sid: f"sub-{sid}",
        dispatcher=_dispatch,
    ))

    # 每日热点 cron（11/17 各跑一次）；source_entity_id 不绑业务实体，统一空串
    async def _desc_hotspot(sid: str, irminsul: "Irminsul") -> str:
        return "每日热点采集（4 源 UGC 综合 LLM 排序）"

    async def _dispatch_hotspot(task, state) -> None:
        from paimon.archons.venti.hotspot import run_daily_hotspot_collect
        venti = state.venti
        if venti and venti.is_hotspot_running():
            logger.info("[风神·hotspot] 已在采集中，跳过 cron 触发")
            return
        if venti:
            venti._hotspot_inflight = True
        try:
            await run_daily_hotspot_collect(state)
        except Exception as e:
            logger.exception("[风神·hotspot] 采集异常: {}", e)
        finally:
            if venti:
                venti._hotspot_inflight = False

    task_types.register(task_types.TaskTypeMeta(
        task_type="daily_hotspot_collect",
        display_label="风神·每日热点",
        manager_panel="/feed",
        archon="venti",
        icon="rss",
        description_builder=_desc_hotspot,
        anchor_builder=lambda _sid: "hotspot",
        dispatcher=_dispatch_hotspot,
    ))

    # 近期回顾 cron（周六 10 点）；每次跑 = 当日往前 7 天的 daily_hotspot
    async def _desc_weekly(sid: str, irminsul: "Irminsul") -> str:
        return "风神·近期回顾（汇总过去 7 天 daily 热点）"

    async def _dispatch_weekly(task, state) -> None:
        from paimon.archons.venti.hotspot import run_weekly_hotspot_collect
        venti = state.venti
        if venti and venti.is_weekly_running():
            logger.info("[风神·近期回顾] 已在生成中，跳过 cron 触发")
            return
        if venti:
            venti._weekly_inflight = True
        try:
            await run_weekly_hotspot_collect(state)
        except Exception as e:
            logger.exception("[风神·近期回顾] 异常: {}", e)
        finally:
            if venti:
                venti._weekly_inflight = False

    task_types.register(task_types.TaskTypeMeta(
        task_type="weekly_hotspot_collect",
        display_label="风神·近期回顾",
        manager_panel="/feed",
        archon="venti",
        icon="rss",
        description_builder=_desc_weekly,
        anchor_builder=lambda _sid: "weekly",
        dispatcher=_dispatch_weekly,
    ))


def register_subscription_types() -> None:
    """注册风神名下的订阅类型。

    `topic_research`：用户手填关键词订阅，跑 topic.research.py 拉 UGC 30 天调研，
    覆盖式落 feed_topic_research 表，不累加 / 不聚类 / 不推送（与水神资讯同构）。

    其他 archon 各自注册自己的 binding_kind（如水神 mihoyo_game / 岩神 stock_watch）。
    """
    from paimon.foundation import subscription_types
    from paimon.archons.venti.topic_collect import run_topic_research_collect

    async def _desc_topic(sub, irminsul) -> str:
        return f"风神订阅：{sub.query or '未命名'}"

    subscription_types.register(subscription_types.SubscriptionTypeMeta(
        binding_kind="topic_research",
        display_label="风神订阅",
        archon="venti",
        manager_panel="/feed",
        collector=run_topic_research_collect,
        description_builder=_desc_topic,
    ))


