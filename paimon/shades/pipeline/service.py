"""四影管线主服务 ShadesPipeline：__init__ + prepare + run + 通知 helpers + mixin 组合。

闭环结构（详见包 docstring）：环 1 入口审 → 环 2 主循环 N 轮 → 环 3 归档。
方法实现按职责拆 4 个 mixin：execute / authorize / verdict / final。
"""
from __future__ import annotations

from dataclasses import dataclass

from loguru import logger

from paimon.core.authz.cache import AuthzCache
from paimon.foundation.irminsul import Irminsul
from paimon.foundation.irminsul.task import TaskEdict
from paimon.llm.model import Model
from paimon.shades import istaroth, jonova, naberius

from .._plan import Plan
from ._authorize import _AuthorizeMixin
from ._execute import _ExecuteMixin
from ._final import _FinalMixin
from ._verdict import _VerdictMixin


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


class ShadesPipeline(
    _ExecuteMixin, _AuthorizeMixin, _VerdictMixin, _FinalMixin,
):
    """四影管线核心：闭环 prepare → execute → archive；通知/会话/授权 cache 注入。"""

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
        self.last_task_id = ""

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
    ) -> "PrepareResult":
        """前台同步跑：create_task → 入口审 → round-1 plan → 批量授权。

        必须在 SSE 仍活跃的上下文调用（ask_user 依赖活跃 SSE）。
        返回 PrepareResult：成功时 (task, plan) 可交给 execute() 后台跑；
        失败时 msg 就是给用户看的最终字符串。
        """
        task = await self._create_task(user_input, session_id)
        self.last_task_id = task.id
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

    async def run(
        self,
        user_input: str,
        session_id: str = "",
    ) -> str:
        """兼容入口：prepare + execute 一把梭（前台全跑，不分前后台）。"""
        prep = await self.prepare(user_input, session_id)
        if not prep.ok:
            return prep.msg
        return await self.execute(prep.task, prep.plan, session_id)
