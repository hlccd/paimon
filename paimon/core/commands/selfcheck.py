"""三月自检指令 /selfcheck：默认 Quick（秒级）；--deep 走 Deep（异步后台）。"""
from __future__ import annotations

from paimon.state import state

from ._dispatch import CommandContext, command


@command("selfcheck")
async def cmd_selfcheck(ctx: CommandContext) -> str:
    """三月·自检入口。/selfcheck [--deep] [--help]

    默认跑 Quick（秒级组件探针）；`--deep` 启动 Deep（调 check skill 跑项目体检，
    异步后台执行，结果见 WebUI `/selfcheck` 面板 + 📨 推送）。
    """
    svc = state.selfcheck
    if not svc:
        return "自检服务未启用（config.selfcheck_enabled=false 或未初始化）"

    args = (ctx.args or "").strip()
    # 按 token 拆而不是 startswith：避免 "/selfcheck deep foo" 的 foo 被当 Quick
    tokens = args.split(maxsplit=1)
    first = tokens[0] if tokens else ""
    rest = tokens[1].strip() if len(tokens) > 1 else ""

    if first in ("--help", "-h", "help"):
        return (
            "/selfcheck 用法:\n"
            "  /selfcheck                  - Quick 自检（秒级，组件状态表）\n"
            "  /selfcheck --help           - 本帮助\n"
            "\n"
            "面板: WebUI → /selfcheck（Quick 历史 + 详情）\n"
            "\n"
            "注：Deep 自检暂缓——当前 mimo-v2-omni 对 check skill 的\n"
            "N+M+K 多轮循环执行不充分，跑半截就停。换 Claude Opus\n"
            "级模型验证过再启用（见 docs/todo.md）。底层代码保留，\n"
            "config.selfcheck_deep_hidden=False 重启即可恢复手动入口。"
        )

    if first in ("--deep", "deep"):
        # Deep 暂缓开关：docs/todo.md §三月·自检·Deep 暂缓
        # 当前 mimo-v2-omni 模型执行不充分；底层 _run_deep_inner 代码保留
        # 未来换 Claude Opus 级模型验证后可设 selfcheck_deep_hidden=False 恢复
        from paimon.config import config as _cfg
        if getattr(_cfg, "selfcheck_deep_hidden", True):
            return (
                "Deep 自检当前暂缓（LLM 执行不充分）。\n"
                "Quick 自检可用（直接跑 /selfcheck）。\n"
                "恢复 Deep 步骤：\n"
                "  1. 给 deep pool 配 Claude Opus 级模型\n"
                "  2. .env 设 SELFCHECK_DEEP_HIDDEN=false\n"
                "  3. 重启 paimon"
            )
        # Deep：非阻塞启动，立即返回
        result = await svc.run_deep(
            args=rest or None, triggered_by="user",
        )
        if not result["started"]:
            if result["reason"] == "already_running":
                return (
                    "已有 Deep 自检在进行中，请等待完成后再试\n"
                    "（见 WebUI /selfcheck 面板 Deep Tab）"
                )
            return f"Deep 启动失败: {result['reason']}"
        return (
            f"🔬 Deep 自检已启动 run={result['run_id']}\n"
            f"后台跑 check skill（可能 3~15 分钟），完成后推📨 推送。\n"
            f"面板实时查看: /selfcheck"
        )

    # 默认 Quick
    run = await svc.run_quick(triggered_by="user")
    if run.status != "completed":
        return f"Quick 自检异常: {run.error or run.status}"

    summary = run.quick_summary or {}
    overall = summary.get("overall", "?")
    warnings = summary.get("warnings", [])
    components = summary.get("components", [])

    icon = {"ok": "✅", "degraded": "⚠️", "critical": "🚨"}.get(overall, "❓")
    lines = [
        f"{icon} Quick 自检完成 run={run.id[:8]} · 耗时 {run.duration_seconds*1000:.0f}ms",
        f"整体状态: {overall}",
        "",
        "组件状态:",
    ]
    for c in components:
        cicon = {"ok": "✓", "degraded": "△", "critical": "✗"}.get(
            c.get("status", "?"), "?",
        )
        lines.append(
            f"  {cicon} {c.get('name', '?'):<16} "
            f"[{c.get('status', '?')}] {c.get('latency_ms', 0):.1f}ms"
        )
    if warnings:
        lines.append("")
        lines.append("⚠️ 告警:")
        for w in warnings:
            lines.append(f"  - {w}")
    lines.append("")
    lines.append("详情/历史: WebUI /selfcheck")
    return "\n".join(lines)
