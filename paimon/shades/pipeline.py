"""四影管线 — 闭环结构

```
[环1·入口审] 死执·review → 拒绝即归档
     ↓
[环2·主循环 N 轮]
   生执·plan → 死执·scan_plan → 派蒙·batch_ask（批量敏感授权）
     → 空执·dispatch(拓扑并发 + 失败重试) → 解析水神 verdict
     pass → 跳出
     revise/redo → 回生执下一轮（失败节点触发改派）
     round≥cap → 尽力而为返回最后一轮产物
     ↓
[环3·归档] 时执·archive（成功/失败都进；失败先跑 saga 补偿）
```

环 2 的核心是"草水雷多轮循环"（docs/aimon.md §2.3）。
"""
from __future__ import annotations

import asyncio
import time
from uuid import uuid4

from loguru import logger

from paimon.config import config
from paimon.core.authz.cache import AuthzCache
from paimon.core.authz.keywords import BatchReplyResult, classify_batch_reply
from paimon.foundation.irminsul import Irminsul
from paimon.foundation.irminsul.task import TaskEdict
from paimon.llm.model import Model
from paimon.shades import asmoday, istaroth, jonova, naberius

from ._plan import Plan, mark_downstream_skipped
from ._saga import run_compensations
from ._verdict import (
    LEVEL_PASS,
    ReviewVerdict,
    find_last_verdict_producer,
    parse_verdict,
)


class ShadesPipeline:

    def __init__(
        self,
        model: Model,
        irminsul: Irminsul,
        *,
        channel=None,          # paimon.channels.base.Channel | None
        chat_id: str = "",
        authz_cache: AuthzCache | None = None,
        user_id: str = "default",
        batch_ask_timeout: float = 60.0,  # 批量询问略宽松
    ):
        self._model = model
        self._irminsul = irminsul
        self._channel = channel
        self._chat_id = chat_id
        self._authz_cache = authz_cache
        self._user_id = user_id
        self._batch_ask_timeout = batch_ask_timeout

    async def run(
        self,
        user_input: str,
        session_id: str = "",
        escalation_reason: str | None = None,
    ) -> str:
        task = await self._create_task(user_input, session_id, escalation_reason)
        if escalation_reason:
            logger.info(
                "[四影] 魔女会转入 task={} reason={}",
                task.id, escalation_reason,
            )
        logger.info("[四影] 管线启动 task={} title={}", task.id, task.title[:60])

        max_rounds = max(1, int(getattr(config, "shades_max_rounds", 3)))
        plan: Plan | None = None
        verdict: ReviewVerdict | None = None
        last_results: dict[str, str] = {}
        completed_ids: set[str] = set()  # 管线生命周期内所有"成功完成"的节点 id（跨轮）
        round_idx = 1
        round_cap_hit = False

        try:
            # 环 1：入口安全审
            safe, reason = await jonova.review(task, self._model, self._irminsul)
            if not safe:
                await self._irminsul.task_update_status(task.id, status="rejected", actor="死执")
                await istaroth.archive(
                    task, self._irminsul,
                    failure_reason=f"死执拒绝: {reason}",
                    rounds=0,
                )
                return f"请求未通过安全审查: {reason}"

            # 环 2：主循环
            while round_idx <= max_rounds:
                plan = await naberius.plan(
                    task, self._model, self._irminsul,
                    previous_plan=plan, verdict=verdict, round=round_idx,
                )

                if round_idx == 1:
                    await self._irminsul.task_update_status(
                        task.id, status="running", actor="空执",
                    )

                # 死执 scan + 派蒙批量授权
                scan_ok = await self._batch_authorize(task, plan, session_id)
                if not scan_ok:
                    # 所有敏感节点都被拒 → 视作用户主动取消
                    await istaroth.archive(
                        task, self._irminsul,
                        failure_reason="用户拒绝了全部敏感操作",
                        rounds=round_idx,
                    )
                    return "任务已取消（你拒绝了全部敏感操作）。"

                last_results = await asmoday.dispatch(
                    task, plan, self._model, self._irminsul,
                )
                # 记录本轮真正成功的节点 id（跨轮累积，saga 补偿时需要）
                # asmoday 已把 status 同步到 in-memory Subtask，只收 completed 的
                for s in plan.subtasks:
                    if s.status == "completed":
                        completed_ids.add(s.id)

                verdict = self._resolve_verdict(plan, last_results)
                logger.info(
                    "[四影] round {} verdict={} issues={}",
                    round_idx, verdict.level, len(verdict.issues),
                )
                await self._annotate_verdict_on_subtasks(plan, verdict)

                await self._irminsul.audit_append(
                    event_type="shades_round_verdict",
                    payload={
                        "round": round_idx,
                        "level": verdict.level,
                        "issue_count": len(verdict.issues),
                        "summary": verdict.summary[:300],
                    },
                    task_id=task.id, session_id=task.session_id, actor="四影",
                )

                if verdict.level == LEVEL_PASS:
                    break

                if round_idx >= max_rounds:
                    round_cap_hit = True
                    logger.warning(
                        "[四影] round cap 触顶 ({}) 仍未 pass，返回最后一轮产物",
                        max_rounds,
                    )
                    await self._irminsul.audit_append(
                        event_type="shades_round_cap_hit",
                        payload={"max_rounds": max_rounds, "final_level": verdict.level},
                        task_id=task.id, session_id=task.session_id, actor="四影",
                    )
                    break

                round_idx += 1

            # 环 3：成功归档
            final = self._compose_final(plan, last_results, verdict, round_cap_hit)
            await istaroth.archive(task, self._irminsul, rounds=round_idx)
            logger.info("[四影] 管线完成 task={} rounds={}", task.id, round_idx)
            return final

        except Exception as e:
            # 环 3：失败路径 — 先 saga 补偿再归档
            logger.error("[四影] 管线异常 task={}: {}", task.id, e)
            try:
                all_subs = await self._irminsul.subtask_list(task.id)
                await run_compensations(
                    task, all_subs, completed_ids,
                    self._model, self._irminsul,
                    trigger_reason=f"管线异常: {e}",
                )
            except Exception as saga_err:
                logger.error("[四影] saga 补偿本身异常: {}", saga_err)

            try:
                await istaroth.archive(
                    task, self._irminsul,
                    failure_reason=str(e),
                    rounds=round_idx,
                )
            except Exception as arc_err:
                logger.error("[四影] 失败归档本身异常: {}", arc_err)
            return f"任务执行失败: {e}"

    # ---------------- batch authz ----------------

    async def _batch_authorize(
        self, task: TaskEdict, plan: Plan, session_id: str,
    ) -> bool:
        """死执 scan + 派蒙批量询问。

        返回 False 表示"用户拒绝全部" / "管线应终止"；
        返回 True 表示"可以继续 dispatch"（plan 可能被原地剔除部分节点）。
        """
        # 依赖不全就跳过批量授权（如无 channel 或 cache 未注入，仍允许降级运行）
        if self._channel is None or self._authz_cache is None:
            return True

        scan = jonova.scan_plan(
            plan, self._authz_cache,
            user_id=self._user_id, session_id=session_id,
        )

        # 先剔除 permanent_deny 命中的节点
        if scan.blocked_ids:
            await self._drop_blocked_nodes(plan, scan.blocked_ids, task)

        # 无待问项 → 直接通过
        if not scan.has_questions:
            return True

        # 询问用户
        prompt = jonova.format_scan_prompt(scan.items_to_ask)
        total = len(scan.items_to_ask)

        try:
            reply = await self._channel.ask_user(
                self._chat_id, prompt, timeout=self._batch_ask_timeout,
            )
        except NotImplementedError:
            logger.warning(
                "[四影·batch_ask] 频道 {} 未支持 ask_user，保守拒绝全部",
                getattr(self._channel, "name", "?"),
            )
            return await self._reject_all_sensitive(plan, scan.items_to_ask, task)
        except asyncio.TimeoutError:
            logger.info(
                "[四影·batch_ask] 询问超时 ({}s)，保守拒绝",
                self._batch_ask_timeout,
            )
            return await self._reject_all_sensitive(plan, scan.items_to_ask, task)

        result = classify_batch_reply(reply, total=total)
        logger.info(
            "[四影·batch_ask] 用户答复='{}' → {} (indices={} perm={})",
            reply[:60], result.kind, result.allow_indices, result.permanent,
        )
        await self._irminsul.audit_append(
            event_type="shades_batch_ask",
            payload={
                "total": total,
                "reply_preview": reply[:200],
                "kind": result.kind,
                "allow_indices": result.allow_indices,
                "permanent": result.permanent,
            },
            task_id=task.id, session_id=task.session_id, actor="四影·batch_ask",
        )
        return await self._apply_batch_result(
            plan, scan.items_to_ask, result, task, session_id,
        )

    async def _apply_batch_result(
        self,
        plan: Plan,
        items: list,  # list[ScanItem]
        result: BatchReplyResult,
        task: TaskEdict,
        session_id: str,
    ) -> bool:
        """按用户答复把对应节点标 allowed 或 从 plan 剔除。"""
        assert self._authz_cache is not None

        if result.kind in ("all_allow", "all_perm_allow"):
            for item in items:
                await self._remember_decision(
                    item, "allow", permanent=(result.kind == "all_perm_allow"),
                    session_id=session_id, task=task,
                )
            return True

        if result.kind in ("all_deny", "all_perm_deny"):
            for item in items:
                await self._remember_decision(
                    item, "deny", permanent=(result.kind == "all_perm_deny"),
                    session_id=session_id, task=task,
                )
            ids = [i.subtask_id for i in items]
            await self._drop_blocked_nodes(plan, ids, task)
            # 若所有节点都是敏感节点且全被拒，直接终止
            return await self._still_has_executable(plan)

        if result.kind == "partial":
            allow_set = {i for i in result.allow_indices if 1 <= i <= len(items)}
            rejected_ids: list[str] = []
            for idx, item in enumerate(items, start=1):
                if idx in allow_set:
                    await self._remember_decision(
                        item, "allow", permanent=result.permanent,
                        session_id=session_id, task=task,
                    )
                else:
                    await self._remember_decision(
                        item, "deny", permanent=result.permanent,
                        session_id=session_id, task=task,
                    )
                    rejected_ids.append(item.subtask_id)
            if rejected_ids:
                await self._drop_blocked_nodes(plan, rejected_ids, task)
            return await self._still_has_executable(plan)

        # unknown → 保守全拒
        logger.warning("[四影·batch_ask] 答复无法识别，保守拒绝全部敏感节点")
        return await self._reject_all_sensitive(plan, items, task)

    async def _remember_decision(
        self, item, decision: str, *, permanent: bool,
        session_id: str, task: TaskEdict,
    ) -> None:
        """本次 / 永久写入授权。subject=(shades_node, <assignee>) 粗粒度。"""
        assert self._authz_cache is not None
        subject_type, subject_id = "shades_node", item.assignee

        if permanent:
            perm_decision = "permanent_allow" if decision == "allow" else "permanent_deny"
            try:
                await self._irminsul.authz_set(
                    subject_type, subject_id, perm_decision,
                    user_id=self._user_id, session_id=session_id,
                    reason=f"shades_batch_ask:{decision}",
                    actor="派蒙·四影授权",
                )
            except Exception as e:
                logger.warning("[四影·batch_ask] 授权写世界树失败: {}", e)
            self._authz_cache.set(subject_type, subject_id, perm_decision)
        else:
            self._authz_cache.set_session_scope(
                session_id, subject_type, subject_id, decision,
            )

    async def _drop_blocked_nodes(
        self, plan: Plan, blocked_ids: list[str], task: TaskEdict,
    ) -> None:
        """从 plan 中剔除被拒/被禁的节点 + 传递性 skip 下游。"""
        if not blocked_ids:
            return
        results_view: dict[str, str] = {}
        all_skipped: set[str] = set()
        for bid in blocked_ids:
            skipped = mark_downstream_skipped(bid, plan.subtasks, results_view)
            all_skipped.update(skipped)
        removed = set(blocked_ids) | all_skipped
        if not removed:
            return

        # 标记 DB 状态并从 plan 中移除
        for sid in removed:
            try:
                await self._irminsul.subtask_update_status(
                    sid, status="skipped",
                    result="[已剔除] 敏感操作被拒 / 上游被剔除",
                    actor="四影·batch_ask",
                )
            except Exception as e:
                logger.debug("[四影] 标 skipped 失败 {}: {}", sid, e)
        plan.subtasks = [s for s in plan.subtasks if s.id not in removed]

        await self._irminsul.audit_append(
            event_type="shades_nodes_dropped",
            payload={
                "reason": "batch_ask_deny",
                "directly_rejected": blocked_ids,
                "transitive_skipped": list(all_skipped),
            },
            task_id=task.id, session_id=task.session_id, actor="四影·batch_ask",
        )
        logger.info(
            "[四影·batch_ask] 剔除 {} 节点（直接 {}，传递 {}）",
            len(removed), len(blocked_ids), len(all_skipped),
        )

    async def _reject_all_sensitive(
        self, plan: Plan, items: list, task: TaskEdict,
    ) -> bool:
        ids = [i.subtask_id for i in items]
        await self._drop_blocked_nodes(plan, ids, task)
        return await self._still_has_executable(plan)

    async def _still_has_executable(self, plan: Plan) -> bool:
        """plan 中是否仍有可执行节点。"""
        return len(plan.subtasks) > 0

    # ---------------- verdict ----------------

    def _resolve_verdict(self, plan: Plan, results: dict[str, str]) -> ReviewVerdict:
        """从 plan 的"最后一个水神节点"取产物解析 verdict。无水神节点视为 pass。"""
        water = find_last_verdict_producer(plan.subtasks)
        if water is None:
            return ReviewVerdict(level=LEVEL_PASS, summary="(无水神评审节点，默认通过)")

        raw = results.get(water.id, "")
        if not raw:
            # 水神节点失败/跳过：不强求评审结论，视为 pass 并附说明
            return ReviewVerdict(
                level=LEVEL_PASS,
                summary="(水神节点无产物，跳过评审视为通过)",
            )
        return parse_verdict(raw)

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

    # ---------------- final compose ----------------

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
        non_water_terms = [t for t in terminals if t.assignee != "水神"]
        water_terms = [t for t in terminals if t.assignee == "水神"]

        parts: list[str] = []
        for t in non_water_terms:
            parts.append(results[t.id])
        if not parts and water_terms:
            for t in water_terms:
                parts.append(results[t.id])
        if not parts:
            for sid, r in results.items():
                if r:
                    parts.append(r)

        body = "\n\n---\n\n".join(parts).strip()

        if round_cap_hit and verdict is not None:
            body += (
                f"\n\n---\n"
                f"⚠️ 已达最大轮次（level={verdict.level}），返回最后一轮产物。\n"
                f"水神意见：{verdict.summary[:400]}"
            )
        return body or "(产物为空)"

    async def _create_task(
        self,
        user_input: str,
        session_id: str,
        escalation_reason: str | None = None,
    ) -> TaskEdict:
        title = user_input[:100].strip()
        if escalation_reason:
            description = (
                f"{user_input}\n"
                f"---\n"
                f"[魔女会转交] 天使路径失败原因：{escalation_reason}"
            )
            creator = "派蒙·魔女会"
        else:
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
