"""风神模块级注册 + 通用 web_search 采集器（task_types / subscription_types / run_web_search_collect）。"""
from __future__ import annotations

import time
from uuid import uuid4

from loguru import logger

from paimon.foundation.march import today_local_bounds

from ._models import _DEDUP_WINDOW_SECONDS, _build_fallback_digest


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


def register_subscription_types() -> None:
    """注册风神名下的订阅类型（订阅生命周期改造）。

    `manual`：用户手填关键词订阅（venti 特化版，含事件聚类 + p0 预警），
    走原 _collect_subscription_impl 链路，行为完全不变。

    其他 archon 各自注册自己的 binding_kind（如水神 mihoyo_game）。
    """
    from paimon.foundation import subscription_types

    async def _manual_collector(sub, state) -> None:
        if not state.venti:
            logger.error("[风神·订阅] archon 未就绪 sub={}", sub.id)
            return
        # 复用风神原版完整逻辑（含事件聚类 + p0 预警）
        await state.venti._collect_subscription_impl(
            sub.id,
            irminsul=state.irminsul,
            model=state.model,
            march=state.march,
        )

    async def _desc_sub(sub, irminsul) -> str:
        return f"风神订阅：{sub.query or '未命名'}"

    subscription_types.register(subscription_types.SubscriptionTypeMeta(
        binding_kind="manual",
        display_label="风神订阅",
        archon="venti",
        manager_panel="/feed",
        collector=_manual_collector,
        description_builder=_desc_sub,
    ))


async def run_web_search_collect(sub, state) -> None:
    """通用 web-search collector（light 版，无事件聚类 / 无 p0 预警）。

    水神 mihoyo_game / 未来岩神 stock_watch 等"业务实体衍生订阅"用此 collector：
    搜 → 去重 → 落 feed_items → LLM digest（基于今日累计）→ ring_event 推送 →
    mark_pushed + 更新 last_run_at。

    跟风神 _collect_subscription_impl 区别：
    - 不做 venti_event 事件聚类（聚类是新闻舆情特性，业务订阅不需要）
    - 不做 p0 预警分发
    - source_label 用 sub.binding_kind + sub.binding_id 区分（不挤占风神命名空间）

    需要 venti archon 实例提供 _run_web_search / _compose_digest 等私有 helper。
    复用，不重复实现。
    """
    if not state.venti or not state.irminsul or not state.march:
        logger.error("[订阅·light] state 未就绪 sub={}", sub.id)
        return

    irminsul = state.irminsul
    model = state.model
    march = state.march
    archon = state.venti  # 复用 venti 的 _run_web_search / _compose_digest

    # source_label 必须以 archon 中文名作前缀，因为 march.ring_event 从 source.split('·')[0]
    # 推 actor 写入 push_archive；前端 /game 用 actor='水神' 过滤拉记录
    # 例：'水神·mihoyo_game:gs:113975833' → actor='水神', 前端按 source 包含 binding_id 分游戏
    from paimon.foundation import subscription_types
    from paimon.foundation.task_types import ARCHONS as _ARCHON_NAMES
    meta = subscription_types.get(sub.binding_kind)
    actor = _ARCHON_NAMES.get((meta and meta.archon) or "", "") or sub.binding_kind
    source_label = f"{actor}·{sub.binding_kind}:{(sub.binding_id or sub.query or '未命名')[:30]}"

    logger.info(
        "[订阅·light] 开始采集 sub={} kind={} binding={}",
        sub.id, sub.binding_kind, sub.binding_id,
    )

    if not sub.enabled:
        logger.info("[订阅·light] 订阅已禁用 sub={}", sub.id)
        return

    # Step 1: 搜
    try:
        results = await archon._run_web_search(sub.query, sub.max_items, sub.engine)
    except Exception as e:
        logger.error("[订阅·light] 搜索失败 sub={} err={}", sub.id, e)
        await irminsul.subscription_update(
            sub.id, actor=actor, last_error=str(e)[:500],
        )
        return

    if not results:
        logger.info("[订阅·light] 搜索无结果 sub={} query='{}'", sub.id, sub.query)
        await irminsul.subscription_update(
            sub.id, actor=actor,
            last_run_at=time.time(), last_error="",
        )
        return

    # Step 2: 去重（30 天窗口）
    since_ts = time.time() - _DEDUP_WINDOW_SECONDS
    existing = await irminsul.feed_items_existing_urls(sub.id, since_ts=since_ts)
    new_items = [r for r in results if (r.get("url") or "") not in existing]

    inserted_ids: list = []
    if new_items:
        records = await irminsul.feed_items_insert_with_records(
            sub.id, new_items, actor=actor,
        )
        inserted_ids = [r["id"] for r in records]
        logger.info(
            "[订阅·light] 新增 {} 条 / 总 {} sub={}",
            len(new_items), len(results), sub.id,
        )

    # Step 3: LLM digest（基于今日累计 feed_items，不走事件聚类路径）
    day_start, _ = today_local_bounds()
    today_items = await irminsul.feed_items_list(
        sub_id=sub.id, since=day_start, limit=500,
    )
    if not today_items:
        logger.info("[订阅·light] 当天累计为空，跳过 digest sub={}", sub.id)
        await irminsul.subscription_update(
            sub.id, actor=actor,
            last_run_at=time.time(), last_error="",
        )
        return

    today_payload = [
        {
            "title": it.title or "",
            "url": it.url or "",
            "description": it.description or "",
            "engine": it.engine or "",
        }
        for it in today_items
    ]
    digest = await archon._compose_digest(sub.query, today_payload, model)

    # Step 4: ring_event 推送（dedup_per_day=True 同 venti 原版）
    digest_id = uuid4().hex[:12]
    try:
        await march.ring_event(
            channel_name=sub.channel_name,
            chat_id=sub.chat_id,
            source=source_label,
            message=digest,
            extra={
                "sub_id": sub.id,
                "binding_kind": sub.binding_kind,
                "binding_id": sub.binding_id,
                "query": sub.query,
                "digest_id": digest_id,
            },
            dedup_per_day=True,
        )
    except Exception as e:
        logger.error("[订阅·light] 响铃失败 sub={} err={}", sub.id, e)

    # Step 5: mark + sub tick
    if inserted_ids:
        await irminsul.feed_items_mark_pushed(
            inserted_ids, digest_id, actor=actor,
        )
    await irminsul.subscription_update(
        sub.id, actor=actor,
        last_run_at=time.time(), last_error="",
    )

    logger.info(
        "[订阅·light] 采集完成 sub={} 新增={} digest={}",
        sub.id, len(inserted_ids), digest_id,
    )
