"""任务摘要回溯：给 /task-index、WebUI 详情面板共用的纯函数。

数据落点：
- 写代码任务 → 时执归档时写 `.paimon/tasks/<id>/summary.md`
- 所有任务 → 管线末尾 `_notify_progress` 把 `_compose_final` 的产物经 march.ring_event
  推到 push_archive（`actor='四影'`，`extra.task_id=<id>`）
- 子任务级 → asmoday 把 _STAGE_ROUTER 派出的影函数返回写进 `task_subtasks.result`

任何一个有内容就够展示。这个模块负责按"信息密度"逐级回退。
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from loguru import logger

if TYPE_CHECKING:
    from paimon.foundation.irminsul import Irminsul
    from paimon.foundation.irminsul.task import Subtask


# 完成性提示词：用于在 push_archive 候选里挑"终局摘要"消息（vs round 进度 / 启动消息）
_FINAL_HINTS = ("🎉", "💥", "已达最大轮次", "任务已取消", "完成（rounds=", "完成 (rounds=")


async def resolve_task_summary(
    irminsul: "Irminsul",
    task_id: str,
    subtasks: list["Subtask"],
    *,
    max_chars: int = 1500,
) -> str:
    """按优先级返回任务摘要：

    1. workspace `summary.md`（写代码任务有；结构化最完整）
    2. push_archive 里 actor='四影' 且 task_id 匹配的最终消息（_compose_final 产物）
    3. 拼接所有 completed subtask.result（兜底）
    4. 诊断性提示（区分"全空"vs"暂无"两种空状态）
    """
    # 1. workspace summary.md
    try:
        from paimon.foundation.task_workspace import (
            get_workspace_path, workspace_exists,
        )
        if workspace_exists(task_id):
            sm = get_workspace_path(task_id) / "summary.md"
            if sm.exists():
                txt = sm.read_text(encoding="utf-8").strip()
                if txt:
                    return txt[:max_chars]
    except Exception as e:
        logger.debug("[task_summary] 读 summary.md 失败 task={}: {}", task_id[:8], e)

    # 2. push_archive 反查
    try:
        recs = await irminsul.push_archive_list(actor="四影", limit=200)
        prefix = task_id[:8]
        # 严格匹配优先 + 老数据按 message 文本 'task=<prefix>' 兼容
        candidates = []
        for r in recs:
            if (r.extra or {}).get("task_id") == task_id:
                candidates.append(r)
                continue
            if f"task={prefix}" in (r.message_md or ""):
                candidates.append(r)

        # 终局消息优先（含完成/失败/超轮符号），其次最新
        finals = [r for r in candidates if any(h in r.message_md for h in _FINAL_HINTS)]
        chosen = finals[0] if finals else (candidates[0] if candidates else None)
        if chosen and chosen.message_md and chosen.message_md.strip():
            return chosen.message_md.strip()[:max_chars]
    except Exception as e:
        logger.debug("[task_summary] push_archive 反查失败 task={}: {}", task_id[:8], e)

    # 3. 拼 completed subtask.result
    parts: list[str] = []
    for s in subtasks:
        if s.status == "completed":
            r = (s.result or "").strip()
            if r:
                parts.append(f"【{s.assignee}】\n{r[:600]}")
    if parts:
        return "\n\n---\n\n".join(parts)[:max_chars]

    # 4. 诊断性兜底
    completed_subs = [s for s in subtasks if s.status == "completed"]
    if completed_subs and all(not (s.result or "").strip() for s in completed_subs):
        return (
            "(所有 archon 子任务都返回了空 result —— 疑似 archon 内 LLM 终局消息抓取失败；"
            "可在 WebUI `/dashboard` 推送抽屉里查 actor=四影 的归档记录看是否有线索)"
        )
    return "(暂无产物摘要)"
