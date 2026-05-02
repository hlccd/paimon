"""水神·游戏 · task_types / subscription_types 注册 + 米哈游账号订阅 ensure/clear。"""
from __future__ import annotations

from loguru import logger


def register_task_types() -> None:
    """注册水神·游戏名下的周期任务类型。bootstrap 启动时调一次。

    `mihoyo_collect`：每日 8:05 签到 + 便笺 + 深渊一次打包。
    """
    from paimon.foundation import task_types

    async def _desc(source_entity_id: str, irminsul) -> str:
        return "米哈游每日采集（签到 + 便笺 + 深渊）"

    async def _dispatch(task, state) -> None:
        if not state.furina_game:
            logger.error("[水神·游戏] service 未就绪，跳过采集")
            return
        try:
            await state.furina_game.collect_all(
                march=state.march,
                chat_id=task.chat_id, channel_name=task.channel_name,
            )
        except Exception as e:
            logger.exception("[水神·游戏] 采集异常: {}", e)

    task_types.register(task_types.TaskTypeMeta(
        task_type="mihoyo_collect",
        display_label="米哈游采集",
        manager_panel="/game",
        archon="furina",
        icon="gamepad",
        description_builder=_desc,
        anchor_builder=None,
        dispatcher=_dispatch,
    ))

    # mihoyo_game_collect：水神自己的游戏资讯订阅 task type（区别于风神 feed_collect）
    # 让任务面板水神段下能看到游戏资讯订阅，跟手填 manual 风神订阅分开
    async def _desc_mihoyo_sub(sub_id: str, irminsul) -> str:
        try:
            sub = await irminsul.subscription_get(sub_id)
        except Exception as e:
            return f"（查询订阅失败：{e}）"
        if not sub:
            return f"游戏订阅已删除（{sub_id[:8]}）"
        return f"游戏资讯：{sub.query or '未命名'}"

    async def _dispatch_mihoyo_sub(task, state) -> None:
        if not state.venti:
            logger.error(
                "[水神·游戏订阅] venti archon 未就绪 sub={}", task.source_entity_id,
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
                "[水神·游戏订阅] 采集异常 sub={}: {}", task.source_entity_id, e,
            )

    task_types.register(task_types.TaskTypeMeta(
        task_type="mihoyo_game_collect",
        display_label="水神·游戏资讯",
        manager_panel="/game",
        archon="furina",
        icon="rss",
        description_builder=_desc_mihoyo_sub,
        anchor_builder=None,
        dispatcher=_dispatch_mihoyo_sub,
    ))


# ============================================================
# 订阅类型注册 + ensure/clear 业务层辅助（订阅生命周期改造）
# ============================================================

# game 代号 → 中文名（query 模板填充用）
_GAME_DISPLAY: dict[str, str] = {
    "gs": "原神",
    "sr": "崩坏:星穹铁道",
    "zzz": "绝区零",
}

# mihoyo_game 订阅默认 cron：早 7 点统一（避开 mihoyo_collect 的 8:05 签到）
_MIHOYO_SUB_CRON = "0 7 * * *"


def _mihoyo_query_for(binding_id: str) -> str:
    """binding_id 'gs:114514' → '原神 最新资讯'。"""
    game = (binding_id or "").split(":", 1)[0]
    name = _GAME_DISPLAY.get(game, game or "游戏")
    return f"{name} 最新资讯"


def register_subscription_types() -> None:
    """注册水神·游戏名下的订阅类型。bootstrap 启动时调一次。

    `mihoyo_game`：绑定米哈游账号时由 ensure_mihoyo_subscriptions 自动建；
    解绑时由 clear_mihoyo_subscriptions 清。collector 复用 venti.run_web_search_collect
    （light 版，无事件聚类）。
    """
    from paimon.archons.venti import run_web_search_collect
    from paimon.foundation import subscription_types

    async def _desc(sub, irminsul) -> str:
        return f"水神·游戏资讯：{_mihoyo_query_for(sub.binding_id)}"

    subscription_types.register(subscription_types.SubscriptionTypeMeta(
        binding_kind="mihoyo_game",
        display_label="水神·游戏资讯",
        archon="furina",
        manager_panel="/game",
        collector=run_web_search_collect,
        description_builder=_desc,
    ))


async def ensure_mihoyo_subscriptions(
    irminsul, march, *, uid: str, game: str,
    chat_id: str, channel_name: str,
) -> None:
    """绑定米哈游账号时调用：给该 (game, uid) ensure 一条游戏资讯订阅 +
    挂 mihoyo_game_collect ScheduledTask。幂等：已存在则更新 query/cron 不重建。

    迁移逻辑：旧版本用 task_type='feed_collect'（归风神段），新版本用
    'mihoyo_game_collect'（归水神段）。检测到旧 task_type 自动删除重建。
    """
    binding_id = f"{game}:{uid}"
    sub = await irminsul.subscription_ensure_for(
        binding_kind="mihoyo_game", binding_id=binding_id,
        query=_mihoyo_query_for(binding_id),
        schedule_cron=_MIHOYO_SUB_CRON,
        channel_name=channel_name, chat_id=chat_id,
        max_items=30,
        actor="水神",
    )

    # 检查现有 task 类型；旧版 feed_collect 需要删掉重建为 mihoyo_game_collect
    if sub.linked_task_id:
        try:
            existing_task = await irminsul.schedule_get(sub.linked_task_id)
        except Exception:
            existing_task = None
        if existing_task and existing_task.task_type != "mihoyo_game_collect":
            logger.info(
                "[水神·游戏订阅·迁移] sub={} task_type={} → mihoyo_game_collect",
                sub.id, existing_task.task_type,
            )
            try:
                await march.delete_task(sub.linked_task_id)
            except Exception as e:
                logger.warning(
                    "[水神·游戏订阅·迁移] 删旧 task 失败 sub={}: {}", sub.id, e,
                )
            await irminsul.subscription_update(
                sub.id, actor="水神", linked_task_id="",
            )
            sub.linked_task_id = ""
        elif not existing_task:
            # task 找不到（可能被手动删了）→ 清空 linked_task_id 触发重建
            await irminsul.subscription_update(
                sub.id, actor="水神", linked_task_id="",
            )
            sub.linked_task_id = ""

    # 没 task 就建（无论是首次还是迁移后）
    if not sub.linked_task_id:
        try:
            task_id = await march.create_task(
                chat_id=chat_id, channel_name=channel_name, prompt="",
                trigger_type="cron", trigger_value={"expr": _MIHOYO_SUB_CRON},
                task_type="mihoyo_game_collect", source_entity_id=sub.id,
            )
            await irminsul.subscription_update(
                sub.id, actor="水神", linked_task_id=task_id,
            )
            logger.info(
                "[水神·游戏订阅] ensure 完成 binding={} sub={} task={}",
                binding_id, sub.id, task_id,
            )
        except Exception as e:
            logger.exception(
                "[水神·游戏订阅] 挂 task 失败 binding={}: {}", binding_id, e,
            )
    else:
        logger.info(
            "[水神·游戏订阅] ensure 命中已有订阅 binding={} sub={} (幂等)",
            binding_id, sub.id,
        )


async def clear_mihoyo_subscriptions(
    irminsul, march, *, uid: str, game: str,
) -> None:
    """解绑米哈游账号时调用：先删 ScheduledTask（业务层职责），再清订阅。"""
    binding_id = f"{game}:{uid}"
    subs = await irminsul.subscription_list_by_binding("mihoyo_game", binding_id)
    for sub in subs:
        if sub.linked_task_id and march:
            try:
                await march.delete_task(sub.linked_task_id)
            except Exception as e:
                logger.warning(
                    "[水神·游戏订阅] 删 task 失败 sub={} task={}: {}",
                    sub.id, sub.linked_task_id, e,
                )
    deleted = await irminsul.subscription_clear_for(
        "mihoyo_game", binding_id, actor="水神",
    )
    if deleted:
        logger.info(
            "[水神·游戏订阅] clear 完成 binding={} 删 {} 条",
            binding_id, len(deleted),
        )
