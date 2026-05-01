"""世界树主门面 —— 全系统唯一存储层。

对外暴露扁平 `<域>_<动作>` 方法（共 9 个域 ~45 个方法），内部委托到各 domain repo。
"""
from __future__ import annotations

from pathlib import Path

import aiosqlite
from loguru import logger

from ._db import init_db
from .audit import AuditEntry, AuditRepo
from .authz import Authz, AuthzRepo
from .dividend import ChangeEvent, DividendRepo, ScoreSnapshot, WatchlistEntry
from .dividend_event import DividendEvent, DividendEventRepo
from .user_watchlist import UserWatchEntry, UserWatchlistRepo, UserWatchPrice
from .mihoyo import (
    MihoyoAbyss, MihoyoAccount, MihoyoCharacter, MihoyoGacha, MihoyoNote, MihoyoRepo,
)
from .knowledge import KnowledgeRepo
from .memory import Memory, MemoryMeta, MemoryRepo
from .session import SessionMeta, SessionRecord, SessionRepo
from .skills import SkillDecl, SkillRepo
from .feed_event import FeedEvent, FeedEventRepo
from .llm_profile import LLMProfile, LLMProfileRepo
from .llm_route import LLMRoute, LLMRouteRepo
from .push_archive import PushArchiveRecord, PushArchiveRepo
from .selfcheck import SelfcheckRepo, SelfcheckRun
from .subscription import FeedItem, Subscription, SubscriptionRepo
from .task import FlowEntry, ProgressEntry, Subtask, TaskEdict, TaskRepo
from .schedule import ScheduleRepo, ScheduledTask
from .token import TokenRepo, TokenRow


class Irminsul:
    """世界树：全系统唯一存储层。

    对外按 9 个数据域提供读/写/快照/列表接口。所有写/删方法必传 actor（服务方中文名），
    内部统一打 `[世界树] <actor>·<动作> <对象>` INFO 日志。
    """

    def __init__(self, home: Path):
        self._home = home
        self._db_path = home / "irminsul.db"
        self._fs_root = home / "irminsul"
        self._knowledge_root = self._fs_root / "knowledge"
        self._memory_root = self._fs_root / "memory"
        self._selfcheck_root = self._fs_root / "selfcheck"
        self._db: aiosqlite.Connection | None = None
        # Repo 延迟到 initialize
        self._authz: AuthzRepo | None = None
        self._skill: SkillRepo | None = None
        self._knowledge: KnowledgeRepo | None = None
        self._memory: MemoryRepo | None = None
        self._task: TaskRepo | None = None
        self._token: TokenRepo | None = None
        self._audit: AuditRepo | None = None
        self._dividend: DividendRepo | None = None
        self._dividend_event: DividendEventRepo | None = None
        self._user_watchlist: UserWatchlistRepo | None = None
        self._mihoyo: MihoyoRepo | None = None
        self._session: SessionRepo | None = None
        self._schedule: ScheduleRepo | None = None
        self._subscription: SubscriptionRepo | None = None
        self._feed_event: FeedEventRepo | None = None
        self._push_archive: PushArchiveRepo | None = None
        self._selfcheck: SelfcheckRepo | None = None
        self._llm_profile: LLMProfileRepo | None = None
        self._llm_route: LLMRouteRepo | None = None

    async def initialize(self) -> None:
        self._home.mkdir(parents=True, exist_ok=True)
        self._fs_root.mkdir(parents=True, exist_ok=True)
        self._knowledge_root.mkdir(parents=True, exist_ok=True)
        self._memory_root.mkdir(parents=True, exist_ok=True)
        self._selfcheck_root.mkdir(parents=True, exist_ok=True)

        self._db = await init_db(self._db_path)

        self._authz = AuthzRepo(self._db)
        self._skill = SkillRepo(self._db)
        self._knowledge = KnowledgeRepo(self._knowledge_root)
        self._memory = MemoryRepo(self._db, self._memory_root)
        self._task = TaskRepo(self._db)
        self._token = TokenRepo(self._db)
        self._audit = AuditRepo(self._db)
        self._dividend = DividendRepo(self._db)
        self._dividend_event = DividendEventRepo(self._db)
        self._user_watchlist = UserWatchlistRepo(self._db)
        self._mihoyo = MihoyoRepo(self._db)
        self._session = SessionRepo(self._db)
        self._schedule = ScheduleRepo(self._db)
        self._subscription = SubscriptionRepo(self._db)
        self._feed_event = FeedEventRepo(self._db)
        self._push_archive = PushArchiveRepo(self._db)
        self._selfcheck = SelfcheckRepo(self._db, self._selfcheck_root)
        self._llm_profile = LLMProfileRepo(self._db)
        self._llm_route = LLMRouteRepo(self._db)

        logger.info("[世界树] 初始化完成  db={}", self._db_path)

        # 会话迁移（幂等）
        legacy_sessions = self._home / "sessions"
        if legacy_sessions.exists():
            imported = await self._session.migrate_from_json(legacy_sessions)
            if imported > 0:
                logger.info("[世界树] 会话迁移  共导入 {} 条", imported)

    async def close(self) -> None:
        if self._db:
            await self._db.close()
            self._db = None
            logger.info("[世界树] 已关闭")

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
