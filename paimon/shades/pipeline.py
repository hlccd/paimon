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
from dataclasses import dataclass
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


@dataclass
class PrepareResult:
    """ShadesPipeline.prepare() 的返回值。

    ok=True 时把 (task, plan) 交给 execute() 后台跑；
    ok=False 时 msg 就是直接回用户的文字。
    """
    task: TaskEdict
    plan: Plan | None
    ok: bool
    msg: str


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
        reply=None,            # paimon.channels.base.ChannelReply | None —— 推中间 notice
    ):
        self._model = model
        self._irminsul = irminsul
        self._channel = channel
        self._chat_id = chat_id
        self._authz_cache = authz_cache
        self._user_id = user_id
        self._batch_ask_timeout = batch_ask_timeout
        self._reply = reply
        # _batch_authorize 失败时的具体原因（给 prepare / execute 用作 msg）
        # 区分三种情况：用户真的拒绝 / 渠道不支持交互授权 / 授权超时
        self._last_batch_authz_failure = ""

    async def _notice(self, text: str, *, kind: str = "milestone") -> None:
        """向当前 reply 推一条中间状态（渠道自决是否发；失败静默）。

        execute 阶段 SSE/被动窗口可能已关闭，此时 notice 直接丢。
        和 `_notify_progress`（📨 推送）是两条独立路径：
          - _notice  = 原会话里的 notice 气泡（会话级）
          - _notify_progress = 推送会话 + 任务审计（跨会话）
        """
        if self._reply is None:
            return
        try:
            await self._reply.notice(text, kind=kind)
        except Exception as e:
            logger.debug("[四影·notice] 推送失败: {}", e)

    @staticmethod
    def _format_dispatch_msg(plan: "Plan") -> str:
        """把 plan 的子任务列表格式化成面向用户的派发消息。

        子任务描述**完整不截断**（用户明确要求，即使很长也全列；QQ 单条消息上限
        约 2000 字，通常远够装下 DAG）。只去掉 `[STAGE:xxx]` 内部标记前缀。
        """
        lines = [f"🚀 已派发 {len(plan.subtasks)} 个子任务执行："]
        for i, sub in enumerate(plan.subtasks, start=1):
            desc = (sub.description or "").strip()
            if desc.startswith("["):
                rb = desc.find("]")
                if 0 < rb < 40:
                    desc = desc[rb + 1:].strip()
            lines.append(f"  {i}. {sub.assignee} · {desc}")
        lines.append(
            "如超过几分钟未完成，可随时去 /tasks 面板或 /task-list 查看进度。"
        )
        return "\n".join(lines)

    async def _notify_progress(self, text: str) -> None:
        """向用户推一条关键进度消息（走 march.ring_event → 派蒙独占出口 → 推送会话）。

        失败静默（推送不可用不应打断管线）。
        """
        if not self._channel or not self._chat_id:
            return
        try:
            from paimon.state import state as _state
            if _state.march:
                await _state.march.ring_event(
                    channel_name=self._channel.name,
                    chat_id=self._chat_id,
                    source="四影",
                    message=text,
                    # 关键：把 task_id 写进 push_archive.extra_json，
                    # 让 /task-index 能反查这条任务的最终摘要（_compose_final 的产物）
                    task_id=self.last_task_id or "",
                )
        except Exception as e:
            logger.debug("[四影·progress] 推送失败: {}", e)

    async def prepare(
        self,
        user_input: str,
        session_id: str = "",
        escalation_reason: str | None = None,
    ) -> "PrepareResult":
        """前台同步跑：create_task → 入口审 → round-1 plan → 批量授权。

        必须在 SSE 仍活跃的上下文调用（ask_user 依赖活跃 SSE）。
        返回 PrepareResult：成功时 (task, plan) 可交给 execute() 后台跑；
        失败时 msg 就是给用户看的最终字符串。
        """
        task = await self._create_task(user_input, session_id, escalation_reason)
        self.last_task_id = task.id
        if escalation_reason:
            logger.info("[四影·prepare] 魔女会转入 task={} reason={}", task.id, escalation_reason)
        logger.info("[四影·prepare] task={} title={}", task.id, task.title[:60])

        # ack：任务已登录 + 短标题已生成，此刻推最即时的回执。
        # QQ 渠道会暂存 ack 到首条 milestone 再一起发（节省 seq 预算；
        # prepare 直接失败时 ack 永远不发）。Web 立刻推浅灰小字。
        await self._notice(
            f"收到任务：{task.title} (task={task.id[:8]})，正在准备（安全审查 + 编排）…",
            kind="ack",
        )

        try:
            safe, reason = await jonova.review(task, self._model, self._irminsul)
            if not safe:
                await self._irminsul.task_update_status(task.id, status="rejected", actor="死执")
                await istaroth.archive(
                    task, self._irminsul,
                    failure_reason=f"死执拒绝: {reason}", rounds=0,
                )
                return PrepareResult(
                    task=task, plan=None, ok=False,
                    msg=f"请求未通过安全审查: {reason}",
                )

            await self._notice("🔒 安全审查通过")

            plan = await naberius.plan(
                task, self._model, self._irminsul,
                previous_plan=None, verdict=None, round=1,
            )
            await self._irminsul.task_update_status(
                task.id, status="running", actor="空执",
            )

            # 批量授权（此刻 SSE 活跃 → ask_user 能问到用户）
            scan_ok = await self._batch_authorize(task, plan, session_id)
            if not scan_ok:
                # 区分"用户真拒绝" vs "渠道不支持交互授权" vs "超时"
                reason = self._last_batch_authz_failure or "用户拒绝了全部敏感操作"
                await istaroth.archive(
                    task, self._irminsul,
                    failure_reason=reason, rounds=1,
                )
                return PrepareResult(
                    task=task, plan=plan, ok=False,
                    msg=f"⚠️ 任务已取消\n{reason}",
                )
            # prepare 末尾一条 milestone，含全部子任务列表。
            # 不在 execute 里发派发 milestone —— 异步路径下 SSE 在 hint 后就关闭，
            # execute 阶段的 notice 推不到原会话。prepare 末尾是最后能推的时机。
            await self._notice(self._format_dispatch_msg(plan))
            return PrepareResult(task=task, plan=plan, ok=True, msg="")
        except Exception as e:
            logger.exception("[四影·prepare] 异常 task={}: {}", task.id, e)
            try:
                await istaroth.archive(
                    task, self._irminsul,
                    failure_reason=f"prepare 异常: {e}", rounds=0,
                )
            except Exception:
                pass
            return PrepareResult(
                task=task, plan=None, ok=False,
                msg=f"任务准备失败: {e}",
            )

    async def execute(
        self,
        task: TaskEdict,
        initial_plan: Plan,
        session_id: str = "",
    ) -> str:
        """后台跑：从 round-1 dispatch 开始，完成所有轮次与归档。

        round-1 plan 来自 prepare()（已授权，不再问）；
        round-2+ 进入循环再 naberius.plan + batch_authorize（会话级 authz_cache
        通常让复审默认放行，除非 LLM 引入新类型敏感节点）。
        """
        self.last_task_id = task.id
        max_rounds = max(1, int(getattr(config, "shades_max_rounds", 3)))
        plan: Plan | None = initial_plan
        verdict: ReviewVerdict | None = None
        last_results: dict[str, str] = {}
        completed_ids: set[str] = set()
        round_idx = 1
        round_cap_hit = False

        try:
            # 关键进度：任务启动
            await self._notify_progress(
                f"🧭 四影启动 task={task.id[:8]}\n"
                f"  标题: {task.title[:80]}\n"
                f"  DAG: {len(plan.subtasks)} 节点，上限 {max_rounds} 轮"
            )

            while round_idx <= max_rounds:
                if round_idx > 1:
                    plan = await naberius.plan(
                        task, self._model, self._irminsul,
                        previous_plan=plan, verdict=verdict, round=round_idx,
                    )
                    await self._notify_progress(
                        f"🔁 进入 round {round_idx}（上轮 {verdict.level if verdict else '?'}）"
                    )
                    scan_ok = await self._batch_authorize(task, plan, session_id)
                    if not scan_ok:
                        reason = self._last_batch_authz_failure or "用户拒绝了全部敏感操作"
                        await istaroth.archive(
                            task, self._irminsul,
                            failure_reason=f"revise 轮：{reason}",
                            rounds=round_idx,
                        )
                        await self._notify_progress(
                            f"❌ task={task.id[:8]} round {round_idx} {reason[:80]}"
                        )
                        return f"⚠️ 任务已取消（round {round_idx}）\n{reason}"

                # 注意：派发 milestone 已在 prepare 末尾发过，这里不再重复。
                # 异步 bg 路径下 SSE 已关；同步路径下也不需要再提醒用户一次。
                # revise 轮的进度继续走 _notify_progress (📨 推送 + /tasks 面板)。

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

                # 关键进度 2/3：本轮各阶段 verdict 汇总（只一行，含三阶段通过情况）
                stage_status = self._stage_status_line(plan, last_results)
                icon = {"pass": "✅", "revise": "⚠️", "redo": "❌"}.get(verdict.level, "❓")
                await self._notify_progress(
                    f"{icon} round {round_idx} → {verdict.level}\n"
                    f"  阶段: {stage_status}\n"
                    f"  {verdict.summary[:120]}"
                )

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
            # 把最终产物推到📨 推送（非写代码任务没 workspace summary.md，这里补）
            head = "🎉" if not round_cap_hit else "⚠️"
            await self._notify_progress(
                f"{head} task={task.id[:8]} 完成（rounds={round_idx}）\n\n{final[:3500]}"
            )
            # 注意：final 不在此发 done_recap notice —— 最终产物应作为正文气泡呈现（marked
            # 渲染），不是浅灰小字 notice。由上层（core/chat.py）拿到 return 的 final 后
            # 走 reply.send + flush，WebUI 前端把 typing 占位替换为正文气泡。
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
            await self._notify_progress(
                f"💥 task={task.id[:8]} 管线异常: {str(e)[:200]}"
            )
            # 同成功路径：失败说明也交给上层走正文，不在这里发 notice
            return f"💥 任务执行失败：{e}"

    async def run(
        self,
        user_input: str,
        session_id: str = "",
        escalation_reason: str | None = None,
    ) -> str:
        """兼容入口：prepare + execute 一把梭（前台全跑，不分前后台）。"""
        prep = await self.prepare(user_input, session_id, escalation_reason)
        if not prep.ok:
            return prep.msg
        return await self.execute(prep.task, prep.plan, session_id)

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

    # ---------------- verdict ----------------

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
                f"水神意见：{verdict.summary[:400]}"
            )
        return body or "(产物为空)"

    async def _create_task(
        self,
        user_input: str,
        session_id: str,
        escalation_reason: str | None = None,
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
