"""原石统计指令 /stat：全局 + 当前会话 token 用量与花费汇总。"""
from __future__ import annotations

from paimon.state import state

from ._dispatch import CommandContext, command


def _format_stats(stats: dict, label: str) -> list[str]:
    """通用统计渲染：调用次数 / 输入输出 token / 缓存 / 总花费 / 按 component 拆分。"""
    total_tok = stats["total_input_tokens"] + stats["total_output_tokens"]
    lines = [
        f"{label}:",
        f"  调用: {stats['count']}次",
        f"  输入: {stats['total_input_tokens']:,} token",
        f"  输出: {stats['total_output_tokens']:,} token",
    ]
    cw = stats.get("total_cache_creation_tokens", 0)
    cr = stats.get("total_cache_read_tokens", 0)
    if cw or cr:
        lines.append(f"  缓存写入: {cw:,} / 缓存命中: {cr:,}")
    lines.append(f"  总token: {total_tok:,}")
    lines.append(f"  估算花费: ~${stats['total_cost_usd']:.4f}")
    if stats.get("by_component"):
        for comp, data in stats["by_component"].items():
            lines.append(f"    {comp}: {data['count']}次 ~${data['cost_usd']:.4f}")
    return lines


@command("stat")
async def cmd_stat(ctx: CommandContext) -> str:
    """/stat — 原石统计 + 用途分布 + 当前会话单独段。"""
    primogem = state.primogem
    if not primogem:
        return "原石模块未启用"

    session_mgr = state.session_mgr
    current = session_mgr.get_current(ctx.msg.channel_key) if session_mgr else None

    g = await primogem.get_global_stats()
    lines = _format_stats(g, "原石统计 (全局)")

    purpose_stats = await primogem.get_purpose_stats()
    if purpose_stats:
        lines.append("  按用途:")
        for purpose, data in purpose_stats.items():
            lines.append(f"    {purpose}: {data['count']}次 ~${data['cost_usd']:.4f}")

    if current:
        s = await primogem.get_session_stats(current.id)
        if s["count"] > 0:
            lines.append("")
            lines.extend(_format_stats(s, f"当前会话 ({current.name})"))

    return "\n".join(lines)
