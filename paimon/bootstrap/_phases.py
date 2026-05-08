"""启动期实现细节：自动放行已加载 skill / 启动 ensure 订阅 / cron 任务补齐。

抽出来让 main.py 的 create_app 主流程线性可读；每个 phase 独立 try/except，
失败只 warn 不阻塞启动。
"""
from __future__ import annotations

from loguru import logger

from paimon.config import Config
from paimon.state import state


async def _ensure_startup_subscriptions() -> None:
    """启动时给所有米哈游账号 + 关注股 ensure 资讯订阅（幂等；task 被手动删时自动恢复）。"""
    try:
        from paimon.archons.furina_game import (
            ensure_mihoyo_subscriptions as _furina_ensure_sub,
        )
        from paimon.channels.webui.channel import PUSH_CHAT_ID
        accs = await state.irminsul.mihoyo_account_list()
        for acc in accs:
            await _furina_ensure_sub(
                state.irminsul, state.march,
                uid=acc.uid, game=acc.game,
                chat_id=PUSH_CHAT_ID, channel_name="webui",
            )
        if accs:
            logger.info("[水神·游戏订阅·启动 ensure] 处理 {} 个账号", len(accs))
    except Exception as e:
        logger.warning("[水神·游戏订阅·启动 ensure] 失败（不阻塞启动）: {}", e)

    try:
        from paimon.archons.zhongli.zhongli import (
            ensure_stock_subscriptions as _zhongli_ensure_sub,
        )
        from paimon.channels.webui.channel import PUSH_CHAT_ID
        entries = await state.irminsul.user_watch_list()
        for e in entries:
            await _zhongli_ensure_sub(
                state.irminsul, state.march,
                stock_code=e.stock_code, stock_name=e.stock_name,
                chat_id=PUSH_CHAT_ID, channel_name="webui",
            )
        if entries:
            logger.info("[岩神·关注股订阅·启动 ensure] 处理 {} 个股", len(entries))
    except Exception as e:
        logger.warning("[岩神·关注股订阅·启动 ensure] 失败（不阻塞启动）: {}", e)


async def _ensure_dividend_cron(cfg: Config) -> None:
    """岩神·红利股定时任务：默认启用（dividend_auto_enable=True，单用户开箱即用）。"""
    if not cfg.dividend_auto_enable:
        return
    try:
        from paimon.core.commands import toggle_dividend_cron
        from paimon.channels.webui.channel import PUSH_CHAT_ID
        ok, msg = await toggle_dividend_cron(
            enable=True,
            channel_name="webui",
            chat_id=PUSH_CHAT_ID,
            restore_disabled=False,   # 尊重用户的 /dividend off
        )
        if ok:
            logger.info("[岩神·启动] {}", msg)
        else:
            logger.warning("[岩神·启动] 自动启用失败: {}", msg)
    except Exception as e:
        logger.warning("[岩神·启动] 自动启用异常（不阻塞）: {}", e)


async def _ensure_mihoyo_collect_cron() -> None:
    """水神·游戏每日采集 cron：8:05 一次，只在有绑定账号时默认开启。"""
    try:
        from paimon.channels.webui.channel import PUSH_CHAT_ID
        existing = await state.march.list_tasks()
        types_present = {t.task_type for t in existing}
        if "mihoyo_collect" not in types_present:
            # 有账号才默认创建，避免用户从未绑定却有无效 cron
            accs = await state.irminsul.mihoyo_account_list()
            if accs:
                await state.march.create_task(
                    chat_id=PUSH_CHAT_ID, channel_name="webui", prompt="",
                    trigger_type="cron", trigger_value={"expr": "5 8 * * *"},
                    task_type="mihoyo_collect", source_entity_id="all",
                )
                logger.info("[水神·游戏·启动] 已创建每日采集 cron（8:05）")
    except Exception as e:
        logger.warning("[水神·游戏·启动] 创建 cron 异常（不阻塞）: {}", e)


async def _ensure_hygiene_cron() -> None:
    """草神·记忆 + 知识库整理 cron：周一 00:00 / 00:10 错峰，避免两个同时跑。"""
    try:
        from paimon.channels.webui.channel import PUSH_CHAT_ID
        existing = await state.march.list_tasks()
        types_present = {t.task_type for t in existing}
        if "memory_hygiene" not in types_present:
            await state.march.create_task(
                chat_id=PUSH_CHAT_ID, channel_name="webui", prompt="",
                trigger_type="cron", trigger_value={"expr": "0 0 * * 1"},
                task_type="memory_hygiene", source_entity_id="all",
            )
            logger.info("[草神·启动] 已创建记忆整理 cron（周一 00:00）")
        if "kb_hygiene" not in types_present:
            await state.march.create_task(
                chat_id=PUSH_CHAT_ID, channel_name="webui", prompt="",
                trigger_type="cron", trigger_value={"expr": "10 0 * * 1"},
                task_type="kb_hygiene", source_entity_id="all",
            )
            logger.info("[草神·启动] 已创建知识库整理 cron（周一 00:10）")
    except Exception as e:
        logger.warning("[草神·启动] 创建整理 cron 异常（不阻塞）: {}", e)


async def _autoallow_loaded_skills_and_archons() -> None:
    """单用户自用：已加载的 builtin skill + 9 个四影 stage 默认 permanent_allow。

    subject_type="stage"：四影 asmoday 通过 _STAGE_ROUTER 派发到对应影的 9 个 stage 名

    git review 已把过关；真破坏命令由 pre_filter 拦。运行时通过 watcher 加载的
    plugin / AI 生成 skill 不在此白名单，仍走死执 review。仅跳过用户已显式
    permanent_deny 的，避免覆盖严格意图。详见 docs/todo.md「权限体系 v2 重新设计」。
    """
    try:
        snapshot = await state.irminsul.authz_snapshot()
        _STAGE_NAMES = (
            "spec", "design", "code",
            "review_spec", "review_design", "review_code",
            "simple_code", "exec", "chat",
        )
        targets: list[tuple[str, str]] = []
        targets.extend(("skill", s.name) for s in state.skill_registry.list_all())
        targets.extend(("stage", n) for n in _STAGE_NAMES)
        auto_count = 0
        for subj_type, subj_id in targets:
            existing = snapshot.get((subj_type, subj_id))
            if existing == "permanent_deny":
                continue   # 用户明确禁止过，不覆盖
            if existing == "permanent_allow":
                continue   # 已经放行，不重复写
            await state.irminsul.authz_set(
                subj_type, subj_id, "permanent_allow",
                actor="启动·自动放行",
                reason="启动时已加载，单用户自用场景默认放行",
            )
            auto_count += 1
        if auto_count:
            await state.authz_cache.load(state.irminsul)  # 让本次写入立刻生效
            logger.info("[派蒙·授权] 启动时自动放行 {} 项（skill + archon）", auto_count)
    except Exception as e:
        logger.warning("[派蒙·授权] 启动时自动放行失败（不阻塞）: {}", e)
