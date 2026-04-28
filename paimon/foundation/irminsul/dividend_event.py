"""理财事件聚类数据域 —— 域 8.5（岩神·红利股事件化）

唯一写入者：岩神（_aggregate_events 后调 upsert）
读取者：岩神事件查询、WebUI /wealth 事件 tab、digest 生成

跨扫描 merge 语义：
- 同 stock_code + event_type 在 7 天内 → merge 进 timeline + occurrence_count++
- 超 7 天 → 视为新事件（旧的留在表里不动，等 sweep 清）
- 本轮某股没命中此 type 但表里有 active → mark resolved（自动闭环）

severity 升级：merge 时只升不降（p2→p1 升级，p1→p2 不退）。
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4

import aiosqlite
from loguru import logger


_MERGE_WINDOW_SECONDS = 7 * 86400        # 7 天内同事件 merge
_TIMELINE_MAX_ENTRIES = 30               # 单事件 timeline 最多保留 30 项

_DIVIDEND_EVENT_COLS = (
    "id", "stock_code", "stock_name", "industry", "severity", "event_type",
    "title", "summary", "timeline_json", "first_seen_at", "last_seen_at",
    "last_pushed_at", "last_severity", "status", "occurrence_count",
    "detail_json", "created_at", "updated_at",
)

# severity 排名：数字越小越严重，用于"升级"判定
_SEVERITY_RANK = {"p0": 0, "p1": 1, "p2": 2, "": 9}


@dataclass
class DividendEvent:
    id: str = ""
    stock_code: str = ""
    stock_name: str = ""
    industry: str = ""
    severity: str = "p2"
    event_type: str = ""
    title: str = ""
    summary: str = ""
    timeline: list[dict] = field(default_factory=list)
    first_seen_at: float = 0.0
    last_seen_at: float = 0.0
    last_pushed_at: float | None = None
    last_severity: str = ""
    status: str = "active"
    occurrence_count: int = 1
    detail: dict = field(default_factory=dict)
    created_at: float = 0.0
    updated_at: float = 0.0


class DividendEventRepo:
    def __init__(self, db: aiosqlite.Connection):
        self._db = db

    async def upsert(
        self, *, stock_code: str, event_type: str,
        severity: str, stock_name: str, industry: str,
        title: str, summary: str,
        timeline_entry: dict,
        detail: dict | None = None,
        actor: str = "岩神",
    ) -> tuple[str, bool]:
        """同 stock_code+event_type 在 7 天内 merge；返回 (event_id, is_new)。

        - is_new=True：本次新建一条记录
        - is_new=False：merge 到既有记录
        """
        now = time.time()
        cutoff = now - _MERGE_WINDOW_SECONDS

        async with self._db.execute(
            "SELECT id, severity, occurrence_count, timeline_json "
            "FROM dividend_events "
            "WHERE stock_code = ? AND event_type = ? "
            "AND last_seen_at >= ? AND status = 'active' "
            "ORDER BY last_seen_at DESC LIMIT 1",
            (stock_code, event_type, cutoff),
        ) as cur:
            row = await cur.fetchone()

        if row is None:
            event_id = uuid4().hex[:12]
            timeline = [timeline_entry]
            await self._db.execute(
                "INSERT INTO dividend_events ("
                "id, stock_code, stock_name, industry, severity, event_type, "
                "title, summary, timeline_json, first_seen_at, last_seen_at, "
                "last_pushed_at, last_severity, status, occurrence_count, "
                "detail_json, created_at, updated_at"
                ") VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    event_id, stock_code, stock_name, industry, severity, event_type,
                    title, summary,
                    json.dumps(timeline, ensure_ascii=False),
                    now, now,
                    None, "", "active", 1,
                    json.dumps(detail or {}, ensure_ascii=False),
                    now, now,
                ),
            )
            await self._db.commit()
            logger.info(
                "[世界树] {}·新事件 {} {} {} {}",
                actor, event_id, stock_code, event_type, severity,
            )
            return event_id, True

        old_id, old_sev, old_count, old_tl_json = row
        try:
            tl = json.loads(old_tl_json) or []
        except (json.JSONDecodeError, TypeError):
            tl = []

        # 同日幂等：当天多次扫描（rescore/daily 反复点）不重复算命中。
        # 跨天才 append + occurrence++；同日只用最新数据替换 timeline 末项。
        # 对标风神 feed_events 按天聚合的语义。
        new_scan_date = (timeline_entry.get("scan_date") or "").strip()
        last_scan_date = (tl[-1].get("scan_date") or "").strip() if tl else ""
        same_day = bool(new_scan_date and new_scan_date == last_scan_date)
        if same_day:
            tl[-1] = timeline_entry
        else:
            tl.append(timeline_entry)
            if len(tl) > _TIMELINE_MAX_ENTRIES:
                tl = tl[-_TIMELINE_MAX_ENTRIES:]

        # severity 只升不降
        upgraded = (
            severity if _SEVERITY_RANK.get(severity, 9) < _SEVERITY_RANK.get(old_sev, 9)
            else old_sev
        )

        await self._db.execute(
            "UPDATE dividend_events SET "
            "severity = ?, last_seen_at = ?, "
            "occurrence_count = occurrence_count + ?, "
            "timeline_json = ?, summary = ?, title = ?, "
            "stock_name = ?, industry = ?, "
            "detail_json = ?, updated_at = ? "
            "WHERE id = ?",
            (
                upgraded, now,
                0 if same_day else 1,
                json.dumps(tl, ensure_ascii=False),
                summary, title, stock_name, industry,
                json.dumps(detail or {}, ensure_ascii=False),
                now, old_id,
            ),
        )
        await self._db.commit()
        logger.debug(
            "[世界树] {}·{} 事件 {} {}/{} occ={}",
            actor,
            "同日刷新" if same_day else "跨日 merge",
            old_id, stock_code, event_type,
            old_count + (0 if same_day else 1),
        )
        return old_id, False

    async def mark_resolved(
        self, stock_code: str, *,
        exclude_types: set[str] | None = None,
        actor: str = "岩神",
    ) -> int:
        """把该股票所有 active 事件中、event_type 不在 exclude_types 集合里的标 resolved。

        典型用法：本轮该股有 score_change 事件，传 exclude_types={"score_change"}，
        其它历史 active 事件（如 dividend_drop）就被认为"已恢复"标 resolved。
        """
        exclude = exclude_types or set()
        now = time.time()
        async with self._db.execute(
            "SELECT id, event_type FROM dividend_events "
            "WHERE stock_code = ? AND status = 'active'",
            (stock_code,),
        ) as cur:
            rows = await cur.fetchall()
        if not rows:
            return 0
        n = 0
        for eid, etype in rows:
            if etype in exclude:
                continue
            await self._db.execute(
                "UPDATE dividend_events SET status = 'resolved', updated_at = ? "
                "WHERE id = ?",
                (now, eid),
            )
            n += 1
        if n:
            await self._db.commit()
            logger.info(
                "[世界树] {}·resolve {} 条事件 stock={}",
                actor, n, stock_code,
            )
        return n

    async def list(
        self, *,
        severity: str | None = None,
        status: str | None = "active",
        stock_code: str | None = None,
        days: int | None = None,
        limit: int = 200,
    ) -> list[DividendEvent]:
        """筛选事件，按 last_seen_at 降序。

        默认 status='active'；传 status=None 拿全状态。
        days 只看 last_seen_at >= now - days * 86400 的。
        """
        clauses: list[str] = []
        params: list[Any] = []
        if severity is not None:
            clauses.append("severity = ?")
            params.append(severity)
        if status is not None:
            clauses.append("status = ?")
            params.append(status)
        if stock_code is not None:
            clauses.append("stock_code = ?")
            params.append(stock_code)
        if days is not None:
            clauses.append("last_seen_at >= ?")
            params.append(time.time() - days * 86400)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        async with self._db.execute(
            f"SELECT {', '.join(_DIVIDEND_EVENT_COLS)} FROM dividend_events "
            f"{where} ORDER BY last_seen_at DESC LIMIT ?",
            (*params, limit),
        ) as cur:
            rows = await cur.fetchall()
        return [self._row_to_event(r) for r in rows]

    async def count_by_severity(
        self, *, days: int | None = None,
        status: str | None = "active",
    ) -> dict[str, int]:
        """{p0: n, p1: n, p2: n}。"""
        clauses: list[str] = []
        params: list[Any] = []
        if status is not None:
            clauses.append("status = ?")
            params.append(status)
        if days is not None:
            clauses.append("last_seen_at >= ?")
            params.append(time.time() - days * 86400)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        async with self._db.execute(
            f"SELECT severity, COUNT(*) FROM dividend_events {where} "
            "GROUP BY severity",
            tuple(params),
        ) as cur:
            rows = await cur.fetchall()
        result = {"p0": 0, "p1": 0, "p2": 0}
        for sev, n in rows:
            if sev in result:
                result[sev] = int(n)
        return result

    async def get(self, event_id: str) -> DividendEvent | None:
        async with self._db.execute(
            f"SELECT {', '.join(_DIVIDEND_EVENT_COLS)} FROM dividend_events "
            "WHERE id = ?",
            (event_id,),
        ) as cur:
            row = await cur.fetchone()
        return self._row_to_event(row) if row else None

    async def cleanup_before(self, keep_days: int, *, actor: str) -> int:
        """清 last_seen_at 早于 (now - keep_days) 的所有事件。"""
        cutoff = time.time() - keep_days * 86400
        async with self._db.execute(
            "DELETE FROM dividend_events WHERE last_seen_at < ?",
            (cutoff,),
        ) as cur:
            n = cur.rowcount
        await self._db.commit()
        if n:
            logger.info(
                "[世界树] {}·dividend_events 清理 {} 条（超 {} 天）",
                actor, n, keep_days,
            )
        return n

    @staticmethod
    def _row_to_event(row) -> DividendEvent:
        try:
            tl = json.loads(row[8] or "[]")
        except (json.JSONDecodeError, TypeError):
            tl = []
        try:
            detail = json.loads(row[15] or "{}")
        except (json.JSONDecodeError, TypeError):
            detail = {}
        return DividendEvent(
            id=row[0], stock_code=row[1], stock_name=row[2], industry=row[3],
            severity=row[4], event_type=row[5],
            title=row[6], summary=row[7],
            timeline=tl,
            first_seen_at=row[9], last_seen_at=row[10],
            last_pushed_at=row[11], last_severity=row[12],
            status=row[13], occurrence_count=row[14],
            detail=detail,
            created_at=row[16], updated_at=row[17],
        )
