"""红利股追踪指令（岩神域）：toggle_dividend_cron 工具 + /dividend 命令族。

`toggle_dividend_cron` 抽出来给 bootstrap 启动时自动启用 + tools/builtin/dividend.py 共用。
"""
from __future__ import annotations

from loguru import logger

from paimon.state import state

from ._dispatch import CommandContext, command


# 默认 cron：工作日 19:00 收盘后 daily 更新；月 1 日 21:00 全扫刷 watchlist
_DIVIDEND_CRON_DAILY = "0 19 * * 1-5"
_DIVIDEND_CRON_FULL = "0 21 1 * *"


async def toggle_dividend_cron(
    *, enable: bool, channel_name: str, chat_id: str,
    restore_disabled: bool = True,
) -> tuple[bool, str]:
    """helper：开启/关闭红利股 daily + full 两个 cron。幂等。

    restore_disabled: True（默认，/dividend on 路径用）= 把已存在但被三月退避
    禁用的 task 恢复；False（启动时自动启用路径用）= 遵循用户的 /dividend off
    意图，不把被 disable 的任务重新开起来，只补缺失的。
    """
    if not state.irminsul or not state.march:
        return False, "世界树 / 三月未就绪"

    # 找已有 dividend_scan 任务（方案 D：按 task_type 分类，不再按 prompt 前缀）
    tasks = await state.march.list_tasks()
    existing = {
        t.source_entity_id: t
        for t in tasks
        if t.task_type == "dividend_scan" and t.source_entity_id
    }

    if not enable:
        # 暂停（而非删除）已有 dividend cron
        # 选 pause 而非 delete 的原因：保留"用户关过"的证据，让启动自动启用路径
        # (restore_disabled=False) 能识别这是用户明确意图，不会重新开起来；
        # 且 /tasks 面板上仍能看到"已停止"的卡，透明度更好
        paused = 0
        already_off = 0
        for mode_key, t in existing.items():
            if not t.enabled:
                already_off += 1
                continue
            try:
                if await state.march.pause_task(t.id):
                    paused += 1
            except Exception as e:
                logger.warning("[岩神·cron] 暂停 {} 失败: {}", t.id, e)
        parts = []
        if paused: parts.append(f"暂停 {paused} 条")
        if already_off: parts.append(f"{already_off} 条本就关闭")
        detail = "、".join(parts) if parts else "无需操作"
        return True, f"已关闭红利股定时任务（{detail}）"

    # enable：确保两个 cron 都在
    created: list[str] = []
    resumed: list[str] = []
    for mode, cron in [("daily", _DIVIDEND_CRON_DAILY), ("full", _DIVIDEND_CRON_FULL)]:
        if mode in existing:
            t = existing[mode]
            # disabled 可能来自两个原因：(a) 三月退避熔断 (b) 用户主动 /dividend off
            # 自启动路径（restore_disabled=False）不区分这两种——宁可让用户再
            # /dividend on 一次，也不擅自把用户关掉的重新打开
            if not t.enabled and restore_disabled:
                try:
                    if await state.march.resume_task(t.id):
                        resumed.append(mode)
                except Exception as e:
                    logger.warning("[岩神·cron] 恢复 {} 失败: {}", mode, e)
            continue
        try:
            await state.march.create_task(
                chat_id=chat_id,
                channel_name=channel_name,
                prompt="",  # 方案 D：路由靠 task_type + mode，prompt 不承担编码
                trigger_type="cron",
                trigger_value={"expr": cron},
                task_type="dividend_scan",
                source_entity_id=mode,
            )
            created.append(f"{mode} ({cron})")
        except Exception as e:
            return False, f"{mode} cron 创建失败: {e}"

    if not created and not resumed:
        return True, "红利股定时任务已在运行（daily + full 都已启用）"
    parts = []
    if created:
        parts.append(f"新建: {'、'.join(created)}")
    if resumed:
        parts.append(f"恢复: {'、'.join(resumed)}")
    return True, "已启用红利股定时任务（" + "；".join(parts) + "）"


@command("dividend")
async def cmd_dividend(ctx: CommandContext) -> str:
    """红利股追踪（岩神）。

    /dividend on         启用定时：daily(工作日 19:00) + full(月 1 日 21:00)
    /dividend off        停用全部定时
    /dividend run-full   立即全市场扫描（~15 分钟）
    /dividend run-daily  立即 watchlist 日更（~1 分钟）
    /dividend rescore    秒级重评分（仅用缓存）
    /dividend top [N]    查看当前 top（默认 20）
    /dividend recommended 查看推荐选股（watchlist）
    /dividend changes [N] 近 N 天变化（默认 7）
    /dividend history <code> [days] 单股历史评分
    """
    if not state.zhongli or not state.irminsul:
        return "岩神未就绪"

    args = ctx.args.strip()
    if not args:
        return cmd_dividend.__doc__ or "用法: /dividend on|off|run-*|top|changes|history"

    parts = args.split(maxsplit=1)
    action = parts[0].lower()
    rest = parts[1].strip() if len(parts) > 1 else ""

    if action in ("on", "off"):
        ok, msg = await toggle_dividend_cron(
            enable=(action == "on"),
            channel_name=ctx.msg.channel_name,
            chat_id=ctx.msg.chat_id,
        )
        return msg

    if action in ("run-full", "run-daily", "rescore"):
        mode_map = {"run-full": "full", "run-daily": "daily", "rescore": "rescore"}
        mode = mode_map[action]
        if not state.march:
            return "三月未就绪"
        if state.zhongli.is_scanning():
            return "已有扫描在进行，请等待完成后再触发"
        from paimon.foundation.bg import bg
        bg(state.zhongli.collect_dividend(
            mode=mode,
            irminsul=state.irminsul,
            march=state.march,
            chat_id=ctx.msg.chat_id,
            channel_name=ctx.msg.channel_name,
        ), label=f"zhongli·红利股·{mode}")
        hint = {
            "full": "约 15-20 分钟",
            "daily": "约 30-60 秒",
            "rescore": "几秒内完成",
        }[mode]
        return f"已触发红利股 {mode} 扫描（{hint}），完成后推送报告"

    if action == "top":
        n = 20
        if rest:
            try:
                n = max(1, min(int(rest), 100))
            except ValueError:
                pass
        rows = await state.zhongli.get_top(n, state.irminsul)
        if not rows:
            return "暂无评分数据，请先跑 /dividend run-daily"
        return state.zhongli._format_ranking(rows)

    if action == "recommended":
        rows = await state.zhongli.get_recommended(state.irminsul)
        if not rows:
            return "暂无推荐数据，请先跑 /dividend run-full"
        return state.zhongli._format_recommended_snapshots(rows)

    if action == "changes":
        days = 7
        if rest:
            try:
                days = max(1, min(int(rest), 90))
            except ValueError:
                pass
        chs = await state.zhongli.get_changes(days, state.irminsul)
        if not chs:
            return f"最近 {days} 天无显著变化"
        return state.zhongli._format_changes_list(chs)

    if action == "history":
        if not rest:
            return "用法: /dividend history <6位股票代码> [days]"
        bits = rest.split()
        code = bits[0]
        days = 90
        if len(bits) > 1:
            try:
                days = max(1, min(int(bits[1]), 365))
            except ValueError:
                pass
        import re as _re
        if not _re.fullmatch(r"\d{6}", code):
            return "股票代码必须是 6 位数字"
        history = await state.zhongli.get_stock_history(code, days, state.irminsul)
        return state.zhongli._format_history(code, history)

    return (
        f"未知子命令: {action}\n"
        "可用: on / off / run-full / run-daily / rescore / top / recommended / changes / history"
    )
