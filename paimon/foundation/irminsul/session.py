"""聊天会话域 —— 世界树域 9

唯一写入者 / 读取者：派蒙
额外读取者：时执（归档时读旧会话）

设计要点：
- 整个消息链作为 messages_json TEXT 存在一列里
- session_memory（压缩块 list[str]）也存 JSON 数组
- channel_key 表达"此会话当前绑定哪个 channel"；同一 channel 活跃会话集中最多一条
- 含 migrate_from_json：旧 paimon_home/sessions/*.json + state.json 导入
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path

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
            " response_status, created_at, updated_at, archived_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
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
            "  archived_at = excluded.archived_at",
            (
                rec.id, rec.name, rec.channel_key,
                json.dumps(rec.messages, ensure_ascii=False),
                json.dumps(rec.session_memory, ensure_ascii=False),
                rec.last_context_tokens, rec.last_context_ratio,
                rec.last_compressed_at, rec.compressed_rounds,
                rec.response_status,
                created_at, updated_at, rec.archived_at,
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
            "response_status, created_at, updated_at, archived_at "
            "FROM session_records WHERE id = ?",
            (session_id,),
        ) as cur:
            row = await cur.fetchone()
        if not row:
            return None
        return SessionRecord(
            id=row[0], name=row[1], channel_key=row[2],
            messages=json.loads(row[3]) if row[3] else [],
            session_memory=json.loads(row[4]) if row[4] else [],
            last_context_tokens=row[5], last_context_ratio=row[6],
            last_compressed_at=row[7], compressed_rounds=row[8],
            response_status=row[9],
            created_at=row[10], updated_at=row[11], archived_at=row[12],
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
            "response_status, created_at, updated_at, archived_at "
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

    async def migrate_from_json(self, legacy_dir: Path) -> int:
        """把 legacy_dir (paimon_home/sessions/) 下 *.json 导入 session_records 表。
        读 legacy_dir.parent/state.json 拿 bindings（channel_key）。
        完成后把 legacy_dir 改名 sessions.migrated。幂等。
        """
        if not legacy_dir.exists() or not legacy_dir.is_dir():
            return 0

        json_files = list(legacy_dir.glob("*.json"))
        if not json_files:
            try:
                legacy_dir.rename(legacy_dir.parent / "sessions.migrated")
            except Exception:
                pass
            return 0

        # 解析 bindings
        bindings: dict[str, str] = {}
        state_path = legacy_dir.parent / "state.json"
        if state_path.exists():
            try:
                state_data = json.loads(state_path.read_text(encoding="utf-8"))
                bindings = state_data.get("bindings", {}) or {}
            except Exception as e:
                logger.warning("[世界树] 会话迁移  解析 state.json 失败: {}", e)

        sid_to_channel: dict[str, str] = {sid: ch for ch, sid in bindings.items()}

        imported = 0
        for jf in json_files:
            try:
                data = json.loads(jf.read_text(encoding="utf-8"))
            except Exception as e:
                logger.warning("[世界树] 会话迁移  跳过损坏文件 {}: {}", jf.name, e)
                continue

            sid = data.get("id", jf.stem)
            channel_key = sid_to_channel.get(sid, "")
            now = time.time()
            try:
                await self._db.execute(
                    "INSERT OR IGNORE INTO session_records "
                    "(id, name, channel_key, messages_json, session_memory_json, "
                    " last_context_tokens, last_context_ratio, last_compressed_at, compressed_rounds, "
                    " response_status, created_at, updated_at, archived_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL)",
                    (
                        sid,
                        data.get("name", f"s-{sid[:8]}"),
                        channel_key,
                        json.dumps(data.get("messages", []) or [], ensure_ascii=False),
                        json.dumps(data.get("session_memory", []) or [], ensure_ascii=False),
                        int(data.get("last_context_tokens", 0)),
                        float(data.get("last_context_ratio", 0.0)),
                        float(data.get("last_compressed_at", 0.0)),
                        int(data.get("compressed_rounds", 0)),
                        data.get("response_status", "idle"),
                        float(data.get("created_at", now)),
                        float(data.get("updated_at", now)),
                    ),
                )
                imported += 1
            except Exception as e:
                logger.warning("[世界树] 会话迁移  写入失败 {}: {}", jf.name, e)

        await self._db.commit()

        try:
            legacy_dir.rename(legacy_dir.parent / "sessions.migrated")
            logger.info(
                "[世界树] 会话迁移  导入 {} 条，{} 改名为 sessions.migrated",
                imported, legacy_dir.name,
            )
        except Exception as e:
            logger.warning("[世界树] 会话迁移  改名失败: {}", e)

        return imported
