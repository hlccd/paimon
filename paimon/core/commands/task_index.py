"""四影任务索引指令：/task-list 列最近 7 天 + /task-index N 查详情。

docs/interaction.md §2.3.2 / §四 / §五：QQ 290s 窗口外失去 done_recap 后的兜底主动查询路径。
列出后写 channel_key → ([id], expire) 索引；/task-index N 取 ids[N-1]。
"""
from __future__ import annotations

from paimon.state import state

from ._dispatch import CommandContext, command


_TASK_LIST_TTL_SECONDS = 600
_TASK_LIST_LOOKBACK_SECONDS = 7 * 86400
_TASK_LIST_MAX_ITEMS = 20


_TASK_STATUS_LABEL = {
    "pending": "待处理",
    "running": "进行中",
    "completed": "完成",
    "failed": "失败",
    "rejected": "已拒绝",
    "skipped": "已跳过",
}

_SUBTASK_STATUS_ICON = {
    "completed": "✅",
    "failed": "❌",
    "skipped": "⏭️",
    "running": "🔄",
    "pending": "⏳",
    "superseded": "♻️",
}


def _fmt_relative_time(ts: float, now: float | None = None) -> str:
    """秒级时间戳 → "X秒/分/小时/天前"；超 7 天回落到 MM-DD HH:MM。"""
    import time as _time
    if not ts or ts <= 0:
        return "-"
    now = now if now is not None else _time.time()
    diff = max(0, int(now - ts))
    if diff < 60:
        return f"{diff}秒前"
    if diff < 3600:
        return f"{diff // 60}分钟前"
    if diff < 86400:
        return f"{diff // 3600}小时前"
    if diff < 7 * 86400:
        return f"{diff // 86400}天前"
    return _time.strftime("%m-%d %H:%M", _time.localtime(ts))


def _fmt_duration(seconds: float) -> str:
    """秒数 → "X秒" / "X分Y秒" / "X时Y分Z秒" 简洁中文。"""
    seconds = max(0, int(seconds))
    if seconds < 60:
        return f"{seconds}秒"
    if seconds < 3600:
        return f"{seconds // 60}分 {seconds % 60}秒"
    h, rem = divmod(seconds, 3600)
    return f"{h}时 {rem // 60}分 {rem % 60}秒"


async def _build_task_list_index(channel_key: str) -> list:
    """筛选最近 7 天四影任务 + 写 channel 级编号缓存。返回 list[TaskEdict]。

    /task-list 和 /task-index 共用：list 显式调，index 在缓存缺失/过期时静默调。
    返回空列表表示暂无任务（调用方根据上下文给不同提示）。
    """
    import time as _time
    irminsul = state.irminsul
    if not irminsul:
        return []
    edicts = await irminsul.task_list(limit=50)
    now = _time.time()
    cutoff = now - _TASK_LIST_LOOKBACK_SECONDS
    items = [
        e for e in edicts
        if (e.creator or "").startswith("派蒙")
        and e.lifecycle_stage != "archived"
        and (e.updated_at or e.created_at) >= cutoff
    ][:_TASK_LIST_MAX_ITEMS]
    state.task_list_index[channel_key] = (
        [e.id for e in items], now + _TASK_LIST_TTL_SECONDS,
    )
    return items


@command("task-list")
async def cmd_task_list(ctx: CommandContext) -> str:
    """/task-list — 列最近 7 天的深度任务（按 updated_at DESC 取 20 条）。

    docs/interaction.md §2.3.2 / §四：列表后写 channel 级编号缓存，TTL 10 分钟，
    /task-index N 用同 channel_key 取回。
    """
    if not state.irminsul:
        return "世界树未就绪"

    items = await _build_task_list_index(ctx.msg.channel_key)
    if not items:
        return (
            "📋 最近 7 天暂无深度任务\n"
            "（用 /task <描述> 强制走四影管线；或自然语言里描述复杂任务派蒙会自动判定）"
        )

    import time as _time
    now = _time.time()
    lines = ["📋 最近 7 天任务："]
    for idx, e in enumerate(items, start=1):
        label = _TASK_STATUS_LABEL.get(e.status, e.status or "?")
        when = _fmt_relative_time(e.updated_at or e.created_at, now=now)
        title = (e.title or e.description or "").strip().replace("\n", " ")[:50] or "(无标题)"
        lines.append(f"{idx}. [{label}] {when} · {title}")
    lines.append("")
    lines.append(f"发送 /task-index N 查看详情（{_TASK_LIST_TTL_SECONDS // 60} 分钟内有效）")
    return "\n".join(lines)


@command("task-index")
async def cmd_task_index(ctx: CommandContext) -> str:
    """/task-index [N] — 查看深度任务详情。

    无参 → 取最近一条（N=1）。缓存缺失或过期时自动重建索引（不再要求先 /task-list）。
    """
    import time as _time

    arg = ctx.args.strip()
    if not arg:
        n = 1
    else:
        try:
            n = int(arg.split()[0])
        except (ValueError, IndexError):
            return f"序号格式错误: '{arg}'，需要正整数"
        if n < 1:
            return "序号需 ≥ 1"

    channel_key = ctx.msg.channel_key
    cached = state.task_list_index.get(channel_key)
    now = _time.time()
    if cached and cached[1] >= now:
        ids = cached[0]
    else:
        # 自动重建：用户直接 /task-index 不需要先 /task-list
        items = await _build_task_list_index(channel_key)
        if not state.irminsul:
            return "世界树未就绪"
        if not items:
            return "📋 最近 7 天暂无深度任务"
        ids = [e.id for e in items]

    if n > len(ids):
        return f"序号超出范围（共 {len(ids)} 条）"
    task_id = ids[n - 1]

    irminsul = state.irminsul
    if not irminsul:
        return "世界树未就绪"

    edict = await irminsul.task_get(task_id)
    if not edict:
        return f"任务已不存在或已被清理: {task_id[:8]}"

    subtasks = await irminsul.subtask_list(task_id)

    # 头部
    label = _TASK_STATUS_LABEL.get(edict.status, edict.status or "?")
    created_str = _time.strftime("%Y-%m-%d %H:%M", _time.localtime(edict.created_at)) if edict.created_at else "-"
    end_ts = edict.archived_at or edict.updated_at or 0
    duration = (end_ts - edict.created_at) if edict.created_at and end_ts > edict.created_at else 0
    head_lines = [
        f"📌 任务：{edict.title}",
        f"状态：{label} · {created_str} · 耗时 {_fmt_duration(duration)}",
    ]
    if edict.creator:
        head_lines.append(f"创建者：{edict.creator}")

    # 子任务概览
    body_lines: list[str] = ["", f"子任务（{len(subtasks)} 个）："]
    if not subtasks:
        body_lines.append("  (无)")
    else:
        for s in subtasks:
            icon = _SUBTASK_STATUS_ICON.get(s.status, "·")
            verdict = f" [{s.verdict_status}]" if s.verdict_status else ""
            desc = (s.description or "").strip().replace("\n", " ")[:50] or "(无描述)"
            body_lines.append(f"{icon} {s.assignee} · {desc}{verdict}")

    # 摘要：workspace summary.md → push_archive 终局消息 → subtask.result 拼接 → 诊断兜底
    body_lines.append("")
    body_lines.append("摘要：")
    from paimon.shades._task_summary import resolve_task_summary
    summary_text = await resolve_task_summary(irminsul, task_id, subtasks)
    body_lines.append(summary_text)

    return "\n".join(head_lines + body_lines)
