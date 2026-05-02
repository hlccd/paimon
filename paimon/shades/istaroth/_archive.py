"""时执 · Istaroth — 任务归档：状态 final + audit 写入 + summary.md 生成。"""
from __future__ import annotations

import json

from loguru import logger

from paimon.foundation.irminsul import Irminsul
from paimon.foundation.irminsul.task import TaskEdict


async def archive(
    task: TaskEdict,
    irminsul: Irminsul,
    *,
    failure_reason: str | None = None,
    rounds: int | None = None,
) -> None:
    """四影管线末尾：归档任务 + 写审计。

    failure_reason 非空时走失败路径：任务状态标 failed，审计 event 用 task_failed。
    成功路径下额外接受 rounds（总轮次）用于审计记录。
    """
    final_status = "failed" if failure_reason else "completed"
    await irminsul.task_update_status(task.id, status=final_status, actor="时执")

    subtasks = await irminsul.subtask_list(task.id)
    summary = {
        "total_subtasks": len(subtasks),
        "completed": sum(1 for s in subtasks if s.status == "completed"),
        "failed": sum(1 for s in subtasks if s.status == "failed"),
        "skipped": sum(1 for s in subtasks if s.status == "skipped"),
        "rounds": rounds if rounds is not None else max(
            (s.round for s in subtasks), default=1,
        ),
    }
    if failure_reason:
        summary["failure_reason"] = failure_reason[:500]

    await irminsul.audit_append(
        event_type="task_failed" if failure_reason else "task_completed",
        payload=summary,
        task_id=task.id,
        session_id=task.session_id,
        actor="时执",
    )

    await irminsul.task_update_lifecycle(task.id, stage="cold", actor="时执")

    # 若任务有关联工作区（三阶段写代码任务），生成 summary.md 供派蒙呈现
    try:
        await _maybe_write_task_summary(task, subtasks, summary, failure_reason)
    except Exception as e:
        logger.warning("[时执] 生成 summary.md 失败（不影响归档）: {}", e)

    if failure_reason:
        logger.warning(
            "[时执] 失败归档 task={} rounds={} reason={}",
            task.id, summary["rounds"], failure_reason[:120],
        )
    else:
        logger.info(
            "[时执] 归档完成 task={} rounds={} (子任务: {}完成/{}失败/{}跳过)",
            task.id, summary["rounds"],
            summary["completed"], summary["failed"], summary["skipped"],
        )


async def _maybe_write_task_summary(
    task: TaskEdict, subtasks: list, summary: dict,
    failure_reason: str | None,
) -> None:
    """若 .paimon/tasks/{id}/ 存在 → 生成 summary.md（派蒙呈现用）。"""
    from paimon.foundation.task_workspace import (
        get_workspace_path,
        list_workspace_files,
        workspace_exists,
    )
    if not workspace_exists(task.id):
        return
    workspace = get_workspace_path(task.id)

    lines = [
        f"# 任务总结: {task.title}",
        "",
        f"**状态**: {'✅ 完成' if not failure_reason else '❌ 失败'}",
        f"**轮数**: {summary['rounds']}",
        f"**子任务**: {summary['completed']} 完成 / {summary['failed']} 失败 / {summary['skipped']} 跳过",
        "",
        "## 产物",
        "",
    ]

    for name in ("spec.md", "design.md"):
        p = workspace / name
        if p.exists():
            kb = p.stat().st_size / 1024
            lines.append(f"- {name} ({kb:.1f} KB) — {p}")

    files = list_workspace_files(task.id)
    if files:
        lines.append(f"- code/ ({len(files)} files)")
        for f in files[:30]:
            try:
                rel = f.relative_to(workspace / "code")
                kb = f.stat().st_size / 1024
                lines.append(f"  - {rel} ({kb:.1f} KB)")
            except (ValueError, OSError):
                pass

    # 审查历史（从 *.check.json 读）
    lines.append("")
    lines.append("## 审查结果")
    lines.append("")
    for name in ("spec.check.json", "design.check.json", "code.check.json"):
        p = workspace / name
        if not p.exists():
            continue
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            sev = data.get("severity_counts", {})
            lines.append(
                f"- **{name.replace('.check.json', '')}**: {data.get('level', '?')} "
                f"(P0:{sev.get('P0', 0)} P1:{sev.get('P1', 0)} "
                f"P2:{sev.get('P2', 0)} P3:{sev.get('P3', 0)})"
            )
        except (json.JSONDecodeError, OSError):
            pass

    # 自检
    sc_path = workspace / "self-check.log"
    if sc_path.exists():
        lines.append("")
        lines.append("## 自检")
        lines.append("")
        sc_text = sc_path.read_text(encoding="utf-8")[:2000]
        lines.append("```")
        lines.append(sc_text)
        lines.append("```")

    if failure_reason:
        lines.append("")
        lines.append("## ⚠️ 失败原因")
        lines.append(failure_reason[:1000])

    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append(
        f"**下一步**: `/task-merge {task.id[:12]}` 合并到工作目录，"
        f"或 `/task-discard {task.id[:12]}` 丢弃"
    )

    summary_path = workspace / "summary.md"
    summary_path.write_text("\n".join(lines), encoding="utf-8")
    logger.info("[时执] summary.md 已生成: {}", summary_path)
