"""世界树 façade · 基础数据域 1-7：authz/skill/knowledge/memory/task/token/audit。"""
from __future__ import annotations

from pathlib import Path

from ..audit import AuditEntry
from ..authz import Authz
from ..dividend import ChangeEvent, ScoreSnapshot, WatchlistEntry
from ..dividend_event import DividendEvent
from ..user_watchlist import UserWatchEntry, UserWatchPrice
from ..mihoyo import (
    MihoyoAbyss, MihoyoAccount, MihoyoCharacter, MihoyoGacha, MihoyoNote,
)
from ..memory import Memory, MemoryMeta
from ..session import SessionMeta, SessionRecord
from ..skills import SkillDecl
from ..feed_event import FeedEvent
from ..llm_profile import LLMProfile
from ..llm_route import LLMRoute
from ..push_archive import PushArchiveRecord
from ..selfcheck import SelfcheckRun
from ..subscription import FeedItem, Subscription
from ..task import FlowEntry, ProgressEntry, Subtask, TaskEdict
from ..schedule import ScheduledTask
from ..token import TokenRow

class _BasicsMixin:
    # ============ 域 1: 授权 ============
    async def authz_get(self, subject_type: str, subject_id: str, *, user_id: str = "default") -> Authz | None:
        return await self._authz.get(subject_type, subject_id, user_id=user_id)

    async def authz_set(
        self, subject_type: str, subject_id: str, decision: str,
        *, user_id: str = "default", session_id: str = "", reason: str = "", actor: str,
    ) -> None:
        await self._authz.set(
            subject_type, subject_id, decision,
            user_id=user_id, session_id=session_id, reason=reason, actor=actor,
        )

    async def authz_revoke(
        self, subject_type: str, subject_id: str,
        *, user_id: str = "default", actor: str,
    ) -> bool:
        return await self._authz.revoke(subject_type, subject_id, user_id=user_id, actor=actor)

    async def authz_list(self, *, user_id: str = "default") -> list[Authz]:
        return await self._authz.list(user_id=user_id)

    async def authz_snapshot(self, *, user_id: str = "default") -> dict[tuple[str, str], str]:
        return await self._authz.snapshot(user_id=user_id)

    # ============ 域 2: Skill 声明 ============
    async def skill_declare(self, decl: SkillDecl, *, actor: str) -> None:
        await self._skill.declare(decl, actor=actor)

    async def skill_get(self, name: str) -> SkillDecl | None:
        return await self._skill.get(name)

    async def skill_list(self, *, source: str | None = None, include_orphaned: bool = False) -> list[SkillDecl]:
        return await self._skill.list(source=source, include_orphaned=include_orphaned)

    async def skill_mark_orphaned(self, name: str, orphaned: bool, *, actor: str) -> None:
        await self._skill.mark_orphaned(name, orphaned, actor=actor)

    async def skill_remove(self, name: str, *, actor: str) -> bool:
        return await self._skill.remove(name, actor=actor)

    async def skill_snapshot(self, *, include_orphaned: bool = False) -> list[SkillDecl]:
        return await self._skill.snapshot(include_orphaned=include_orphaned)

    # ============ 域 3: 知识库 ============
    async def knowledge_read(self, category: str, topic: str) -> str | None:
        return await self._knowledge.read(category, topic)

    async def knowledge_write(self, category: str, topic: str, body: str, *, actor: str) -> None:
        await self._knowledge.write(category, topic, body, actor=actor)

    async def knowledge_list(self, category: str = "") -> list[tuple[str, str]]:
        return await self._knowledge.list(category)

    async def knowledge_list_detailed(self, category: str = "") -> list[dict]:
        return await self._knowledge.list_detailed(category)

    async def knowledge_delete(self, category: str, topic: str, *, actor: str) -> bool:
        return await self._knowledge.delete(category, topic, actor=actor)

    # ============ 域 4: 记忆 ============
    async def memory_write(
        self, *, mem_type: str, subject: str, title: str, body: str,
        tags: list[str] | None = None, source: str = "",
        ttl: float | None = None, actor: str,
    ) -> str:
        return await self._memory.write(
            mem_type=mem_type, subject=subject, title=title, body=body,
            tags=tags, source=source, ttl=ttl, actor=actor,
        )

    async def memory_get(self, mem_id: str) -> Memory | None:
        return await self._memory.get(mem_id)

    async def memory_list(
        self, *, mem_type: str | None = None, subject: str | None = None,
        tags_any: list[str] | None = None, limit: int = 100,
    ) -> list[MemoryMeta]:
        return await self._memory.list(
            mem_type=mem_type, subject=subject, tags_any=tags_any, limit=limit,
        )

    async def memory_update(
        self, mem_id: str, *,
        title: str | None = None, body: str | None = None,
        tags: list[str] | None = None, ttl: float | None = None,
        actor: str,
    ) -> bool:
        return await self._memory.update(
            mem_id, title=title, body=body, tags=tags, ttl=ttl, actor=actor,
        )

    async def memory_delete(self, mem_id: str, *, actor: str) -> bool:
        return await self._memory.delete(mem_id, actor=actor)

    async def memory_expire(self, now: float, *, actor: str) -> int:
        return await self._memory.expire(now, actor=actor)

    # ============ 域 5: 活跃任务 ============
    async def task_create(self, edict: TaskEdict, *, actor: str) -> None:
        await self._task.create(edict, actor=actor)

    async def task_get(self, task_id: str) -> TaskEdict | None:
        return await self._task.get(task_id)

    async def task_update_status(self, task_id: str, status: str, *, actor: str) -> None:
        await self._task.update_status(task_id, status, actor=actor)

    async def task_update_lifecycle(self, task_id: str, stage: str, *, actor: str) -> None:
        await self._task.update_lifecycle(task_id, stage, actor=actor)

    # --- 生命周期清扫（时执·_lifecycle 用）---

    async def task_stuck_running_timeout(
        self, *, now: float, timeout_seconds: float, actor: str,
    ) -> list[str]:
        return await self._task.stuck_running_timeout(
            now=now, timeout_seconds=timeout_seconds, actor=actor,
        )

    async def task_promote_lifecycle(
        self, *, now: float, cold_ttl_seconds: float, actor: str,
    ) -> list[str]:
        return await self._task.promote_lifecycle(
            now=now, cold_ttl_seconds=cold_ttl_seconds, actor=actor,
        )

    async def task_purge_expired(
        self, *, now: float, archived_ttl_seconds: float, actor: str,
    ) -> list[str]:
        return await self._task.purge_expired(
            now=now, archived_ttl_seconds=archived_ttl_seconds, actor=actor,
        )

    async def task_list(
        self, *, status: str | None = None, lifecycle_stage: str | None = None,
        session_id: str | None = None, limit: int = 100,
    ) -> list[TaskEdict]:
        return await self._task.list(
            status=status, lifecycle_stage=lifecycle_stage,
            session_id=session_id, limit=limit,
        )

    async def subtask_create(self, sub: Subtask, *, actor: str) -> None:
        await self._task.subtask_create(sub, actor=actor)

    async def subtask_update_status(self, subtask_id: str, status: str, result: str = "", *, actor: str) -> None:
        await self._task.subtask_update_status(subtask_id, status, result, actor=actor)

    async def subtask_update_verdict(
        self, subtask_id: str, verdict_status: str, *, actor: str,
    ) -> None:
        """水神裁决后为单个子任务打标 verdict（passed / needs_revise / needs_redo）。"""
        await self._task.subtask_update_verdict(subtask_id, verdict_status, actor=actor)

    async def subtask_list(self, task_id: str) -> list[Subtask]:
        return await self._task.subtask_list(task_id)

    async def flow_append(
        self, task_id: str, from_agent: str, to_agent: str, action: str,
        payload: dict | None = None, *, actor: str,
    ) -> None:
        await self._task.flow_append(task_id, from_agent, to_agent, action, payload, actor=actor)

    async def flow_list(self, task_id: str) -> list[FlowEntry]:
        return await self._task.flow_list(task_id)

    async def progress_append(
        self, task_id: str, agent: str, progress_pct: int,
        message: str = "", subtask_id: str | None = None, *, actor: str,
    ) -> None:
        await self._task.progress_append(
            task_id, agent, progress_pct, message, subtask_id, actor=actor,
        )

    async def progress_list(self, task_id: str) -> list[ProgressEntry]:
        return await self._task.progress_list(task_id)

    # ============ 域 6: Token 记录 ============
    async def token_write(
        self, session_id: str, component: str, model_name: str,
        input_tokens: int, output_tokens: int, cost_usd: float, *,
        cache_creation_tokens: int = 0, cache_read_tokens: int = 0,
        purpose: str = "", timestamp: float | None = None, actor: str,
    ) -> None:
        await self._token.write(
            session_id, component, model_name,
            input_tokens, output_tokens, cost_usd,
            cache_creation_tokens=cache_creation_tokens,
            cache_read_tokens=cache_read_tokens,
            purpose=purpose, timestamp=timestamp, actor=actor,
        )

    async def token_rows(
        self, *, session_id: str | None = None, component: str | None = None,
        purpose: str | None = None, since: float | None = None,
        until: float | None = None, limit: int = 10000,
    ) -> list[TokenRow]:
        return await self._token.rows(
            session_id=session_id, component=component, purpose=purpose,
            since=since, until=until, limit=limit,
        )

    async def token_aggregate(
        self, *, group_by: list[str],
        session_id: str | None = None, since: float | None = None,
    ) -> list[dict]:
        return await self._token.aggregate(
            group_by=group_by, session_id=session_id, since=since,
        )

    # ============ 域 7: 审计 ============
    async def audit_append(
        self, event_type: str, payload: dict, *,
        task_id: str | None = None, session_id: str = "", actor: str,
    ) -> None:
        await self._audit.append(
            event_type, payload,
            task_id=task_id, session_id=session_id, actor=actor,
        )

    async def audit_list(
        self, *, event_type: str | None = None,
        task_id: str | None = None, since: float | None = None, limit: int = 100,
    ) -> list[AuditEntry]:
        return await self._audit.list(
            event_type=event_type, task_id=task_id, since=since, limit=limit,
        )
