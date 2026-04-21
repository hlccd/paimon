"""理财数据域 —— 世界树域 8

唯一写入者 / 读取者：岩神（股价 / 分红 / 资产业务）
首版只建表 + 最小 API；完整业务字段等岩神模块实现时细化。
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field

import aiosqlite
from loguru import logger


@dataclass
class DividendRecord:
    id: int
    symbol: str
    exchange: str
    name: str
    record_date: str                          # 'YYYY-MM-DD'
    amount: float
    yield_pct: float
    payload: dict = field(default_factory=dict)
    created_at: float = 0.0


class DividendRepo:
    def __init__(self, db: aiosqlite.Connection):
        self._db = db

    async def write(
        self,
        symbol: str,
        record_date: str,
        amount: float,
        *,
        exchange: str = "",
        name: str = "",
        yield_pct: float = 0.0,
        payload: dict | None = None,
        actor: str,
    ) -> None:
        await self._db.execute(
            "INSERT INTO dividend_stocks "
            "(symbol, exchange, name, record_date, amount, yield_pct, payload, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                symbol, exchange, name, record_date, amount, yield_pct,
                json.dumps(payload or {}, ensure_ascii=False),
                time.time(),
            ),
        )
        await self._db.commit()
        logger.info(
            "[世界树] {}·分红记录写入  {} ({})",
            actor, symbol, record_date,
        )

    async def list(
        self, *,
        symbol: str | None = None,
        since: str | None = None,
        limit: int = 100,
    ) -> list[DividendRecord]:
        clauses, params = [], []
        if symbol is not None:
            clauses.append("symbol = ?"); params.append(symbol)
        if since is not None:
            clauses.append("record_date >= ?"); params.append(since)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        sql = (
            "SELECT id, symbol, exchange, name, record_date, amount, yield_pct, "
            "payload, created_at "
            f"FROM dividend_stocks {where} ORDER BY record_date DESC LIMIT ?"
        )
        params.append(limit)
        async with self._db.execute(sql, tuple(params)) as cur:
            rows = await cur.fetchall()
        return [
            DividendRecord(
                id=r[0], symbol=r[1], exchange=r[2], name=r[3],
                record_date=r[4], amount=r[5], yield_pct=r[6],
                payload=json.loads(r[7]) if r[7] else {},
                created_at=r[8],
            )
            for r in rows
        ]
