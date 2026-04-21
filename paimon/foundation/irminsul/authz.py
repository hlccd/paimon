"""授权记录域（authz）—— 世界树域 1

唯一写入者：派蒙（对话写）、草神面板（撤销写）
读取者：派蒙 / 死执（启动 snapshot 灌缓存）、草神面板（UI 展示）
"""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass

import aiosqlite
from loguru import logger


@dataclass
class Authz:
    id: str
    subject_type: str       # 'skill' | 'tool'
    subject_id: str
    decision: str           # 'permanent_allow' | 'permanent_deny'
    user_id: str
    session_id: str
    reason: str
    created_at: float
    updated_at: float


class AuthzRepo:
    def __init__(self, db: aiosqlite.Connection):
        self._db = db

    async def get(
        self, subject_type: str, subject_id: str, *, user_id: str = "default"
    ) -> Authz | None:
        async with self._db.execute(
            "SELECT id, subject_type, subject_id, decision, user_id, session_id, "
            "reason, created_at, updated_at "
            "FROM authz_records "
            "WHERE subject_type = ? AND subject_id = ? AND user_id = ?",
            (subject_type, subject_id, user_id),
        ) as cur:
            row = await cur.fetchone()
        return _row_to_authz(row) if row else None

    async def set(
        self,
        subject_type: str,
        subject_id: str,
        decision: str,
        *,
        user_id: str = "default",
        session_id: str = "",
        reason: str = "",
        actor: str,
    ) -> None:
        now = time.time()
        new_id = uuid.uuid4().hex
        # UPSERT：命中 UNIQUE(subject_type, subject_id, user_id) 时更新 decision / reason / updated_at
        await self._db.execute(
            "INSERT INTO authz_records "
            "(id, subject_type, subject_id, decision, user_id, session_id, reason, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(subject_type, subject_id, user_id) DO UPDATE SET "
            "  decision = excluded.decision, "
            "  session_id = excluded.session_id, "
            "  reason = excluded.reason, "
            "  updated_at = excluded.updated_at",
            (new_id, subject_type, subject_id, decision, user_id, session_id, reason, now, now),
        )
        await self._db.commit()
        logger.info(
            "[世界树] {}·授权写入  {}/{} → {}",
            actor, subject_type, subject_id, decision,
        )

    async def revoke(
        self, subject_type: str, subject_id: str,
        *, user_id: str = "default", actor: str,
    ) -> bool:
        async with self._db.execute(
            "DELETE FROM authz_records "
            "WHERE subject_type = ? AND subject_id = ? AND user_id = ?",
            (subject_type, subject_id, user_id),
        ) as cur:
            deleted = cur.rowcount > 0
        await self._db.commit()
        if deleted:
            logger.info(
                "[世界树] {}·授权撤销  {}/{}",
                actor, subject_type, subject_id,
            )
        return deleted

    async def list(self, *, user_id: str = "default") -> list[Authz]:
        async with self._db.execute(
            "SELECT id, subject_type, subject_id, decision, user_id, session_id, "
            "reason, created_at, updated_at "
            "FROM authz_records WHERE user_id = ? "
            "ORDER BY updated_at DESC",
            (user_id,),
        ) as cur:
            rows = await cur.fetchall()
        return [_row_to_authz(r) for r in rows]

    async def snapshot(
        self, *, user_id: str = "default"
    ) -> dict[tuple[str, str], str]:
        """启动灌缓存用：返回 {(subject_type, subject_id): decision}"""
        async with self._db.execute(
            "SELECT subject_type, subject_id, decision "
            "FROM authz_records WHERE user_id = ?",
            (user_id,),
        ) as cur:
            return {(r[0], r[1]): r[2] async for r in cur}


def _row_to_authz(row) -> Authz:
    return Authz(
        id=row[0], subject_type=row[1], subject_id=row[2], decision=row[3],
        user_id=row[4], session_id=row[5], reason=row[6],
        created_at=row[7], updated_at=row[8],
    )
