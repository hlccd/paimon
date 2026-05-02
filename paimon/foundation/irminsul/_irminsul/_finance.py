"""世界树 façade · 理财数据域 8/8.5/8.6/8.7：dividend + dividend_event + user_watch + mihoyo。"""
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

class _FinanceMixin:
    # ============ 域 8: 理财（岩神 · 红利股追踪）============

    # -- watchlist --
    async def watchlist_save(
        self, entries: list[WatchlistEntry], refresh_date: str, *, actor: str,
    ) -> int:
        return await self._dividend.watchlist.save(entries, refresh_date, actor=actor)

    async def watchlist_get(self) -> list[WatchlistEntry]:
        return await self._dividend.watchlist.list()

    async def watchlist_last_refresh(self) -> str | None:
        return await self._dividend.watchlist.last_refresh()

    # -- snapshot --
    async def snapshot_upsert(
        self, scan_date: str, snap: ScoreSnapshot, *, actor: str,
    ) -> None:
        await self._dividend.snapshot.upsert(scan_date, snap, actor=actor)

    async def snapshot_clear_date(self, scan_date: str, *, actor: str) -> int:
        return await self._dividend.snapshot.clear_date(scan_date, actor=actor)

    async def snapshot_latest_date(self) -> str | None:
        return await self._dividend.snapshot.latest_date()

    async def snapshot_latest_top(self, n: int = 100) -> list[ScoreSnapshot]:
        return await self._dividend.snapshot.latest_top(n)

    async def snapshot_codes_at_date(self, scan_date: str) -> list[str]:
        """指定日期的所有 stock_code。日更传 watchlist_last_refresh 拿候选池。"""
        return await self._dividend.snapshot.codes_at_date(scan_date)

    async def snapshot_at_date(self, scan_date: str) -> list[ScoreSnapshot]:
        """指定日期的所有完整 snapshot。日更用它拿候选池股票的 name / industry。"""
        return await self._dividend.snapshot.at_date(scan_date)

    async def snapshot_latest_for_watchlist(self) -> list[ScoreSnapshot]:
        return await self._dividend.snapshot.latest_for_watchlist()

    async def snapshot_history(
        self, stock_code: str, days: int = 90,
    ) -> list[ScoreSnapshot]:
        return await self._dividend.snapshot.history(stock_code, days)

    async def snapshot_get(
        self, scan_date: str, stock_code: str,
    ) -> ScoreSnapshot | None:
        return await self._dividend.snapshot.get_one(scan_date, stock_code)

    # -- changes --
    async def change_save(
        self, events: list[ChangeEvent], *, actor: str,
    ) -> int:
        return await self._dividend.changes.save(events, actor=actor)

    async def change_recent(self, days: int = 7) -> list[ChangeEvent]:
        return await self._dividend.changes.recent(days)

    # -- 生命周期 --
    async def dividend_cleanup(self, keep_days: int = 180, *, actor: str) -> dict:
        return await self._dividend.cleanup(keep_days, actor=actor)

    # ============ 域 8.5: 理财事件聚类 ============

    async def dividend_event_upsert(
        self, *, stock_code: str, event_type: str,
        severity: str, stock_name: str, industry: str,
        title: str, summary: str,
        timeline_entry: dict,
        detail: dict | None = None,
        actor: str = "岩神",
    ) -> tuple[str, bool]:
        return await self._dividend_event.upsert(
            stock_code=stock_code, event_type=event_type,
            severity=severity, stock_name=stock_name, industry=industry,
            title=title, summary=summary,
            timeline_entry=timeline_entry, detail=detail, actor=actor,
        )

    async def dividend_event_mark_resolved(
        self, stock_code: str, *,
        exclude_types: set[str] | None = None,
        actor: str = "岩神",
    ) -> int:
        return await self._dividend_event.mark_resolved(
            stock_code, exclude_types=exclude_types, actor=actor,
        )

    async def dividend_event_list(
        self, *, severity: str | None = None,
        status: str | None = "active",
        stock_code: str | None = None,
        days: int | None = None,
        limit: int = 200,
    ) -> list[DividendEvent]:
        return await self._dividend_event.list(
            severity=severity, status=status, stock_code=stock_code,
            days=days, limit=limit,
        )

    async def dividend_event_count_by_severity(
        self, *, days: int | None = None, status: str | None = "active",
    ) -> dict[str, int]:
        return await self._dividend_event.count_by_severity(days=days, status=status)

    async def dividend_event_get(self, event_id: str) -> DividendEvent | None:
        return await self._dividend_event.get(event_id)

    async def dividend_event_cleanup(
        self, keep_days: int = 180, *, actor: str,
    ) -> int:
        return await self._dividend_event.cleanup_before(keep_days, actor=actor)

    # ============ 域 8.6: 用户关注股 ============

    async def user_watch_add(self, entry: UserWatchEntry, *, actor: str) -> bool:
        return await self._user_watchlist.add(entry, actor=actor)

    async def user_watch_remove(self, stock_code: str, *, actor: str) -> bool:
        return await self._user_watchlist.remove(stock_code, actor=actor)

    async def user_watch_update(
        self, stock_code: str, *,
        note: str | None = None, alert_pct: float | None = None,
        stock_name: str | None = None,
        actor: str,
    ) -> bool:
        return await self._user_watchlist.update(
            stock_code, note=note, alert_pct=alert_pct, stock_name=stock_name, actor=actor,
        )

    async def user_watch_list(self) -> list[UserWatchEntry]:
        return await self._user_watchlist.list()

    async def user_watch_get(self, stock_code: str) -> UserWatchEntry | None:
        return await self._user_watchlist.get(stock_code)

    async def user_watch_codes(self) -> list[str]:
        return await self._user_watchlist.codes()

    async def user_watch_price_upsert(
        self, rows: list[UserWatchPrice], *, actor: str,
    ) -> int:
        return await self._user_watchlist.price_upsert(rows, actor=actor)

    async def user_watch_price_latest(self, stock_code: str) -> UserWatchPrice | None:
        return await self._user_watchlist.price_latest(stock_code)

    async def user_watch_price_recent(
        self, stock_code: str, days: int = 30,
    ) -> list[UserWatchPrice]:
        return await self._user_watchlist.price_recent(stock_code, days)

    async def user_watch_price_series(
        self, stock_code: str, column: str,
    ) -> list[float]:
        return await self._user_watchlist.price_series(stock_code, column)

    async def user_watch_price_max_date(self, stock_code: str) -> str | None:
        return await self._user_watchlist.price_max_date(stock_code)

    # ============ 域 8.7: 米哈游账号 ============

    async def mihoyo_account_upsert(self, acc: MihoyoAccount, *, actor: str) -> None:
        await self._mihoyo.account_upsert(acc, actor=actor)

    async def mihoyo_account_remove(self, game: str, uid: str, *, actor: str) -> bool:
        return await self._mihoyo.account_remove(game, uid, actor=actor)

    async def mihoyo_account_get(self, game: str, uid: str) -> MihoyoAccount | None:
        return await self._mihoyo.account_get(game, uid)

    async def mihoyo_account_list(self, *, game: str | None = None) -> list[MihoyoAccount]:
        return await self._mihoyo.account_list(game=game)

    async def mihoyo_account_update_authkey(
        self, uid: str, authkey: str, *, game: str = "gs", actor: str,
    ) -> None:
        await self._mihoyo.account_update_authkey(uid, authkey, game=game, actor=actor)

    async def mihoyo_account_set_sign_time(self, game: str, uid: str, ts: float) -> None:
        await self._mihoyo.account_set_sign_time(game, uid, ts)

    async def mihoyo_note_upsert(self, n: MihoyoNote, *, actor: str) -> None:
        await self._mihoyo.note_upsert(n, actor=actor)

    async def mihoyo_note_get(self, game: str, uid: str) -> MihoyoNote | None:
        return await self._mihoyo.note_get(game, uid)

    async def mihoyo_note_list(self) -> list[MihoyoNote]:
        return await self._mihoyo.note_list()

    async def mihoyo_abyss_upsert(self, a: MihoyoAbyss, *, actor: str) -> None:
        await self._mihoyo.abyss_upsert(a, actor=actor)

    async def mihoyo_abyss_latest(
        self, game: str, uid: str, abyss_type: str,
    ) -> MihoyoAbyss | None:
        return await self._mihoyo.abyss_latest(game, uid, abyss_type)

    async def mihoyo_gacha_insert(
        self, items: list[MihoyoGacha], *, actor: str,
    ) -> int:
        return await self._mihoyo.gacha_insert(items, actor=actor)

    async def mihoyo_gacha_max_id(self, game: str, uid: str, gacha_type: str) -> str:
        return await self._mihoyo.gacha_max_id(game, uid, gacha_type)

    async def mihoyo_gacha_list(
        self, game: str, uid: str, gacha_type: str, *, limit: int = 500,
    ) -> list[MihoyoGacha]:
        return await self._mihoyo.gacha_list(game, uid, gacha_type, limit=limit)

    async def mihoyo_gacha_stats(self, game: str, uid: str, gacha_type: str) -> dict:
        return await self._mihoyo.gacha_stats(game, uid, gacha_type)

    async def mihoyo_character_upsert(
        self, items: list[MihoyoCharacter], *, actor: str,
    ) -> int:
        return await self._mihoyo.character_upsert(items, actor=actor)

    async def mihoyo_character_list(self, game: str, uid: str) -> list[MihoyoCharacter]:
        return await self._mihoyo.character_list(game, uid)
