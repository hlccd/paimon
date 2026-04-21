"""Token 记录域 —— 世界树域 6

唯一写入者 / 读取者：原石（业务服务层，持有费率表 + 聚合逻辑）
世界树只负责字节落盘 + 基本的 GROUP BY 聚合原语，原石二次加工。
"""
from __future__ import annotations

from dataclasses import dataclass

import aiosqlite
from loguru import logger


@dataclass
class TokenRow:
    id: int
    timestamp: float
    session_id: str
    component: str
    model_name: str
    input_tokens: int
    output_tokens: int
    cache_creation_tokens: int
    cache_read_tokens: int
    cost_usd: float
    purpose: str


# 支持的 GROUP BY 列 / 时间维度
_GROUP_EXPR = {
    "component": "component",
    "purpose": "purpose",
    "session_id": "session_id",
    "model_name": "model_name",
    "hour": "CAST(strftime('%H', timestamp, 'unixepoch', 'localtime') AS INTEGER)",
    "weekday": "CAST(strftime('%w', timestamp, 'unixepoch', 'localtime') AS INTEGER)",
    "day": "date(timestamp, 'unixepoch', 'localtime')",
    "week": "strftime('%Y-W%W', timestamp, 'unixepoch', 'localtime')",
    "month": "strftime('%Y-%m', timestamp, 'unixepoch', 'localtime')",
}


class TokenRepo:
    def __init__(self, db: aiosqlite.Connection):
        self._db = db

    async def write(
        self,
        session_id: str,
        component: str,
        model_name: str,
        input_tokens: int,
        output_tokens: int,
        cost_usd: float,
        *,
        cache_creation_tokens: int = 0,
        cache_read_tokens: int = 0,
        purpose: str = "",
        timestamp: float | None = None,
        actor: str,
    ) -> None:
        import time as _t
        ts = timestamp if timestamp is not None else _t.time()
        await self._db.execute(
            "INSERT INTO token_usage "
            "(timestamp, session_id, component, model_name, "
            " input_tokens, output_tokens, cache_creation_tokens, cache_read_tokens, "
            " cost_usd, purpose) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                ts, session_id, component, model_name,
                input_tokens, output_tokens,
                cache_creation_tokens, cache_read_tokens,
                cost_usd, purpose,
            ),
        )
        await self._db.commit()
        cost_str = f"${cost_usd:.4f}" if cost_usd < 0.01 else f"${cost_usd:.2f}"
        logger.info(
            "[世界树] {}·写入 Token 记录  session={}, component={}, 消耗={}",
            actor, (session_id[:8] if session_id else "-"), component, cost_str,
        )

    async def rows(
        self, *,
        session_id: str | None = None,
        component: str | None = None,
        purpose: str | None = None,
        since: float | None = None,
        until: float | None = None,
        limit: int = 10000,
    ) -> list[TokenRow]:
        clauses, params = [], []
        if session_id is not None:
            clauses.append("session_id = ?"); params.append(session_id)
        if component is not None:
            clauses.append("component = ?"); params.append(component)
        if purpose is not None:
            clauses.append("purpose = ?"); params.append(purpose)
        if since is not None:
            clauses.append("timestamp >= ?"); params.append(since)
        if until is not None:
            clauses.append("timestamp < ?"); params.append(until)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        sql = (
            "SELECT id, timestamp, session_id, component, model_name, "
            "input_tokens, output_tokens, cache_creation_tokens, cache_read_tokens, "
            "cost_usd, purpose "
            f"FROM token_usage {where} ORDER BY timestamp LIMIT ?"
        )
        params.append(limit)
        async with self._db.execute(sql, tuple(params)) as cur:
            rows = await cur.fetchall()
        return [
            TokenRow(
                id=r[0], timestamp=r[1], session_id=r[2], component=r[3],
                model_name=r[4], input_tokens=r[5], output_tokens=r[6],
                cache_creation_tokens=r[7], cache_read_tokens=r[8],
                cost_usd=r[9], purpose=r[10],
            )
            for r in rows
        ]

    async def aggregate(
        self, *,
        group_by: list[str],
        session_id: str | None = None,
        since: float | None = None,
    ) -> list[dict]:
        """GROUP BY 聚合。group_by ⊂ {component, purpose, session_id, model_name,
        hour, weekday, day, week, month}。返回每行包含 group 列 + sum_* + count。
        """
        if not group_by:
            raise ValueError("group_by 不能为空")
        exprs = []
        for g in group_by:
            if g not in _GROUP_EXPR:
                raise ValueError(f"不支持的 group_by: {g}")
            exprs.append(f"{_GROUP_EXPR[g]} AS {g}")

        clauses, params = [], []
        if session_id is not None:
            clauses.append("session_id = ?"); params.append(session_id)
        if since is not None:
            clauses.append("timestamp >= ?"); params.append(since)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        group_cols = ", ".join(group_by)

        sql = (
            f"SELECT {', '.join(exprs)}, "
            "SUM(input_tokens) AS sum_input_tokens, "
            "SUM(output_tokens) AS sum_output_tokens, "
            "SUM(cache_creation_tokens) AS sum_cache_creation_tokens, "
            "SUM(cache_read_tokens) AS sum_cache_read_tokens, "
            "SUM(cost_usd) AS sum_cost_usd, "
            "COUNT(*) AS count "
            f"FROM token_usage {where} GROUP BY {group_cols} ORDER BY sum_cost_usd DESC"
        )
        async with self._db.execute(sql, tuple(params)) as cur:
            cols = [d[0] for d in cur.description]
            return [dict(zip(cols, row)) async for row in cur]
