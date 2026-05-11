"""世界树 façade · 基础数据域 1-7：authz/skill/knowledge/memory/token/audit。"""
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
from ..skill_proposals import SkillProposal
from ..skills import SkillDecl
from ..llm_profile import LLMProfile
from ..llm_route import LLMRoute
from ..push_archive import PushArchiveRecord
from ..selfcheck import SelfcheckRun
from ..subscription import FeedItem, Subscription
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

    # ============ 域 16: Skill 自进化提案 ============
    async def skill_proposal_create(
        self, *,
        name: str,
        kind: str = "new",
        target_skill: str = "",
        description: str = "",
        triggers: str = "",
        system_prompt: str = "",
        allowed_tools: list[str] | None = None,
        rationale: str = "",
        proposed_by_session: str = "",
        proposed_by_task: str = "",
        actor: str,
    ) -> str:
        return await self._skill_proposal.create(
            name=name, kind=kind, target_skill=target_skill,
            description=description, triggers=triggers,
            system_prompt=system_prompt, allowed_tools=allowed_tools,
            rationale=rationale,
            proposed_by_session=proposed_by_session,
            proposed_by_task=proposed_by_task, actor=actor,
        )

    async def skill_proposal_get(self, prop_id: str) -> SkillProposal | None:
        return await self._skill_proposal.get(prop_id)

    async def skill_proposal_list(
        self, *,
        status: str | None = None, kind: str | None = None, limit: int = 100,
    ) -> list[SkillProposal]:
        return await self._skill_proposal.list(status=status, kind=kind, limit=limit)

    async def skill_proposal_set_review(
        self, prop_id: str, verdict: str, notes: str = "", *, actor: str,
    ) -> bool:
        return await self._skill_proposal.set_review_verdict(
            prop_id, verdict, notes, actor=actor,
        )

    async def skill_proposal_approve(
        self, prop_id: str, *, decided_by: str = "user", actor: str,
    ) -> bool:
        return await self._skill_proposal.approve(
            prop_id, decided_by=decided_by, actor=actor,
        )

    async def skill_proposal_reject(
        self, prop_id: str, notes: str = "", *,
        decided_by: str = "user", actor: str,
    ) -> bool:
        return await self._skill_proposal.reject(
            prop_id, notes, decided_by=decided_by, actor=actor,
        )

    async def skill_proposal_submit_user_feedback(
        self, prop_id: str, feedback: str, *, actor: str = "用户",
    ) -> bool:
        return await self._skill_proposal.submit_user_feedback(
            prop_id, feedback, actor=actor,
        )

    async def skill_proposal_mark_revising_done(self, prop_id: str) -> None:
        await self._skill_proposal.mark_revising_done(prop_id)

    async def skill_proposal_clear_stale_revising(
        self, *, timeout_seconds: float = 600,
    ) -> int:
        return await self._skill_proposal.clear_stale_revising(
            timeout_seconds=timeout_seconds,
        )

    async def skill_proposal_update_content(
        self, prop_id: str, *,
        description: str | None = None,
        triggers: str | None = None,
        system_prompt: str | None = None,
        allowed_tools: list[str] | None = None,
        rationale: str | None = None,
        bump_revision: bool = True,
        actor: str,
    ) -> bool:
        return await self._skill_proposal.update_content(
            prop_id,
            description=description, triggers=triggers,
            system_prompt=system_prompt, allowed_tools=allowed_tools,
            rationale=rationale, bump_revision=bump_revision, actor=actor,
        )

    async def skill_proposal_mark_applied(self, prop_id: str, *, actor: str) -> bool:
        return await self._skill_proposal.mark_applied(prop_id, actor=actor)

    async def skill_proposal_delete(self, prop_id: str, *, actor: str) -> bool:
        return await self._skill_proposal.delete(prop_id, actor=actor)

    async def skill_proposal_count_by_status(self) -> dict[str, int]:
        return await self._skill_proposal.count_by_status()

    async def skill_proposal_prune(
        self, *, before_ts: float,
        statuses: tuple[str, ...] = ("rejected",),
        actor: str,
    ) -> int:
        return await self._skill_proposal.prune_old(
            before_ts=before_ts, statuses=statuses, actor=actor,
        )

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
