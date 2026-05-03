"""审计 / 归档域 —— 世界树域 7

唯一写入者：时执（生命周期分层 / 审计复盘）
读取者：时执 / 三月面板
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field

import aiosqlite
from loguru import logger


@dataclass
class AuditEntry:
    id: int
    task_id: str | None
    session_id: str
    event_type: str
    actor: str
    payload: dict = field(default_factory=dict)
    created_at: float = 0.0


class AuditRepo:
    def __init__(self, db: aiosqlite.Connection):
        self._db = db

    async def append(
        self, event_type: str, payload: dict, *,
        task_id: str | None = None,
        session_id: str = "",
        actor: str,
    ) -> None:
        await self._db.execute(
            "INSERT INTO audit_revisions "
            "(task_id, session_id, event_type, actor, payload, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                task_id, session_id, event_type, actor,
                json.dumps(payload or {}, ensure_ascii=False),
                time.time(),
            ),
        )
        await self._db.commit()
        logger.info(
            "[世界树] {}·审计记录  event={} task={}",
            actor, event_type, task_id or "-",
        )

    async def list(
        self, *,
        event_type: str | None = None,
        task_id: str | None = None,
        since: float | None = None,
        limit: int = 100,
    ) -> list[AuditEntry]:
        clauses, params = [], []
        if event_type is not None:
            clauses.append("event_type = ?"); params.append(event_type)
        if task_id is not None:
            clauses.append("task_id = ?"); params.append(task_id)
        if since is not None:
            clauses.append("created_at >= ?"); params.append(since)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        sql = (
            "SELECT id, task_id, session_id, event_type, actor, payload, created_at "
            f"FROM audit_revisions {where} ORDER BY created_at DESC LIMIT ?"
        )
        params.append(limit)
        async with self._db.execute(sql, tuple(params)) as cur:
            rows = await cur.fetchall()
        # REL-016：单条 payload JSON 损坏不应阻断整 list 链路（旧版裸 loads 一坏全挂）
        result = []
        for r in rows:
            try:
                payload = json.loads(r[5]) if r[5] else {}
            except (json.JSONDecodeError, TypeError):
                payload = {"_corrupt": True, "_raw_preview": (r[5] or "")[:100]}
            result.append(AuditEntry(
                id=r[0], task_id=r[1], session_id=r[2], event_type=r[3],
                actor=r[4], payload=payload, created_at=r[6],
            ))
        return result
