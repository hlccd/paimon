"""世界树 façade · 运行时数据域 9/10/11/11.5：session + schedule + subscription + feed_event。"""
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

class _RuntimeMixin:
    # ============ 域 9: 会话 ============
    async def session_upsert(self, rec: SessionRecord, *, actor: str) -> None:
        await self._session.upsert(rec, actor=actor)

    async def session_load(self, session_id: str) -> SessionRecord | None:
        return await self._session.load(session_id)

    async def session_list(
        self, *, channel_key: str | None = None,
        archived: bool = False, limit: int = 50,
    ) -> list[SessionMeta]:
        return await self._session.list(
            channel_key=channel_key, archived=archived, limit=limit,
        )

    async def session_list_all_full(self) -> list[SessionRecord]:
        """启动时一次性加载所有活跃会话，给 SessionManager 初始化缓存用。"""
        return await self._session.list_all_full()

    async def session_delete(self, session_id: str, *, actor: str) -> bool:
        return await self._session.delete(session_id, actor=actor)

    async def session_archive(self, session_id: str, *, actor: str) -> bool:
        return await self._session.archive(session_id, actor=actor)

    async def session_archive_if_idle(
        self, *, now: float, inactive_seconds: float, actor: str,
    ) -> list[str]:
        return await self._session.archive_if_idle(
            now=now, inactive_seconds=inactive_seconds, actor=actor,
        )

    async def session_purge_expired(
        self, *, now: float, archived_ttl_seconds: float, actor: str,
    ) -> list[str]:
        return await self._session.purge_expired(
            now=now, archived_ttl_seconds=archived_ttl_seconds, actor=actor,
        )

    async def session_clear_channel_binding(self, channel_key: str, *, except_session: str = "") -> None:
        await self._session.clear_channel_binding(channel_key, except_session=except_session)

    # ============ 域 10: 定时任务（三月）============
    async def schedule_create(self, task: ScheduledTask, *, actor: str) -> str:
        return await self._schedule.create(task, actor=actor)

    async def schedule_get(self, task_id: str) -> ScheduledTask | None:
        return await self._schedule.get(task_id)

    async def schedule_list(self, *, enabled_only: bool = False) -> list[ScheduledTask]:
        return await self._schedule.list_all(enabled_only=enabled_only)

    async def schedule_list_due(self, now: float) -> list[ScheduledTask]:
        return await self._schedule.list_due(now)

    async def schedule_update(self, task_id: str, *, actor: str, **fields) -> bool:
        return await self._schedule.update(task_id, actor=actor, **fields)

    async def schedule_delete(self, task_id: str, *, actor: str) -> bool:
        return await self._schedule.delete(task_id, actor=actor)

    # ============ 域 11: 订阅（风神）============
    async def subscription_create(self, sub: Subscription, *, actor: str) -> str:
        return await self._subscription.create(sub, actor=actor)

    async def subscription_get(self, sub_id: str) -> Subscription | None:
        return await self._subscription.get(sub_id)

    async def subscription_list(
        self, *, user_id: str | None = None, enabled_only: bool = False,
    ) -> list[Subscription]:
        return await self._subscription.list(
            user_id=user_id, enabled_only=enabled_only,
        )

    async def subscription_update(
        self, sub_id: str, *, actor: str, **fields,
    ) -> bool:
        return await self._subscription.update(sub_id, actor=actor, **fields)

    async def subscription_delete(self, sub_id: str, *, actor: str) -> bool:
        return await self._subscription.delete(sub_id, actor=actor)

    async def subscription_list_by_binding(
        self, binding_kind: str, binding_id: str = "",
    ) -> list[Subscription]:
        return await self._subscription.list_by_binding(binding_kind, binding_id)

    async def subscription_ensure_for(
        self, *,
        binding_kind: str,
        binding_id: str,
        query: str,
        schedule_cron: str,
        channel_name: str,
        chat_id: str,
        max_items: int = 10,
        engine: str = "",
        actor: str,
    ) -> Subscription:
        return await self._subscription.ensure_for(
            binding_kind=binding_kind, binding_id=binding_id,
            query=query, schedule_cron=schedule_cron,
            channel_name=channel_name, chat_id=chat_id,
            max_items=max_items, engine=engine, actor=actor,
        )

    async def subscription_clear_for(
        self, binding_kind: str, binding_id: str, *, actor: str,
    ) -> list[str]:
        return await self._subscription.clear_for(
            binding_kind, binding_id, actor=actor,
        )

    async def feed_items_insert(
        self, sub_id: str, items: list[dict], *, actor: str,
    ) -> list[int]:
        return await self._subscription.insert_feed_items(sub_id, items, actor=actor)

    async def feed_items_list(
        self, *,
        sub_id: str | None = None, since: float | None = None,
        only_unpushed: bool = False,
        event_id: str | None = None,
        limit: int = 200,
    ) -> list[FeedItem]:
        return await self._subscription.list_feed_items(
            sub_id=sub_id, since=since, only_unpushed=only_unpushed,
            event_id=event_id, limit=limit,
        )

    async def feed_items_mark_pushed(
        self, ids: list[int], digest_id: str, *, actor: str,
    ) -> int:
        return await self._subscription.mark_feed_items_pushed(
            ids, digest_id, actor=actor,
        )

    async def feed_items_existing_urls(
        self, sub_id: str, *, since_ts: float = 0,
    ) -> set[str]:
        return await self._subscription.existing_urls(sub_id, since_ts=since_ts)

    async def feed_items_count(
        self, *, sub_id: str | None = None, since: float | None = None,
    ) -> int:
        return await self._subscription.count_feed_items(sub_id=sub_id, since=since)

    async def feed_items_insert_with_records(
        self, sub_id: str, items: list[dict], *, actor: str,
    ) -> list[dict]:
        """带 records 的入库（含 db id + 原字段），供风神事件聚类用。"""
        return await self._subscription.insert_feed_items_with_records(
            sub_id, items, actor=actor,
        )

    async def feed_items_attach_event(
        self, item_ids: list[int], event_id: str, *,
        sentiment_score: float = 0.0,
        sentiment_label: str = "",
        actor: str,
    ) -> int:
        """把一组 feed_items 关联到 event_id + 写入条目级情感（覆盖）。"""
        return await self._subscription.attach_event(
            item_ids, event_id,
            sentiment_score=sentiment_score,
            sentiment_label=sentiment_label,
            actor=actor,
        )

    # ============ 域 11.5: 事件聚类（风神 L1 舆情）============
    async def feed_event_create(self, event: FeedEvent, *, actor: str) -> str:
        return await self._feed_event.create(event, actor=actor)

    async def feed_event_get(self, event_id: str) -> FeedEvent | None:
        return await self._feed_event.get(event_id)

    async def feed_event_update(
        self, event_id: str, *, actor: str,
        item_count_inc: int = 0,
        pushed_count_inc: int = 0,
        **fields,
    ) -> bool:
        return await self._feed_event.update(
            event_id, actor=actor,
            item_count_inc=item_count_inc,
            pushed_count_inc=pushed_count_inc,
            **fields,
        )

    async def feed_event_list(
        self, *,
        sub_id: str | None = None,
        since: float | None = None,
        severity: str | None = None,
        limit: int = 100,
    ) -> list[FeedEvent]:
        return await self._feed_event.list(
            sub_id=sub_id, since=since, severity=severity, limit=limit,
        )

    async def feed_event_count(
        self, *,
        sub_id: str | None = None,
        since: float | None = None,
        severity: str | None = None,
    ) -> int:
        return await self._feed_event.count(
            sub_id=sub_id, since=since, severity=severity,
        )

    async def feed_event_count_by_severity(
        self, *,
        since: float | None = None,
        sub_id: str | None = None,
    ) -> dict[str, int]:
        return await self._feed_event.count_by_severity(
            since=since, sub_id=sub_id,
        )

    async def feed_event_avg_sentiment(
        self, *,
        since: float | None = None,
        sub_id: str | None = None,
    ) -> float:
        return await self._feed_event.avg_sentiment(since=since, sub_id=sub_id)

    async def feed_event_timeline(
        self, *, days: int, sub_id: str | None = None,
    ) -> list[dict]:
        return await self._feed_event.timeline(days=days, sub_id=sub_id)

    async def feed_event_sources_top(
        self, *, days: int, limit: int = 10,
        sub_id: str | None = None,
    ) -> list[dict]:
        return await self._feed_event.sources_top(
            days=days, limit=limit, sub_id=sub_id,
        )

    async def feed_event_delete(self, event_id: str, *, actor: str) -> bool:
        return await self._feed_event.delete(event_id, actor=actor)

    async def feed_event_sweep_old(
        self, *, retention_seconds: float, actor: str,
    ) -> int:
        return await self._feed_event.sweep_old(
            retention_seconds=retention_seconds, actor=actor,
        )
