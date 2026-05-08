"""四影 · execute 主循环：N 轮草水雷规划→分派→裁决；archive 归档收尾。"""
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


class _ExecuteMixin:
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
        # 至少 2 轮：round 1 出 revise 必须有 round 2 修订机会，否则 review 系统等于摆设
        max_rounds = max(2, int(getattr(config, "shades_max_rounds", 3)))
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

        except asyncio.CancelledError:
            # ROB-007：user 取消任务（/stop / 关 SSE / 进程退出）→ 不当作"任务失败"，
            # 只归档为"已取消"让 task workspace 保留 + audit 留痕；不再阻塞 task 锁
            logger.info("[四影] 任务被取消 task={} round={}", task.id, round_idx)
            try:
                await istaroth.archive(
                    task, self._irminsul,
                    failure_reason="user_cancelled",
                    rounds=round_idx,
                )
                await self._irminsul.audit_append(
                    event_type="shades_cancelled",
                    payload={"round": round_idx},
                    task_id=task.id, session_id=task.session_id, actor="四影",
                )
            except Exception as _e:
                logger.warning("[四影] 取消归档失败（已吞）: {}", _e)
            raise

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
