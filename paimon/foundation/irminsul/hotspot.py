"""风神 · 每日热点数据域 11.7。

每天 cron 11/17 两个 slot 各跑一次，按 (capture_date, capture_slot) 自然累积历史。
失败的源走 sources_fail 记录但仍 upsert（前端能看见状态）。
"""
from __future__ import annotations

import time
from typing import Any

import aiosqlite
from loguru import logger


class HotspotRepo:
    """每日热点 CRUD。"""

    def __init__(self, db: aiosqlite.Connection) -> None:
        self._db = db

    async def upsert(
        self,
        *,
        capture_date: str,
        capture_slot: str,
        markdown: str,
        sources_ok: str,
        sources_fail: str,
        items_total: int,
        duration_s: int,
        actor: str = "风神",
    ) -> None:
        """每天只保留 1 条最新：先删同 date 所有记录，再 INSERT。

        capture_slot 仅作信息字段记录"最后一次什么时段触发的"（morning/afternoon/manual），
        不参与唯一约束。下午跑覆盖中午跑，手动跑也覆盖。
        """
        await self._db.execute(
            "DELETE FROM daily_hotspot WHERE capture_date = ?",
            (capture_date,),
        )
        await self._db.execute(
            "INSERT INTO daily_hotspot "
            "(captured_at, capture_date, capture_slot, markdown, "
            " sources_ok, sources_fail, items_total, duration_s) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                int(time.time()), capture_date, capture_slot, markdown,
                sources_ok, sources_fail, items_total, duration_s,
            ),
        )
        await self._db.commit()
        logger.info(
            "[世界树] {}·每日热点 upsert {} (slot={}) ok={} fail={} items={} duration={}s",
            actor, capture_date, capture_slot,
            sources_ok or "-", sources_fail or "-", items_total, duration_s,
        )

    async def get_latest(self) -> dict[str, Any] | None:
        """拿最新一份（按 captured_at 倒序，跨 date+slot 第一条）。"""
        async with self._db.execute(
            "SELECT id, captured_at, capture_date, capture_slot, markdown, "
            "       sources_ok, sources_fail, items_total, duration_s "
            "FROM daily_hotspot ORDER BY captured_at DESC LIMIT 1"
        ) as cur:
            row = await cur.fetchone()
        return self._row_to_dict(row) if row else None

    async def get_by_slot(self, capture_date: str, capture_slot: str) -> dict[str, Any] | None:
        """拿指定 (date, slot) 的记录。"""
        async with self._db.execute(
            "SELECT id, captured_at, capture_date, capture_slot, markdown, "
            "       sources_ok, sources_fail, items_total, duration_s "
            "FROM daily_hotspot WHERE capture_date=? AND capture_slot=?",
            (capture_date, capture_slot),
        ) as cur:
            row = await cur.fetchone()
        return self._row_to_dict(row) if row else None

    async def list_recent(self, days: int = 7) -> list[dict[str, Any]]:
        """近 N 天的所有 slot（最多 N×2 条），按 captured_at 倒序。"""
        since_ts = int(time.time()) - days * 86400
        async with self._db.execute(
            "SELECT id, captured_at, capture_date, capture_slot, markdown, "
            "       sources_ok, sources_fail, items_total, duration_s "
            "FROM daily_hotspot WHERE captured_at >= ? "
            "ORDER BY captured_at DESC",
            (since_ts,),
        ) as cur:
            rows = await cur.fetchall()
        return [self._row_to_dict(r) for r in rows]

    @staticmethod
    def _row_to_dict(row: tuple) -> dict[str, Any]:
        return {
            "id": row[0],
            "captured_at": row[1],
            "capture_date": row[2],
            "capture_slot": row[3],
            "markdown": row[4],
            "sources_ok": row[5],
            "sources_fail": row[6],
            "items_total": row[7],
            "duration_s": row[8],
        }

    # ─── 近期回顾（整张表只保留 1 条最新；每次跑前清表再 INSERT）───
    async def weekly_upsert(
        self,
        *,
        capture_date: str,
        range_start: str,
        range_end: str,
        markdown: str,
        daily_count: int,
        duration_s: int,
        actor: str = "风神",
    ) -> None:
        """整张表只保留 1 条：先 DELETE 全表再 INSERT 新一条。"""
        await self._db.execute("DELETE FROM weekly_hotspot")
        await self._db.execute(
            "INSERT INTO weekly_hotspot "
            "(week_start, markdown, daily_count, duration_s, updated_at, range_start, range_end) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (capture_date, markdown, daily_count, duration_s,
             int(time.time()), range_start, range_end),
        )
        await self._db.commit()
        logger.info(
            "[世界树] {}·近期回顾 upsert 范围 {}~{} daily_count={} duration={}s",
            actor, range_start, range_end, daily_count, duration_s,
        )

    async def weekly_get_latest(self) -> dict[str, Any] | None:
        async with self._db.execute(
            "SELECT week_start, markdown, daily_count, duration_s, updated_at, "
            "       range_start, range_end "
            "FROM weekly_hotspot LIMIT 1"
        ) as cur:
            row = await cur.fetchone()
        return self._row_to_weekly(row) if row else None

    @staticmethod
    def _row_to_weekly(row: tuple) -> dict[str, Any]:
        return {
            "capture_date": row[0],     # 对外暴露语义化字段名
            "markdown": row[1],
            "daily_count": row[2],
            "duration_s": row[3],
            "updated_at": row[4],
            "range_start": row[5] or "",
            "range_end": row[6] or "",
        }
