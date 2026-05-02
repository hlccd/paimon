"""四影 · 裁决解析 + 状态行渲染：水神 verdict 解读、阶段进度文本。"""
from __future__ import annotations

import asyncio
import time
from typing import TYPE_CHECKING
from uuid import uuid4

from loguru import logger

from paimon.config import config
from paimon.core.authz.keywords import classify_batch_reply
from paimon.foundation.irminsul.task import TaskEdict
from paimon.shades import asmoday, istaroth, jonova, naberius

from .._plan import Plan, mark_downstream_skipped
from .._saga import run_compensations
from .._verdict import (
    LEVEL_PASS,
    ReviewVerdict,
    find_last_verdict_producer,
    parse_verdict,
)


class _VerdictMixin:
    def _stage_status_line(self, plan: Plan, results: dict[str, str]) -> str:
        """三阶段 verdict 浓缩成一行（给用户看）。非三阶段 DAG 返回简短节点统计。"""
        stages = [
            ("spec", "review_spec"),
            ("design", "review_design"),
            ("code", "review_code"),
        ]
        by_stage = {
            s: None for _, s in stages  # review_spec → verdict level or None
        }
        for sub in plan.subtasks:
            if sub.assignee != "水神":
                continue
            raw = results.get(sub.id, "").strip()
            if not raw:
                continue
            for _, rv in stages:
                if sub.description.startswith(f"[STAGE:{rv}]"):
                    try:
                        by_stage[rv] = parse_verdict(raw).level
                    except Exception:
                        pass
                    break

        if all(by_stage[rv] is None for _, rv in stages):
            # 非三阶段 DAG
            total = len(plan.subtasks)
            completed = sum(1 for s in plan.subtasks if s.status == "completed")
            return f"{completed}/{total} 完成"

        icon_map = {"pass": "✓", "revise": "△", "redo": "✗", None: "·"}
        parts = []
        for stage, rv in stages:
            parts.append(f"{stage} {icon_map.get(by_stage[rv], '?')}")
        return " / ".join(parts)

    def _resolve_verdict(self, plan: Plan, results: dict[str, str]) -> ReviewVerdict:
        """聚合"本轮实际跑过且有产物的水神节点"，取**最坏 level** 的 verdict。

        - 只看 results 有非空产物的水神节点（已实际执行）
        - 从中取 level 最严重的（redo > revise > pass）
        - 三阶段 DAG 下任一 review 非 pass 都会让整轮回炉（而不是只看末尾 review）
        """
        water_nodes_with_output = [
            s for s in plan.subtasks
            if s.assignee == "水神" and results.get(s.id, "").strip()
        ]
        if not water_nodes_with_output:
            if find_last_verdict_producer(plan.subtasks) is None:
                return ReviewVerdict(
                    level=LEVEL_PASS, summary="(无水神评审节点，默认通过)",
                )
            return ReviewVerdict(
                level=LEVEL_PASS,
                summary="(水神节点无产物，跳过评审视为通过)",
            )

        # 三阶段聚合：任一 review 非 pass → 整轮非 pass；取最坏 level 的 verdict 返回。
        # 没有这个聚合会导致 review_spec redo 但 review_code pass 时错判"整轮 pass"。
        # （MVP 代价：当前 asmoday 仍会跑完所有节点再汇总；阶段门控留 Phase 2。）
        _LEVEL_RANK = {"pass": 0, "revise": 1, "redo": 2}
        parsed_list = [parse_verdict(results[s.id]) for s in water_nodes_with_output]
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
                    sid, verdict_status=node_status, actor="水神",
                )
            except Exception as e:
                logger.warning("[四影] 标记 verdict 失败 sub={}: {}", sid, e)
