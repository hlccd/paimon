"""四影 · 批量敏感操作授权：派蒙问 → 关键词分类 → drop blocked / saga 补偿。"""
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


class _AuthorizeMixin:
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
            items_hint = "\n".join(
                f"  - {item.assignee} · {item.description[:40]}"
                for item in scan.items_to_ask[:10]
            )
            self._last_batch_authz_failure = (
                f"当前频道（{getattr(self._channel, 'name', '?')}）暂不支持交互授权。\n"
                f"此任务涉及 {len(scan.items_to_ask)} 个敏感操作节点：\n{items_hint}\n"
                "请换到 Web 端重试，或用 `/grant <神名>` 预授权相关能力后再试。"
            )
            await self._notify_progress(
                f"🚫 task={task.id[:8]} 渠道未支持交互授权\n"
                f"  涉及 {len(scan.items_to_ask)} 个敏感节点，保守全拒"
            )
            return await self._reject_all_sensitive(plan, scan.items_to_ask, task)
        except asyncio.TimeoutError:
            logger.info(
                "[四影·batch_ask] 询问超时 ({}s)，保守拒绝",
                self._batch_ask_timeout,
            )
            self._last_batch_authz_failure = (
                f"授权询问超时（{self._batch_ask_timeout:.0f} 秒无答复），保守取消。"
            )
            await self._notify_progress(
                f"⏰ task={task.id[:8]} 授权询问超时（{self._batch_ask_timeout:.0f}s）→ 保守全拒"
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
