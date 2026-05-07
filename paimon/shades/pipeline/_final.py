"""四影 · 最终产物组装 + 任务实体创建：_compose_final / _create_task。"""
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

_REVIEW_STAGES = {"review_spec", "review_design", "review_code"}


class _FinalMixin:
    def _compose_final(
        self,
        plan: Plan | None,
        results: dict[str, str],
        verdict: ReviewVerdict | None,
        round_cap_hit: bool,
    ) -> str:
        if plan is None:
            return "(无产物)"

        by_id = plan.by_id
        has_downstream: set[str] = set()
        for s in plan.subtasks:
            for d in (s.deps or []):
                if d in by_id:
                    has_downstream.add(d)
        terminals = [
            s for s in plan.subtasks
            if s.id not in has_downstream and results.get(s.id)
        ]
        non_review_terms = [t for t in terminals if t.assignee not in _REVIEW_STAGES]
        review_terms = [t for t in terminals if t.assignee in _REVIEW_STAGES]

        parts: list[str] = []
        for t in non_review_terms:
            parts.append(results[t.id])
        if not parts and review_terms:
            for t in review_terms:
                parts.append(results[t.id])
        if not parts:
            for sid, r in results.items():
                if r:
                    parts.append(r)

        body = "\n\n---\n\n".join(parts).strip()

        # 终端产物太单薄（LLM 可能把"归档/整理/入库"当终点，真答案在上游）→ 拼全节点
        _ADMIN_HINTS = ("已整理", "已归档", "存入知识库", "整理完毕", "归档完成", "已入库")
        looks_admin = any(h in body for h in _ADMIN_HINTS)
        if len(body) < 200 or looks_admin:
            all_parts: list[str] = []
            for s in plan.subtasks:
                r = results.get(s.id, "")
                if r and r not in all_parts:
                    all_parts.append(f"【{s.assignee}】\n{r}")
            if all_parts:
                body = "\n\n---\n\n".join(all_parts).strip()

        if round_cap_hit and verdict is not None:
            body += (
                f"\n\n---\n"
                f"⚠️ 已达最大轮次（level={verdict.level}），返回最后一轮产物。\n"
                f"评审意见：{verdict.summary[:400]}"
            )
        return body or "(产物为空)"

    async def _create_task(
        self,
        user_input: str,
        session_id: str,
    ) -> TaskEdict:
        # LLM 生成短标题供 ack / notice / task-list 显示。
        # 失败降级为 user_input 截断；慢任务多这一次 LLM 调用不影响整体耗时。
        title = ""
        try:
            t = await self._model.generate_title(user_input, session_id=session_id)
            if t:
                title = t.strip().replace("\n", " ")[:30]
        except Exception as e:
            logger.debug("[四影·create_task] 短标题生成失败: {}", e)
        if not title:
            title = user_input.strip().replace("\n", " ")[:60]

        description = user_input
        creator = "派蒙"
        task = TaskEdict(
            id=uuid4().hex[:12],
            title=title,
            description=description,
            creator=creator,
            status="pending",
            session_id=session_id,
            created_at=time.time(),
            updated_at=time.time(),
        )
        await self._irminsul.task_create(task, actor=creator)
        return task
