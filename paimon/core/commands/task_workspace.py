"""任务工作区指令：/task-merge 合并代码 / /task-discard 丢弃 / /task-summary 看产物。

只操作 .paimon/tasks/{id}/ 目录；不动世界树 task_edicts。
"""
from __future__ import annotations

from ._dispatch import CommandContext, command


def _resolve_task_id_prefix(prefix: str) -> str | None:
    """按前缀找 workspace（.paimon/tasks/ 下的子目录名）。多个匹配返回 None。"""
    from paimon.foundation.task_workspace import _workspace_root
    prefix = prefix.strip()
    if not prefix:
        return None
    root = _workspace_root()
    if not root.exists():
        return None
    matches = [d.name for d in root.iterdir() if d.is_dir() and d.name.startswith(prefix)]
    return matches[0] if len(matches) == 1 else None


@command("task-merge")
async def cmd_task_merge(ctx: CommandContext) -> str:
    """/task-merge <task_id前缀> [--overwrite]

    把 .paimon/tasks/{id}/code/ 下的文件合并到当前工作目录。
    """
    from paimon.foundation.task_workspace import merge_to_cwd, get_workspace_path

    args = ctx.args.strip().split()
    if not args:
        return "用法: /task-merge <task_id前缀> [--overwrite]"
    overwrite = "--overwrite" in args
    args = [a for a in args if not a.startswith("--")]
    if not args:
        return "缺少 task_id 前缀"

    task_id = _resolve_task_id_prefix(args[0])
    if not task_id:
        return f"未找到 task 工作区匹配 '{args[0]}'（或多个匹配）"

    ws = get_workspace_path(task_id)
    if not ws.exists():
        return f"工作区不存在: {ws}"

    result = merge_to_cwd(task_id, overwrite=overwrite)
    parts = [f"merge task #{task_id[:8]}:"]
    if result["copied"]:
        parts.append(f"  ✅ 合并 {len(result['copied'])} 个文件")
        for f in result["copied"][:10]:
            parts.append(f"     + {f}")
        if len(result["copied"]) > 10:
            parts.append(f"     ... 共 {len(result['copied'])} 个")
    if result["skipped"]:
        parts.append(f"  ⏸️  跳过 {len(result['skipped'])} 个（目标已存在且内容不同；加 --overwrite 覆盖）")
        for f in result["skipped"][:5]:
            parts.append(f"     - {f}")
    if result["errors"]:
        parts.append(f"  ❌ 错误 {len(result['errors'])} 条:")
        for e in result["errors"][:5]:
            parts.append(f"     ! {e}")
    if not any((result["copied"], result["skipped"], result["errors"])):
        parts.append("  (无变化)")
    return "\n".join(parts)


@command("task-discard")
async def cmd_task_discard(ctx: CommandContext) -> str:
    """/task-discard <task_id前缀> — 丢弃工作区（删除 .paimon/tasks/{id}/ 目录）"""
    from paimon.foundation.task_workspace import cleanup_workspace, get_workspace_path

    prefix = ctx.args.strip()
    if not prefix:
        return "用法: /task-discard <task_id前缀>"

    task_id = _resolve_task_id_prefix(prefix)
    if not task_id:
        return f"未找到 task 工作区匹配 '{prefix}'（或多个匹配）"

    removed = cleanup_workspace(task_id)
    return f"已丢弃 task #{task_id[:8]}" if removed else "工作区未找到"


@command("task-summary")
async def cmd_task_summary(ctx: CommandContext) -> str:
    """/task-summary <task_id前缀> — 查看任务 summary.md"""
    from paimon.foundation.task_workspace import get_workspace_path

    prefix = ctx.args.strip()
    if not prefix:
        # 列所有 workspace
        from paimon.foundation.task_workspace import _workspace_root
        root = _workspace_root()
        if not root.exists():
            return "暂无任务工作区"
        dirs = sorted((d.name for d in root.iterdir() if d.is_dir()))
        if not dirs:
            return "暂无任务工作区"
        return "任务工作区:\n" + "\n".join(f"  {d}" for d in dirs[:20])

    task_id = _resolve_task_id_prefix(prefix)
    if not task_id:
        return f"未找到 task 工作区匹配 '{prefix}'"
    summary = get_workspace_path(task_id) / "summary.md"
    if not summary.exists():
        return f"summary.md 不存在（任务可能未完成归档）: {summary}"
    return summary.read_text(encoding="utf-8")[:5000]
