"""
原石 (Primogem) — Token 用量追踪模块

基于 SQLite 持久化记录每次 LLM 调用的 token 消耗与费用。
费用为估算值，缓存 token 按折扣价计入。
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import aiosqlite
from loguru import logger

# (input_per_tok, output_per_tok, cache_write_per_tok, cache_read_per_tok)
@dataclass
class ModelRate:
    input: float
    output: float
    cache_write: float
    cache_read: float

_RATES: dict[str, ModelRate] = {
    "claude-opus-4":   ModelRate(15e-6,  75e-6,  18.75e-6, 1.5e-6),
    "claude-sonnet-4": ModelRate(3e-6,   15e-6,  3.75e-6,  0.3e-6),
    "claude-haiku":    ModelRate(0.8e-6, 4e-6,   1e-6,     0.08e-6),
    "gpt-4o":          ModelRate(2.5e-6, 10e-6,  2.5e-6,   1.25e-6),
    "gpt-4o-mini":     ModelRate(0.15e-6, 0.6e-6, 0.15e-6, 0.075e-6),
    "gpt-4":           ModelRate(30e-6,  60e-6,   30e-6,   15e-6),
    "mimo":            ModelRate(1e-6,   1e-6,    1e-6,    0.5e-6),
}
_DEFAULT_RATE = ModelRate(3e-6, 15e-6, 3.75e-6, 0.3e-6)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS token_usage (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp REAL NOT NULL,
    session_id TEXT NOT NULL DEFAULT '',
    component TEXT NOT NULL,
    model_name TEXT NOT NULL,
    input_tokens INTEGER NOT NULL,
    output_tokens INTEGER NOT NULL,
    cache_creation_tokens INTEGER NOT NULL DEFAULT 0,
    cache_read_tokens INTEGER NOT NULL DEFAULT 0,
    cost_usd REAL NOT NULL,
    purpose TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_token_session ON token_usage(session_id);
CREATE INDEX IF NOT EXISTS idx_token_ts ON token_usage(timestamp);
CREATE INDEX IF NOT EXISTS idx_token_component ON token_usage(component);
CREATE INDEX IF NOT EXISTS idx_token_purpose ON token_usage(purpose);
"""

_MIGRATION_COLUMNS = [
    ("cache_creation_tokens", "INTEGER NOT NULL DEFAULT 0"),
    ("cache_read_tokens", "INTEGER NOT NULL DEFAULT 0"),
    ("purpose", "TEXT NOT NULL DEFAULT ''"),
]


class Primogem:
    def __init__(self, db_path: Path):
        self._db_path = db_path
        self._db: aiosqlite.Connection | None = None

    async def initialize(self) -> None:
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._db = await aiosqlite.connect(str(self._db_path))
        await self._db.executescript(_SCHEMA)
        await self._migrate()
        await self._db.commit()
        logger.info("[原石] 数据库就绪 {}", self._db_path)

    async def _migrate(self) -> None:
        if not self._db:
            return
        async with self._db.execute("PRAGMA table_info(token_usage)") as cur:
            existing = {row[1] async for row in cur}
        for col_name, col_def in _MIGRATION_COLUMNS:
            if col_name not in existing:
                await self._db.execute(
                    f"ALTER TABLE token_usage ADD COLUMN {col_name} {col_def}"
                )
                logger.info("[原石] 迁移: 添加列 {}", col_name)

    async def close(self) -> None:
        if self._db:
            await self._db.close()
            self._db = None

    @staticmethod
    def _match_rate(model_name: str) -> ModelRate:
        name = model_name.lower()
        for prefix, rate in _RATES.items():
            if prefix in name:
                return rate
        return _DEFAULT_RATE

    @staticmethod
    def compute_cost(
        model_name: str,
        input_tokens: int,
        output_tokens: int,
        cache_creation_tokens: int = 0,
        cache_read_tokens: int = 0,
    ) -> float:
        rate = Primogem._match_rate(model_name)
        base_input = input_tokens - cache_creation_tokens - cache_read_tokens
        if base_input < 0:
            base_input = 0
        return (
            base_input * rate.input
            + cache_creation_tokens * rate.cache_write
            + cache_read_tokens * rate.cache_read
            + output_tokens * rate.output
        )

    async def record(
        self,
        session_id: str,
        component: str,
        model_name: str,
        input_tokens: int,
        output_tokens: int,
        cost_usd: float,
        cache_creation_tokens: int = 0,
        cache_read_tokens: int = 0,
        purpose: str = "",
    ) -> None:
        if not self._db:
            return
        await self._db.execute(
            "INSERT INTO token_usage "
            "(timestamp, session_id, component, model_name, "
            "input_tokens, output_tokens, cache_creation_tokens, cache_read_tokens, "
            "cost_usd, purpose) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                time.time(), session_id, component, model_name,
                input_tokens, output_tokens,
                cache_creation_tokens, cache_read_tokens, cost_usd, purpose,
            ),
        )
        await self._db.commit()

    async def get_session_stats(self, session_id: str) -> dict[str, Any]:
        return await self._aggregate("WHERE session_id = ?", (session_id,))

    async def get_global_stats(self) -> dict[str, Any]:
        return await self._aggregate("", ())

    async def _aggregate(
        self, where: str, params: tuple
    ) -> dict[str, Any]:
        if not self._db:
            return self._empty_stats()

        sql = (
            "SELECT COALESCE(SUM(input_tokens),0), "
            "COALESCE(SUM(output_tokens),0), "
            "COALESCE(SUM(cache_creation_tokens),0), "
            "COALESCE(SUM(cache_read_tokens),0), "
            "COALESCE(SUM(cost_usd),0), "
            "COUNT(*) "
            f"FROM token_usage {where}"
        )
        async with self._db.execute(sql, params) as cur:
            row = await cur.fetchone()

        total_in, total_out, total_cw, total_cr, total_cost, count = row or (0, 0, 0, 0, 0.0, 0)

        by_component: dict[str, dict] = {}
        sql_comp = (
            "SELECT component, "
            "SUM(input_tokens), SUM(output_tokens), "
            "SUM(cache_creation_tokens), SUM(cache_read_tokens), "
            "SUM(cost_usd), COUNT(*) "
            f"FROM token_usage {where} "
            "GROUP BY component ORDER BY SUM(cost_usd) DESC"
        )
        async with self._db.execute(sql_comp, params) as cur:
            async for r in cur:
                by_component[r[0]] = {
                    "input_tokens": r[1],
                    "output_tokens": r[2],
                    "cache_creation_tokens": r[3],
                    "cache_read_tokens": r[4],
                    "cost_usd": r[5],
                    "count": r[6],
                }

        return {
            "total_input_tokens": total_in,
            "total_output_tokens": total_out,
            "total_cache_creation_tokens": total_cw,
            "total_cache_read_tokens": total_cr,
            "total_cost_usd": total_cost,
            "count": count,
            "by_component": by_component,
        }

    async def get_purpose_stats(self) -> dict[str, dict[str, Any]]:
        if not self._db:
            return {}
        sql = (
            "SELECT purpose, "
            "SUM(input_tokens), SUM(output_tokens), "
            "SUM(cache_creation_tokens), SUM(cache_read_tokens), "
            "SUM(cost_usd), COUNT(*) "
            "FROM token_usage "
            "GROUP BY purpose ORDER BY SUM(cost_usd) DESC"
        )
        result: dict[str, dict[str, Any]] = {}
        async with self._db.execute(sql) as cur:
            async for r in cur:
                result[r[0] or "(未标记)"] = {
                    "input_tokens": r[1],
                    "output_tokens": r[2],
                    "cache_creation_tokens": r[3],
                    "cache_read_tokens": r[4],
                    "cost_usd": r[5],
                    "count": r[6],
                }
        return result

    async def get_detail_stats(self) -> list[dict[str, Any]]:
        if not self._db:
            return []
        sql = (
            "SELECT component, purpose, "
            "SUM(input_tokens), SUM(output_tokens), "
            "SUM(cache_creation_tokens), SUM(cache_read_tokens), "
            "SUM(cost_usd), COUNT(*) "
            "FROM token_usage "
            "GROUP BY component, purpose ORDER BY SUM(cost_usd) DESC"
        )
        result: list[dict[str, Any]] = []
        async with self._db.execute(sql) as cur:
            async for r in cur:
                result.append({
                    "component": r[0],
                    "purpose": r[1] or "",
                    "input_tokens": r[2],
                    "output_tokens": r[3],
                    "cache_creation_tokens": r[4],
                    "cache_read_tokens": r[5],
                    "cost_usd": r[6],
                    "count": r[7],
                })
        return result

    async def get_distribution_stats(self, by: str = "hour") -> list[dict[str, Any]]:
        if not self._db:
            return []
        if by == "weekday":
            group_expr = "CAST(strftime('%w', timestamp, 'unixepoch', 'localtime') AS INTEGER)"
        else:
            group_expr = "CAST(strftime('%H', timestamp, 'unixepoch', 'localtime') AS INTEGER)"
        sql = (
            f"SELECT {group_expr} as period, "
            "SUM(input_tokens), SUM(output_tokens), "
            "SUM(cache_creation_tokens), SUM(cache_read_tokens), "
            "SUM(cost_usd), COUNT(*) "
            "FROM token_usage "
            f"GROUP BY {group_expr} ORDER BY period"
        )
        async with self._db.execute(sql) as cur:
            rows = await cur.fetchall()
        return [
            {
                "period": row[0],
                "input_tokens": row[1],
                "output_tokens": row[2],
                "cache_creation_tokens": row[3],
                "cache_read_tokens": row[4],
                "cost_usd": row[5],
                "count": row[6],
            }
            for row in rows
        ]

    async def get_timeline_stats(
        self, period: str = "day", count: int = 7,
    ) -> list[dict[str, Any]]:
        if not self._db:
            return []

        if period == "week":
            cutoff = time.time() - count * 7 * 86400
            group_expr = "strftime('%Y-W%W', timestamp, 'unixepoch', 'localtime')"
        elif period == "month":
            cutoff = time.time() - count * 30 * 86400
            group_expr = "strftime('%Y-%m', timestamp, 'unixepoch', 'localtime')"
        else:
            cutoff = time.time() - count * 86400
            group_expr = "date(timestamp, 'unixepoch', 'localtime')"

        sql = (
            f"SELECT {group_expr} as period, "
            "SUM(input_tokens), SUM(output_tokens), "
            "SUM(cache_creation_tokens), SUM(cache_read_tokens), "
            "SUM(cost_usd), COUNT(*) "
            "FROM token_usage WHERE timestamp >= ? "
            "GROUP BY period ORDER BY period"
        )
        async with self._db.execute(sql, (cutoff,)) as cur:
            rows = await cur.fetchall()
        return [
            {
                "period": row[0],
                "input_tokens": row[1],
                "output_tokens": row[2],
                "cache_creation_tokens": row[3],
                "cache_read_tokens": row[4],
                "cost_usd": row[5],
                "count": row[6],
            }
            for row in rows
        ]

    @staticmethod
    def _empty_stats() -> dict[str, Any]:
        return {
            "total_input_tokens": 0,
            "total_output_tokens": 0,
            "total_cache_creation_tokens": 0,
            "total_cache_read_tokens": 0,
            "total_cost_usd": 0.0,
            "count": 0,
            "by_component": {},
        }
