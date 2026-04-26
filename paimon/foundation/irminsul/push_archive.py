"""世界树域 13 · 推送归档（替代主动聊天推送）

各神原本经 march.ring_event 推到聊天会话的内容（风神舆情日报、岩神红利股变化等），
改为静默归档到本表，由 WebUI 导航栏全局红点 + 抽屉消费。聊天会话彻底纯净。

docs/foundation/march.md §推送归档
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4

import aiosqlite
from loguru import logger


@dataclass
class PushArchiveRecord:
    id: str = ""
    source: str = ""             # "风神·舆情日报" / "风神·舆情预警" / "岩神·红利股变化"
    actor: str = ""              # "风神" / "岩神" / "三月" 用于按神分组
    channel_name: str = "webui"
    chat_id: str = ""
    message_md: str = ""
    level: str = "silent"        # 'silent' | 'loud'，预留
    extra: dict[str, Any] = field(default_factory=dict)
    created_at: float = 0.0
    read_at: float | None = None  # None = 未读


class PushArchiveRepo:
    """推送归档仓储。所有时间戳 unix 秒。"""

    def __init__(self, db: aiosqlite.Connection):
        self._db = db

    # ---------- 写入 ----------

    async def create(
        self,
        *,
        source: str,
        actor: str,
        message_md: str,
        channel_name: str = "webui",
        chat_id: str = "",
        level: str = "silent",
        extra: dict[str, Any] | None = None,
    ) -> str:
        """落一条归档；返回 record id。"""
        rec_id = uuid4().hex[:12]
        now = time.time()
        await self._db.execute(
            "INSERT INTO push_archive "
            "(id, source, actor, channel_name, chat_id, message_md, level, "
            "extra_json, created_at, read_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,NULL)",
            (
                rec_id, source, actor, channel_name, chat_id,
                message_md, level,
                json.dumps(extra or {}, ensure_ascii=False),
                now,
            ),
        )
        await self._db.commit()
        logger.info(
            "[世界树·推送归档] 新增 {} actor={} source={} level={} len={}",
            rec_id, actor, source, level, len(message_md),
        )
        return rec_id

    # ---------- 查询 ----------

    async def get(self, rec_id: str) -> PushArchiveRecord | None:
        async with self._db.execute(
            "SELECT id, source, actor, channel_name, chat_id, message_md, "
            "level, extra_json, created_at, read_at "
            "FROM push_archive WHERE id = ?", (rec_id,),
        ) as cur:
            row = await cur.fetchone()
        return self._row_to_record(row) if row else None

    async def list(
        self,
        *,
        actor: str | None = None,
        only_unread: bool = False,
        since: float | None = None,
        until: float | None = None,
        limit: int = 50,
    ) -> list[PushArchiveRecord]:
        clauses, params = [], []
        if actor is not None:
            clauses.append("actor = ?"); params.append(actor)
        if only_unread:
            clauses.append("read_at IS NULL")
        if since is not None:
            clauses.append("created_at >= ?"); params.append(since)
        if until is not None:
            clauses.append("created_at < ?"); params.append(until)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        sql = (
            "SELECT id, source, actor, channel_name, chat_id, message_md, "
            "level, extra_json, created_at, read_at "
            f"FROM push_archive {where} ORDER BY created_at DESC LIMIT ?"
        )
        params.append(limit)
        async with self._db.execute(sql, tuple(params)) as cur:
            rows = await cur.fetchall()
        return [self._row_to_record(r) for r in rows]

    async def count_unread(self, *, actor: str | None = None) -> int:
        clauses = ["read_at IS NULL"]
        params: list[Any] = []
        if actor is not None:
            clauses.append("actor = ?"); params.append(actor)
        where = " AND ".join(clauses)
        async with self._db.execute(
            f"SELECT COUNT(*) FROM push_archive WHERE {where}", tuple(params),
        ) as cur:
            row = await cur.fetchone()
        return int(row[0]) if row else 0

    async def count_unread_grouped(self) -> dict[str, int]:
        """按 actor 分组的未读数。返回 {actor: count}。"""
        async with self._db.execute(
            "SELECT actor, COUNT(*) FROM push_archive "
            "WHERE read_at IS NULL GROUP BY actor",
        ) as cur:
            rows = await cur.fetchall()
        return {actor: int(n) for actor, n in rows}

    # ---------- 标记已读 ----------

    async def mark_read(self, rec_id: str) -> bool:
        now = time.time()
        async with self._db.execute(
            "UPDATE push_archive SET read_at = ? "
            "WHERE id = ? AND read_at IS NULL",
            (now, rec_id),
        ) as cur:
            ok = cur.rowcount > 0
        await self._db.commit()
        if ok:
            logger.debug("[世界树·推送归档] 标记已读 {}", rec_id)
        return ok

    async def mark_read_all(self, *, actor: str | None = None) -> int:
        """批量标记已读；返回实际更新条数。"""
        now = time.time()
        if actor is not None:
            async with self._db.execute(
                "UPDATE push_archive SET read_at = ? "
                "WHERE actor = ? AND read_at IS NULL",
                (now, actor),
            ) as cur:
                changed = cur.rowcount
        else:
            async with self._db.execute(
                "UPDATE push_archive SET read_at = ? WHERE read_at IS NULL",
                (now,),
            ) as cur:
                changed = cur.rowcount
        await self._db.commit()
        if changed > 0:
            logger.info(
                "[世界树·推送归档] 批量已读 actor={} count={}",
                actor or "ALL", changed,
            )
        return changed

    # ---------- 清理 ----------

    async def sweep_old(self, *, retention_seconds: float, actor: str = "三月") -> int:
        """清理 created_at 早于 (now - retention) 的归档（无论是否已读）。"""
        cutoff = time.time() - retention_seconds
        async with self._db.execute(
            "DELETE FROM push_archive WHERE created_at < ?", (cutoff,),
        ) as cur:
            n = cur.rowcount
        await self._db.commit()
        if n > 0:
            logger.info(
                "[世界树·推送归档] {}·清理 {} 条 cutoff={}",
                actor, n, cutoff,
            )
        return n

    # ---------- 内部 ----------

    @staticmethod
    def _row_to_record(row) -> PushArchiveRecord:
        try:
            extra = json.loads(row[7] or "{}")
            if not isinstance(extra, dict):
                extra = {}
        except (json.JSONDecodeError, TypeError):
            extra = {}
        return PushArchiveRecord(
            id=row[0],
            source=row[1],
            actor=row[2],
            channel_name=row[3],
            chat_id=row[4],
            message_md=row[5],
            level=row[6],
            extra=extra,
            created_at=float(row[8]),
            read_at=float(row[9]) if row[9] is not None else None,
        )
