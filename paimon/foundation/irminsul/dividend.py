"""理财数据域 —— 世界树域 8（岩神 · 红利股追踪）

唯一写入者：岩神
读取者：岩神、WebUI `/wealth` 面板（经岩神/facade）

三张表：
- dividend_watchlist: 行业均衡选出的推荐股池
- dividend_snapshot:  每日评分快照（UNIQUE scan_date + stock_code）
- dividend_changes:   变化事件（entered / exited / score_change）
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any

import aiosqlite
from loguru import logger


# ============ dataclasses ============


@dataclass
class WatchlistEntry:
    stock_code: str
    stock_name: str = ""
    industry: str = ""
    added_date: str = ""      # 'YYYY-MM-DD'
    last_refresh: str = ""


@dataclass
class ScoreSnapshot:
    id: int = 0
    scan_date: str = ""
    stock_code: str = ""
    stock_name: str = ""
    industry: str = ""
    total_score: float = 0.0
    sustainability_score: float = 0.0
    fortress_score: float = 0.0
    valuation_score: float = 0.0
    track_record_score: float = 0.0
    momentum_score: float = 0.0
    penalty: float = 0.0
    dividend_yield: float = 0.0
    pe: float = 0.0
    pb: float = 0.0
    roe: float = 0.0
    market_cap: float = 0.0
    reasons: str = ""
    advice: str = ""
    detail: dict = field(default_factory=dict)
    created_at: float = 0.0


@dataclass
class ChangeEvent:
    id: int = 0
    event_date: str = ""
    stock_code: str = ""
    stock_name: str = ""
    event_type: str = ""            # 'entered' | 'exited' | 'score_change'
    old_value: float | None = None
    new_value: float | None = None
    description: str = ""
    created_at: float = 0.0


# ============ 列映射常量 ============

_SNAPSHOT_COLS = (
    "id", "scan_date", "stock_code", "stock_name", "industry",
    "total_score", "sustainability_score", "fortress_score",
    "valuation_score", "track_record_score", "momentum_score", "penalty",
    "dividend_yield", "pe", "pb", "roe", "market_cap",
    "reasons", "advice", "detail_json", "created_at",
)

_CHANGE_COLS = (
    "id", "event_date", "stock_code", "stock_name", "event_type",
    "old_value", "new_value", "description", "created_at",
)


# ============ Repos ============


class DividendWatchlistRepo:
    def __init__(self, db: aiosqlite.Connection):
        self._db = db

    async def save(self, entries: list[WatchlistEntry], refresh_date: str, actor: str) -> int:
        """全量刷新 watchlist：清空表 + 批量写入。返回写入条数。"""
        await self._db.execute("DELETE FROM dividend_watchlist")
        for e in entries:
            added = e.added_date or refresh_date
            await self._db.execute(
                "INSERT INTO dividend_watchlist "
                "(stock_code, stock_name, industry, added_date, last_refresh) "
                "VALUES (?,?,?,?,?)",
                (e.stock_code, e.stock_name, e.industry, added, refresh_date),
            )
        await self._db.commit()
        logger.info(
            "[世界树] {}·watchlist 刷新 {} 只 refresh={}",
            actor, len(entries), refresh_date,
        )
        return len(entries)

    async def list(self) -> list[WatchlistEntry]:
        async with self._db.execute(
            "SELECT stock_code, stock_name, industry, added_date, last_refresh "
            "FROM dividend_watchlist ORDER BY industry, stock_code",
        ) as cur:
            rows = await cur.fetchall()
        return [
            WatchlistEntry(
                stock_code=r[0], stock_name=r[1], industry=r[2],
                added_date=r[3], last_refresh=r[4],
            )
            for r in rows
        ]

    async def last_refresh(self) -> str | None:
        async with self._db.execute(
            "SELECT MAX(last_refresh) FROM dividend_watchlist",
        ) as cur:
            row = await cur.fetchone()
        return row[0] if row and row[0] else None


class ScoreSnapshotRepo:
    def __init__(self, db: aiosqlite.Connection):
        self._db = db

    async def upsert(self, scan_date: str, snap: ScoreSnapshot, actor: str) -> None:
        """插入或更新当日某股快照（UNIQUE(scan_date, stock_code)）。"""
        now = time.time()
        await self._db.execute(
            "INSERT INTO dividend_snapshot "
            "(scan_date, stock_code, stock_name, industry, "
            " total_score, sustainability_score, fortress_score, "
            " valuation_score, track_record_score, momentum_score, penalty, "
            " dividend_yield, pe, pb, roe, market_cap, "
            " reasons, advice, detail_json, created_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?) "
            "ON CONFLICT(scan_date, stock_code) DO UPDATE SET "
            " stock_name = excluded.stock_name, industry = excluded.industry, "
            " total_score = excluded.total_score, "
            " sustainability_score = excluded.sustainability_score, "
            " fortress_score = excluded.fortress_score, "
            " valuation_score = excluded.valuation_score, "
            " track_record_score = excluded.track_record_score, "
            " momentum_score = excluded.momentum_score, penalty = excluded.penalty, "
            " dividend_yield = excluded.dividend_yield, pe = excluded.pe, "
            " pb = excluded.pb, roe = excluded.roe, market_cap = excluded.market_cap, "
            " reasons = excluded.reasons, advice = excluded.advice, "
            " detail_json = excluded.detail_json",
            (
                scan_date, snap.stock_code, snap.stock_name, snap.industry,
                snap.total_score, snap.sustainability_score, snap.fortress_score,
                snap.valuation_score, snap.track_record_score, snap.momentum_score, snap.penalty,
                snap.dividend_yield, snap.pe, snap.pb, snap.roe, snap.market_cap,
                snap.reasons, snap.advice,
                json.dumps(snap.detail or {}, ensure_ascii=False),
                now,
            ),
        )
        await self._db.commit()

    async def clear_date(self, scan_date: str, actor: str) -> int:
        async with self._db.execute(
            "DELETE FROM dividend_snapshot WHERE scan_date = ?",
            (scan_date,),
        ) as cur:
            n = cur.rowcount
        await self._db.commit()
        if n > 0:
            logger.debug("[世界树] {}·snapshot 清理 date={} count={}", actor, scan_date, n)
        return n

    async def latest_date(self) -> str | None:
        async with self._db.execute(
            "SELECT MAX(scan_date) FROM dividend_snapshot",
        ) as cur:
            row = await cur.fetchone()
        return row[0] if row and row[0] else None

    async def at_date(self, scan_date: str) -> list[ScoreSnapshot]:
        """指定日期的所有 snapshots（无 limit、不排序）。

        日更场景需要从最近一次全扫描的快照里拿候选池股票的 name / industry，
        latest_top(n) 受 latest_date=今天 影响只能拿到 today 的 watchlist 21 只
        会丢候选池里非 watchlist 那 ~330 只的元数据。
        """
        if not scan_date:
            return []
        async with self._db.execute(
            f"SELECT {', '.join(_SNAPSHOT_COLS)} FROM dividend_snapshot "
            "WHERE scan_date = ?",
            (scan_date,),
        ) as cur:
            rows = await cur.fetchall()
        return [self._row_to_snap(r) for r in rows]

    async def codes_at_date(self, scan_date: str) -> list[str]:
        """指定 scan_date 的所有 stock_code。

        日更场景传入 watchlist.last_refresh（最近一次全扫描日期），拿到候选池
        ~300 只 codes。不能传 latest_date —— latest_date 一般是今天（被 daily
        刚写进去 21 只），会形成"日更只扫 21 只 → today snapshot 21 → 下次
        日更只看到 21"的循环死锁。
        """
        if not scan_date:
            return []
        async with self._db.execute(
            "SELECT stock_code FROM dividend_snapshot WHERE scan_date = ?",
            (scan_date,),
        ) as cur:
            rows = await cur.fetchall()
        return [r[0] for r in rows]

    async def latest_top(self, n: int = 100) -> list[ScoreSnapshot]:
        """取最新扫描日的 top n（按 total_score 降序）。"""
        d = await self.latest_date()
        if not d:
            return []
        async with self._db.execute(
            f"SELECT {', '.join(_SNAPSHOT_COLS)} FROM dividend_snapshot "
            "WHERE scan_date = ? ORDER BY total_score DESC LIMIT ?",
            (d, n),
        ) as cur:
            rows = await cur.fetchall()
        return [self._row_to_snap(r) for r in rows]

    async def latest_for_watchlist(self) -> list[ScoreSnapshot]:
        """取 watchlist 股票在最新扫描日的快照。"""
        d = await self.latest_date()
        if not d:
            return []
        async with self._db.execute(
            f"SELECT {', '.join('s.' + c for c in _SNAPSHOT_COLS)} "
            "FROM dividend_snapshot s "
            "JOIN dividend_watchlist w ON s.stock_code = w.stock_code "
            "WHERE s.scan_date = ? ORDER BY s.total_score DESC",
            (d,),
        ) as cur:
            rows = await cur.fetchall()
        return [self._row_to_snap(r) for r in rows]

    async def history(self, stock_code: str, days: int = 90) -> list[ScoreSnapshot]:
        """取某股**最近 N 天**的评分历史（按 scan_date 升序，折线图用）。

        按 scan_date >= (today - days) 过滤；daily cron 工作日跑，90 天约含 65 条。
        """
        from datetime import date as _date, timedelta as _td
        cutoff = (_date.today() - _td(days=days)).isoformat()
        async with self._db.execute(
            f"SELECT {', '.join(_SNAPSHOT_COLS)} FROM dividend_snapshot "
            "WHERE stock_code = ? AND scan_date >= ? "
            "ORDER BY scan_date ASC LIMIT 500",
            (stock_code, cutoff),
        ) as cur:
            rows = await cur.fetchall()
        return [self._row_to_snap(r) for r in rows]

    async def get_one(self, scan_date: str, stock_code: str) -> ScoreSnapshot | None:
        async with self._db.execute(
            f"SELECT {', '.join(_SNAPSHOT_COLS)} FROM dividend_snapshot "
            "WHERE scan_date = ? AND stock_code = ?",
            (scan_date, stock_code),
        ) as cur:
            row = await cur.fetchone()
        return self._row_to_snap(row) if row else None

    def _row_to_snap(self, row) -> ScoreSnapshot:
        d = dict(zip(_SNAPSHOT_COLS, row))
        raw_detail = d.pop("detail_json", "{}")
        try:
            detail = json.loads(raw_detail) if raw_detail else {}
        except (json.JSONDecodeError, TypeError):
            detail = {}
        return ScoreSnapshot(detail=detail, **d)


class ChangeEventRepo:
    def __init__(self, db: aiosqlite.Connection):
        self._db = db

    async def save(self, events: list[ChangeEvent], actor: str) -> int:
        """同日幂等保存：(event_date, stock_code, event_type) 三元组唯一。

        先 DELETE 相同三元组的旧记录再 INSERT，避免同日多次扫描（cron + 手动
        触发日更/重评分）产生重复 changes 行（与 dividend_events 同日去重一致）。
        """
        if not events:
            return 0
        now = time.time()
        for e in events:
            await self._db.execute(
                "DELETE FROM dividend_changes "
                "WHERE event_date = ? AND stock_code = ? AND event_type = ?",
                (e.event_date, e.stock_code, e.event_type),
            )
            await self._db.execute(
                "INSERT INTO dividend_changes "
                "(event_date, stock_code, stock_name, event_type, "
                " old_value, new_value, description, created_at) "
                "VALUES (?,?,?,?,?,?,?,?)",
                (
                    e.event_date, e.stock_code, e.stock_name, e.event_type,
                    e.old_value, e.new_value, e.description, now,
                ),
            )
        await self._db.commit()
        logger.info(
            "[世界树] {}·changes 入库 {} 条 date={}（同日去重）",
            actor, len(events), events[0].event_date,
        )
        return len(events)

    async def recent(self, days: int = 7) -> list[ChangeEvent]:
        cutoff = time.time() - days * 86400
        async with self._db.execute(
            f"SELECT {', '.join(_CHANGE_COLS)} FROM dividend_changes "
            "WHERE created_at >= ? ORDER BY created_at DESC LIMIT 500",
            (cutoff,),
        ) as cur:
            rows = await cur.fetchall()
        return [self._row_to_change(r) for r in rows]

    async def cleanup_before(self, keep_days: int, actor: str) -> int:
        cutoff = time.time() - keep_days * 86400
        async with self._db.execute(
            "DELETE FROM dividend_changes WHERE created_at < ?",
            (cutoff,),
        ) as cur:
            n = cur.rowcount
        await self._db.commit()
        if n > 0:
            logger.info("[世界树] {}·changes 清理 {} 条（超 {} 天）", actor, n, keep_days)
        return n

    def _row_to_change(self, row) -> ChangeEvent:
        d = dict(zip(_CHANGE_COLS, row))
        return ChangeEvent(**d)


class DividendRepo:
    """门面聚合：三个子 Repo + 生命周期清理。"""

    def __init__(self, db: aiosqlite.Connection):
        self.watchlist = DividendWatchlistRepo(db)
        self.snapshot = ScoreSnapshotRepo(db)
        self.changes = ChangeEventRepo(db)
        self._db = db

    async def cleanup(self, keep_days: int, actor: str) -> dict:
        """清理超 keep_days 的 snapshot + changes。"""
        cutoff = time.time() - keep_days * 86400
        async with self._db.execute(
            "DELETE FROM dividend_snapshot WHERE created_at < ?",
            (cutoff,),
        ) as cur:
            n_snap = cur.rowcount
        await self._db.commit()
        n_change = await self.changes.cleanup_before(keep_days, actor)
        if n_snap > 0:
            logger.info("[世界树] {}·snapshot 清理 {} 条（超 {} 天）", actor, n_snap, keep_days)
        return {"snapshot": n_snap, "changes": n_change}
