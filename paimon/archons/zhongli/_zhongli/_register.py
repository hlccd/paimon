"""岩神 · 模块级注册 + 关注股订阅 ensure/clear。"""
from __future__ import annotations

import re

from loguru import logger


def _extract_code(text: str) -> str | None:
    m = re.search(r'(\d{6})', text)
    return m.group(1) if m else None


# ============================================================
# 周期任务类型注册（方案 D）
# ============================================================


def register_task_types() -> None:
    """注册岩神名下的周期任务类型。由 bootstrap 启动时调一次。

    目前仅 `dividend_scan`（红利股扫描，三种 mode：full/daily/rescore）；
    source_entity_id 存 mode 字符串。/wealth 是单大面板，无 anchor 需求。
    """
    from paimon.foundation import task_types

    _MODE_LABELS = {
        "full": "全市场全扫描",
        "daily": "每日增量更新",
        "rescore": "当日重评分",
    }

    async def _desc(mode: str, irminsul) -> str:
        label = _MODE_LABELS.get(mode, mode or "未知模式")
        return f"{label}"

    async def _dispatch(task, state) -> None:
        if not state.zhongli:
            logger.error(
                "[岩神·采集] archon 未就绪，跳过 mode={}", task.source_entity_id,
            )
            return
        mode = task.source_entity_id
        try:
            await state.zhongli.collect_dividend(
                mode=mode,
                irminsul=state.irminsul,
                march=state.march,
                chat_id=task.chat_id,
                channel_name=task.channel_name,
            )
        except Exception as e:
            logger.exception("[岩神·采集] 异常 mode={}: {}", mode, e)

    task_types.register(task_types.TaskTypeMeta(
        task_type="dividend_scan",
        display_label="岩神理财",
        manager_panel="/wealth",
        archon="zhongli",
        icon="chart",
        description_builder=_desc,
        anchor_builder=None,  # /wealth 单面板，不需要 anchor
        dispatcher=_dispatch,
    ))

    # stock_watch_collect：岩神关注股资讯订阅 task type（区别于风神 feed_collect 手填订阅）
    # 让任务面板岩神段下能看到关注股资讯订阅
    async def _desc_stock_sub(sub_id: str, irminsul) -> str:
        try:
            sub = await irminsul.subscription_get(sub_id)
        except Exception as e:
            return f"（查询订阅失败：{e}）"
        if not sub:
            return f"关注股订阅已删除（{sub_id[:8]}）"
        code = sub.binding_id or "?"
        name = ""
        try:
            entry = await irminsul.user_watch_get(code)
            if entry:
                name = (entry.stock_name or "").strip()
        except Exception:
            pass
        return f"关注股资讯：{name}（{code}）" if name else f"关注股资讯：{code}"

    async def _dispatch_stock_sub(task, state) -> None:
        if not state.venti:
            logger.error(
                "[岩神·关注股订阅] venti archon 未就绪 sub={}", task.source_entity_id,
            )
            return
        try:
            await state.venti.collect_subscription(
                task.source_entity_id,
                irminsul=state.irminsul,
                model=state.model,
                march=state.march,
            )
        except Exception as e:
            logger.exception(
                "[岩神·关注股订阅] 采集异常 sub={}: {}", task.source_entity_id, e,
            )

    task_types.register(task_types.TaskTypeMeta(
        task_type="stock_watch_collect",
        display_label="岩神·关注股资讯",
        manager_panel="/wealth",
        archon="zhongli",
        icon="rss",
        description_builder=_desc_stock_sub,
        anchor_builder=None,
        dispatcher=_dispatch_stock_sub,
    ))


# ============================================================
# 订阅类型注册 + ensure/clear 业务层辅助（关注股资讯生命周期）
# ============================================================

# 关注股资讯订阅默认 cron：早 7:30（介于风神/水神订阅 7:00 与 mihoyo_collect 8:05 之间）
_STOCK_SUB_CRON = "30 7 * * *"


def _stock_query_for(stock_code: str, stock_name: str) -> str:
    """构造资讯搜索 query：'{name} {code} 公告 资讯'。"""
    name = (stock_name or "").strip()
    code = (stock_code or "").strip()
    parts = []
    if name:
        parts.append(name)
    if code:
        parts.append(code)
    parts.append("公告 资讯")
    return " ".join(parts).strip()


def register_subscription_types() -> None:
    """注册岩神名下的订阅类型。bootstrap 启动时调一次。

    `stock_watch`：用户在 /wealth 关注股票时由 ensure_stock_subscriptions 自动建；
    取消关注时由 clear_stock_subscriptions 清。collector 复用 venti.run_web_search_collect。
    """
    from paimon.archons.venti import run_web_search_collect
    from paimon.foundation import subscription_types

    async def _desc(sub, irminsul) -> str:
        code = sub.binding_id or "?"
        name = ""
        try:
            entry = await irminsul.user_watch_get(code)
            if entry:
                name = (entry.stock_name or "").strip()
        except Exception:
            pass
        return f"关注股资讯：{name}（{code}）" if name else f"关注股资讯：{code}"

    subscription_types.register(subscription_types.SubscriptionTypeMeta(
        binding_kind="stock_watch",
        display_label="岩神·关注股资讯",
        archon="zhongli",
        manager_panel="/wealth",
        collector=run_web_search_collect,
        description_builder=_desc,
    ))


async def ensure_stock_subscriptions(
    irminsul, march, *, stock_code: str, stock_name: str,
    chat_id: str, channel_name: str,
) -> None:
    """关注股票时调用：ensure 资讯订阅 + 挂 stock_watch_collect ScheduledTask。
    幂等：已存在仅更新 query/cron，不重建。

    迁移逻辑：检测旧 task_type 不为 stock_watch_collect 时自动删除重建（防御性）。
    """
    binding_id = stock_code
    sub = await irminsul.subscription_ensure_for(
        binding_kind="stock_watch", binding_id=binding_id,
        query=_stock_query_for(stock_code, stock_name),
        schedule_cron=_STOCK_SUB_CRON,
        channel_name=channel_name, chat_id=chat_id,
        max_items=20,
        actor="岩神",
    )

    # 检查现有 task 类型；旧版若用别的 task_type 自动迁移
    if sub.linked_task_id:
        try:
            existing_task = await irminsul.schedule_get(sub.linked_task_id)
        except Exception:
            existing_task = None
        if existing_task and existing_task.task_type != "stock_watch_collect":
            logger.info(
                "[岩神·关注股订阅·迁移] sub={} task_type={} → stock_watch_collect",
                sub.id, existing_task.task_type,
            )
            try:
                await march.delete_task(sub.linked_task_id)
            except Exception as e:
                logger.warning(
                    "[岩神·关注股订阅·迁移] 删旧 task 失败 sub={}: {}", sub.id, e,
                )
            await irminsul.subscription_update(
                sub.id, actor="岩神", linked_task_id="",
            )
            sub.linked_task_id = ""
        elif not existing_task:
            await irminsul.subscription_update(
                sub.id, actor="岩神", linked_task_id="",
            )
            sub.linked_task_id = ""

    if not sub.linked_task_id:
        try:
            task_id = await march.create_task(
                chat_id=chat_id, channel_name=channel_name, prompt="",
                trigger_type="cron", trigger_value={"expr": _STOCK_SUB_CRON},
                task_type="stock_watch_collect", source_entity_id=sub.id,
            )
            await irminsul.subscription_update(
                sub.id, actor="岩神", linked_task_id=task_id,
            )
            logger.info(
                "[岩神·关注股订阅] ensure 完成 stock={}({}) sub={} task={}",
                stock_code, stock_name, sub.id, task_id,
            )
        except Exception as e:
            logger.exception(
                "[岩神·关注股订阅] 挂 task 失败 stock={}: {}", stock_code, e,
            )
    else:
        logger.info(
            "[岩神·关注股订阅] ensure 命中已有订阅 stock={} sub={} (幂等)",
            stock_code, sub.id,
        )


async def clear_stock_subscriptions(
    irminsul, march, *, stock_code: str,
) -> None:
    """取消关注股票时调用：先删 ScheduledTask，再清订阅。"""
    binding_id = stock_code
    subs = await irminsul.subscription_list_by_binding("stock_watch", binding_id)
    for sub in subs:
        if sub.linked_task_id and march:
            try:
                await march.delete_task(sub.linked_task_id)
            except Exception as e:
                logger.warning(
                    "[岩神·关注股订阅] 删 task 失败 sub={} task={}: {}",
                    sub.id, sub.linked_task_id, e,
                )
    deleted = await irminsul.subscription_clear_for(
        "stock_watch", binding_id, actor="岩神",
    )
    if deleted:
        logger.info(
            "[岩神·关注股订阅] clear 完成 stock={} 删 {} 条",
            stock_code, len(deleted),
        )
