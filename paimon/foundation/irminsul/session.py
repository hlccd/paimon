"""聊天会话域 —— 世界树域 9

唯一写入者 / 读取者：派蒙
额外读取者：时执（归档时读旧会话）

设计要点：
- 整个消息链作为 messages_json TEXT 存在一列里
- session_memory（压缩块 list[str]）也存 JSON 数组
- channel_key 表达"此会话当前绑定哪个 channel"；同一 channel 活跃会话集中最多一条
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field

import aiosqlite
from loguru import logger


@dataclass
class SessionMeta:
    """轻量版（list 查询返回，不含消息链 / 记忆块）"""
    id: str
    name: str
    channel_key: str
    response_status: str
    last_context_tokens: int
    last_context_ratio: float
    last_compressed_at: float
    compressed_rounds: int
    created_at: float
    updated_at: float
    archived_at: float | None


@dataclass
class SessionRecord:
    """完整版（和旧 Session 字段保持一致，外加 channel_key/archived_at）"""
    id: str
    name: str
    channel_key: str = ""
    messages: list[dict] = field(default_factory=list)
    session_memory: list[str] = field(default_factory=list)
    last_context_tokens: int = 0
    last_context_ratio: float = 0.0
    last_compressed_at: float = 0.0
    compressed_rounds: int = 0
    response_status: str = "idle"
    created_at: float = 0.0
    updated_at: float = 0.0
    archived_at: float | None = None
    # 时执压缩熔断
    compression_failures: int = 0
    auto_compact_disabled: bool = False


class SessionRepo:
    def __init__(self, db: aiosqlite.Connection):
        self._db = db

    async def upsert(self, rec: SessionRecord, *, actor: str) -> None:
        """完整写入（INSERT or REPLACE）。派蒙保存会话时一次性整条入库。"""
        now = time.time()
        created_at = rec.created_at if rec.created_at > 0 else now
        updated_at = now
        await self._db.execute(
            "INSERT INTO session_records "
            "(id, name, channel_key, messages_json, session_memory_json, "
            " last_context_tokens, last_context_ratio, last_compressed_at, compressed_rounds, "
            " response_status, created_at, updated_at, archived_at, "
            " compression_failures, auto_compact_disabled) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(id) DO UPDATE SET "
            "  name = excluded.name, "
            "  channel_key = excluded.channel_key, "
            "  messages_json = excluded.messages_json, "
            "  session_memory_json = excluded.session_memory_json, "
            "  last_context_tokens = excluded.last_context_tokens, "
            "  last_context_ratio = excluded.last_context_ratio, "
            "  last_compressed_at = excluded.last_compressed_at, "
            "  compressed_rounds = excluded.compressed_rounds, "
            "  response_status = excluded.response_status, "
            "  updated_at = excluded.updated_at, "
            "  archived_at = excluded.archived_at, "
            "  compression_failures = excluded.compression_failures, "
            "  auto_compact_disabled = excluded.auto_compact_disabled",
            (
                rec.id, rec.name, rec.channel_key,
                json.dumps(rec.messages, ensure_ascii=False),
                json.dumps(rec.session_memory, ensure_ascii=False),
                rec.last_context_tokens, rec.last_context_ratio,
                rec.last_compressed_at, rec.compressed_rounds,
                rec.response_status,
                created_at, updated_at, rec.archived_at,
                rec.compression_failures,
                1 if rec.auto_compact_disabled else 0,
            ),
        )
        await self._db.commit()
        logger.info(
            "[世界树] {}·会话保存  {} ({} msgs)",
            actor, rec.id[:8], len(rec.messages),
        )

    async def load(self, session_id: str) -> SessionRecord | None:
        async with self._db.execute(
            "SELECT id, name, channel_key, messages_json, session_memory_json, "
            "last_context_tokens, last_context_ratio, last_compressed_at, compressed_rounds, "
            "response_status, created_at, updated_at, archived_at, "
            "compression_failures, auto_compact_disabled "
            "FROM session_records WHERE id = ?",
            (session_id,),
        ) as cur:
            row = await cur.fetchone()
        if not row:
            return None
        # REL-016：messages/session_memory JSON 损坏不该让 get 直接 raise；
        # 旧版裸 loads 让单坏会话阻断 SessionManager 加载
        try:
            messages = json.loads(row[3]) if row[3] else []
        except (json.JSONDecodeError, TypeError):
            messages = []
        try:
            session_memory = json.loads(row[4]) if row[4] else []
        except (json.JSONDecodeError, TypeError):
            session_memory = []
        return SessionRecord(
            id=row[0], name=row[1], channel_key=row[2],
            messages=messages,
            session_memory=session_memory,
            last_context_tokens=row[5], last_context_ratio=row[6],
            last_compressed_at=row[7], compressed_rounds=row[8],
            response_status=row[9],
            created_at=row[10], updated_at=row[11], archived_at=row[12],
            compression_failures=row[13] or 0,
            auto_compact_disabled=bool(row[14]),
        )

    async def list(
        self, *,
        channel_key: str | None = None,
        archived: bool = False,
        limit: int = 50,
    ) -> list[SessionMeta]:
        clauses, params = [], []
        if channel_key is not None:
            clauses.append("channel_key = ?"); params.append(channel_key)
        if archived:
            clauses.append("archived_at IS NOT NULL")
        else:
            clauses.append("archived_at IS NULL")
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        sql = (
            "SELECT id, name, channel_key, response_status, "
            "last_context_tokens, last_context_ratio, "
            "last_compressed_at, compressed_rounds, "
            "created_at, updated_at, archived_at "
            f"FROM session_records {where} ORDER BY updated_at DESC LIMIT ?"
        )
        params.append(limit)
        async with self._db.execute(sql, tuple(params)) as cur:
            rows = await cur.fetchall()
        return [
            SessionMeta(
                id=r[0], name=r[1], channel_key=r[2],
                response_status=r[3],
                last_context_tokens=r[4], last_context_ratio=r[5],
                last_compressed_at=r[6], compressed_rounds=r[7],
                created_at=r[8], updated_at=r[9], archived_at=r[10],
            )
            for r in rows
        ]

    async def list_all_full(self) -> list[SessionRecord]:
        """启动时一次性加载所有活跃会话（含消息链）。供 SessionManager 用。"""
        async with self._db.execute(
            "SELECT id, name, channel_key, messages_json, session_memory_json, "
            "last_context_tokens, last_context_ratio, last_compressed_at, compressed_rounds, "
            "response_status, created_at, updated_at, archived_at, "
            "compression_failures, auto_compact_disabled "
            "FROM session_records WHERE archived_at IS NULL"
        ) as cur:
            rows = await cur.fetchall()
        result = []
        for row in rows:
            try:
                result.append(SessionRecord(
                    id=row[0], name=row[1], channel_key=row[2],
                    messages=json.loads(row[3]) if row[3] else [],
                    session_memory=json.loads(row[4]) if row[4] else [],
                    last_context_tokens=row[5], last_context_ratio=row[6],
                    last_compressed_at=row[7], compressed_rounds=row[8],
                    response_status=row[9],
                    created_at=row[10], updated_at=row[11], archived_at=row[12],
                    compression_failures=row[13] or 0,
                    auto_compact_disabled=bool(row[14]),
                ))
            except Exception as e:
                # 审计 REL-008：单条损坏不阻塞其他会话加载
                logger.warning("[世界树] 会话加载  跳过损坏会话 {}: {}", row[0], e)
        return result

    async def delete(self, session_id: str, *, actor: str) -> bool:
        async with self._db.execute(
            "DELETE FROM session_records WHERE id = ?", (session_id,),
        ) as cur:
            deleted = cur.rowcount > 0
        await self._db.commit()
        if deleted:
            logger.info("[世界树] {}·会话删除  {}", actor, session_id[:8])
        return deleted

    async def archive(self, session_id: str, *, actor: str) -> bool:
        now = time.time()
        async with self._db.execute(
            "UPDATE session_records SET archived_at = ?, updated_at = ? "
            "WHERE id = ? AND archived_at IS NULL",
            (now, now, session_id),
        ) as cur:
            updated = cur.rowcount > 0
        await self._db.commit()
        if updated:
            logger.info("[世界树] {}·会话归档  {}", actor, session_id[:8])
        return updated

    async def archive_if_idle(
        self, *, now: float, inactive_seconds: float, actor: str,
    ) -> list[str]:
        """批量归档"不活跃"会话。返回受影响的 session_id 列表。

        保护护栏（不会被归档）：
          - archived_at IS NOT NULL（已归档）
          - response_status = 'generating'（正在处理）
          - channel_key != ''（仍有 channel 绑定，说明用户还可能回来）
          - updated_at >= now - inactive_seconds（仍活跃）
        """
        cutoff = now - inactive_seconds
        # 先查出要归档的 id 列表（用于返回 + 给 SessionManager 同步内存）
        async with self._db.execute(
            "SELECT id FROM session_records "
            "WHERE archived_at IS NULL "
            "  AND response_status <> 'generating' "
            "  AND channel_key = '' "
            "  AND updated_at < ?",
            (cutoff,),
        ) as cur:
            rows = await cur.fetchall()
        ids = [r[0] for r in rows]
        if not ids:
            return []

        # 批量 UPDATE
        placeholders = ",".join("?" * len(ids))
        await self._db.execute(
            f"UPDATE session_records SET archived_at = ?, updated_at = ? "
            f"WHERE id IN ({placeholders})",
            (now, now, *ids),
        )
        await self._db.commit()
        logger.info("[世界树] {}·会话批量归档  {} 条", actor, len(ids))
        return ids

    async def purge_expired(
        self, *, now: float, archived_ttl_seconds: float, actor: str,
    ) -> list[str]:
        """彻底删除 archived_at 超过 TTL 的会话。返回被删除的 session_id 列表。"""
        cutoff = now - archived_ttl_seconds
        async with self._db.execute(
            "SELECT id FROM session_records "
            "WHERE archived_at IS NOT NULL AND archived_at < ?",
            (cutoff,),
        ) as cur:
            rows = await cur.fetchall()
        ids = [r[0] for r in rows]
        if not ids:
            return []

        placeholders = ",".join("?" * len(ids))
        await self._db.execute(
            f"DELETE FROM session_records WHERE id IN ({placeholders})",
            tuple(ids),
        )
        await self._db.commit()
        logger.info("[世界树] {}·会话过期清理  删除 {} 条", actor, len(ids))
        return ids

    async def clear_channel_binding(self, channel_key: str, *, except_session: str = "") -> None:
        """把除 except_session 外所有绑到 channel_key 的会话清空 channel_key 字段。"""
        if except_session:
            await self._db.execute(
                "UPDATE session_records SET channel_key = '' "
                "WHERE channel_key = ? AND id <> ?",
                (channel_key, except_session),
            )
        else:
            await self._db.execute(
                "UPDATE session_records SET channel_key = '' WHERE channel_key = ?",
                (channel_key,),
            )
        await self._db.commit()
