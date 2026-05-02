"""世界树 façade · 可观测/治理数据域 12/13/14/15：selfcheck + push_archive + llm_profile + llm_route。"""
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

class _ObservabilityMixin:
    # ============ 域 12: 自检归档（三月）============
    async def selfcheck_create(self, run: SelfcheckRun, *, actor: str) -> str:
        return await self._selfcheck.create(run, actor=actor)

    async def selfcheck_update(self, run_id: str, *, actor: str, **fields) -> bool:
        return await self._selfcheck.update(run_id, actor=actor, **fields)

    async def selfcheck_get(self, run_id: str) -> SelfcheckRun | None:
        return await self._selfcheck.get(run_id)

    async def selfcheck_list(
        self, *, kind: str | None = None, limit: int = 50, offset: int = 0,
    ) -> list[SelfcheckRun]:
        return await self._selfcheck.list(kind=kind, limit=limit, offset=offset)

    async def selfcheck_count(self, *, kind: str | None = None) -> int:
        return await self._selfcheck.count(kind=kind)

    async def selfcheck_latest(self, kind: str) -> SelfcheckRun | None:
        return await self._selfcheck.latest(kind)

    async def selfcheck_delete(self, run_id: str, *, actor: str) -> bool:
        return await self._selfcheck.delete(run_id, actor=actor)

    async def selfcheck_gc(self, *, kind: str, keep_n: int, actor: str) -> int:
        return await self._selfcheck.gc(kind=kind, keep_n=keep_n, actor=actor)

    async def selfcheck_sweep_zombie(self, *, actor: str) -> int:
        """启动时清理 status='running' 的 zombie 记录（进程重启后对齐状态）。"""
        return await self._selfcheck.sweep_zombie_running(actor=actor)

    def selfcheck_blob_dir(self, run_id: str) -> Path:
        """返回 run_id 对应的 blob 目录路径；不保证存在。"""
        return self._selfcheck.blob_dir(run_id)

    def selfcheck_ensure_blob_dir(self, run_id: str) -> Path:
        """确保 blob 目录存在并返回路径。"""
        return self._selfcheck.ensure_blob_dir(run_id)

    # ============ 域 13: 推送归档（替代主动聊天推送）============
    async def push_archive_create(
        self,
        *,
        source: str,
        actor: str,
        message_md: str,
        channel_name: str = "webui",
        chat_id: str = "",
        level: str = "silent",
        extra: dict | None = None,
    ) -> str:
        return await self._push_archive.create(
            source=source, actor=actor, message_md=message_md,
            channel_name=channel_name, chat_id=chat_id,
            level=level, extra=extra,
        )

    async def push_archive_upsert_daily(
        self,
        *,
        source: str,
        actor: str,
        message_md: str,
        day_start: float,
        day_end: float,
        channel_name: str = "webui",
        chat_id: str = "",
        level: str = "silent",
        extra: dict | None = None,
    ) -> tuple[str, str]:
        return await self._push_archive.upsert_daily(
            source=source, actor=actor, message_md=message_md,
            day_start=day_start, day_end=day_end,
            channel_name=channel_name, chat_id=chat_id,
            level=level, extra=extra,
        )

    async def push_archive_touch_daily(
        self, *,
        source: str,
        actor: str,
        day_start: float,
        day_end: float,
    ) -> tuple[bool, str]:
        return await self._push_archive.touch_daily(
            source=source, actor=actor,
            day_start=day_start, day_end=day_end,
        )

    async def push_archive_get(self, rec_id: str) -> PushArchiveRecord | None:
        return await self._push_archive.get(rec_id)

    async def push_archive_list(
        self, *,
        actor: str | None = None,
        only_unread: bool = False,
        since: float | None = None,
        until: float | None = None,
        limit: int = 50,
    ) -> list[PushArchiveRecord]:
        return await self._push_archive.list(
            actor=actor, only_unread=only_unread,
            since=since, until=until, limit=limit,
        )

    async def push_archive_count_unread(
        self, *, actor: str | None = None,
    ) -> int:
        return await self._push_archive.count_unread(actor=actor)

    async def push_archive_count_unread_grouped(self) -> dict[str, int]:
        return await self._push_archive.count_unread_grouped()

    async def push_archive_mark_read(self, rec_id: str) -> bool:
        return await self._push_archive.mark_read(rec_id)

    async def push_archive_mark_read_all(
        self, *, actor: str | None = None,
    ) -> int:
        return await self._push_archive.mark_read_all(actor=actor)

    async def push_archive_sweep_old(
        self, *, retention_seconds: float, actor: str = "三月",
    ) -> int:
        return await self._push_archive.sweep_old(
            retention_seconds=retention_seconds, actor=actor,
        )

    # ============ 域 14: LLM Profile ============
    async def llm_profile_create(
        self, profile: LLMProfile, *, actor: str,
    ) -> str:
        return await self._llm_profile.create(profile, actor=actor)

    async def llm_profile_update(
        self, profile_id: str, *, actor: str, **fields,
    ) -> bool:
        return await self._llm_profile.update(profile_id, actor=actor, **fields)

    async def llm_profile_delete(
        self, profile_id: str, *, actor: str,
    ) -> bool:
        return await self._llm_profile.delete(profile_id, actor=actor)

    async def llm_profile_set_default(
        self, profile_id: str, *, actor: str,
    ) -> bool:
        return await self._llm_profile.set_default(profile_id, actor=actor)

    async def llm_profile_set_default_by_name(
        self, name: str, *, actor: str,
    ) -> bool:
        return await self._llm_profile.set_default_by_name(name, actor=actor)

    async def llm_profile_get(
        self, profile_id: str, *, include_key: bool = True,
    ) -> LLMProfile | None:
        return await self._llm_profile.get(profile_id, include_key=include_key)

    async def llm_profile_list(
        self, *, include_keys: bool = False,
    ) -> list[LLMProfile]:
        return await self._llm_profile.list(include_keys=include_keys)

    async def llm_profile_get_default(self) -> LLMProfile | None:
        return await self._llm_profile.get_default()

    # ============ 域 15: LLM 路由 ============
    async def llm_route_upsert(
        self, route_key: str, profile_id: str, *, actor: str,
    ) -> None:
        await self._llm_route.upsert(route_key, profile_id, actor=actor)

    async def llm_route_delete(self, route_key: str, *, actor: str) -> bool:
        return await self._llm_route.delete(route_key, actor=actor)

    async def llm_route_get(self, route_key: str) -> LLMRoute | None:
        return await self._llm_route.get(route_key)

    async def llm_route_list_all(self) -> list[LLMRoute]:
        return await self._llm_route.list_all()

    async def llm_route_clear_for_profile(
        self, profile_id: str, *, actor: str,
    ) -> int:
        return await self._llm_route.clear_for_profile(profile_id, actor=actor)

    async def llm_route_delete_purpose_overrides(
        self, component: str, *, actor: str,
    ) -> list[str]:
        return await self._llm_route.delete_purpose_overrides_for(
            component, actor=actor,
        )
