"""四影 · 裁决解析 + 状态行渲染：评审 verdict 解读、阶段进度文本。"""
from __future__ import annotations

import asyncio
import time
from typing import TYPE_CHECKING
from uuid import uuid4

from loguru import logger

from paimon.config import config
from paimon.core.authz.keywords import classify_batch_reply
from paimon.foundation.irminsul.task import TaskEdict
from paimon.shades import asmoday, istaroth, naberius

from .._plan import Plan, mark_downstream_skipped
from ..istaroth import run_compensations
from .._verdict import (
    LEVEL_PASS,
    ReviewVerdict,
    find_last_verdict_producer,
    parse_verdict,
)

_REVIEW_STAGES = {"review_proposal"}


class _VerdictMixin:
    def _stage_status_line(self, plan: Plan, results: dict[str, str]) -> str:
        """评审节点的 verdict 浓缩成一行（给用户看）。无评审节点返回简短节点统计。

        当前只有 review_proposal 一个评审 stage，简化为列出每个 review_proposal
        节点的 verdict（实际场景一般每轮只有 1 个 review_proposal 节点）。
        """
        review_subs = [s for s in plan.subtasks if s.assignee in _REVIEW_STAGES]
        if not review_subs:
            total = len(plan.subtasks)
            completed = sum(1 for s in plan.subtasks if s.status == "completed")
            return f"{completed}/{total} 完成"

        icon_map = {"pass": "✓", "revise": "△", "redo": "✗", None: "·"}
        parts = []
        for sub in review_subs:
            level = None
            raw = results.get(sub.id, "").strip()
            if raw:
                try:
                    level = parse_verdict(raw).level
                except Exception:
                    pass
            parts.append(f"review_proposal {icon_map.get(level, '·')}")
        return " / ".join(parts)

    def _resolve_verdict(self, plan: Plan, results: dict[str, str]) -> ReviewVerdict:
        """聚合所有 review_proposal 节点的 verdict，取**最坏 level**。

        - 只看 results 有非空产物的评审节点（已实际执行）
        - 从中取 level 最严重的（redo > revise > pass）
        """
        review_nodes_with_output = [
            s for s in plan.subtasks
            if s.assignee in _REVIEW_STAGES and results.get(s.id, "").strip()
        ]
        if not review_nodes_with_output:
            if find_last_verdict_producer(plan.subtasks) is None:
                return ReviewVerdict(
                    level=LEVEL_PASS, summary="(无评审节点，默认通过)",
                )
            return ReviewVerdict(
                level=LEVEL_PASS,
                summary="(评审节点无产物，跳过评审视为通过)",
            )

        _LEVEL_RANK = {"pass": 0, "revise": 1, "redo": 2}
        parsed_list = [parse_verdict(results[s.id]) for s in review_nodes_with_output]
        worst = max(parsed_list, key=lambda v: _LEVEL_RANK.get(v.level, 0))
        return worst

    async def _annotate_verdict_on_subtasks(
        self, plan: Plan, verdict: ReviewVerdict,
    ) -> None:
        if not verdict.issues:
            return
        ids = {s.id for s in plan.subtasks}
        status_map = {
            "pass": "passed",
            "revise": "needs_revise",
            "redo": "needs_redo",
        }
        node_status = status_map.get(verdict.level, "")
        if not node_status:
            return
        for issue in verdict.issues:
            sid = issue.get("subtask_id")
            if not sid or sid not in ids:
                continue
            try:
                await self._irminsul.subtask_update_verdict(
                    sid, verdict_status=node_status, actor="评审",
                )
            except Exception as e:
                logger.warning("[四影] 标记 verdict 失败 sub={}: {}", sid, e)
