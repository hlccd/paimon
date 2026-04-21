"""记忆域 —— 世界树域 4

唯一写入者：草神（时执收尾抽取 / 面板编辑 / 三月反思合并）
读取者：派蒙（prefetch）/ 草神 / 三月（反思）
承载"个人偏好"（user 类）+"习惯纠正"（feedback 类）等跨会话记忆。

存储介质：
- memory_index 表 —— 元数据（id/type/subject/tags/ttl 等），支持按索引字段查
- 文件系统 .paimon/irminsul/memory/{type}/{subject}/{id}.md —— body 正文
"""
from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path

import aiosqlite
from loguru import logger

from ._paths import resolve_safe


@dataclass
class MemoryMeta:
    """轻量版（list 查询返回，不含 body）"""
    id: str
    mem_type: str
    subject: str
    title: str
    tags: list[str] = field(default_factory=list)
    source: str = ""
    created_at: float = 0.0
    updated_at: float = 0.0
    ttl: float | None = None


@dataclass
class Memory(MemoryMeta):
    """带 body 的完整版"""
    body: str = ""


class MemoryRepo:
    def __init__(self, db: aiosqlite.Connection, root: Path):
        """root = paimon_home/irminsul/memory"""
        self._db = db
        self._root = root

    def _body_path(self, mem_type: str, subject: str, mem_id: str) -> Path:
        filename = f"{mem_id}.md"
        return resolve_safe(self._root, mem_type, subject, filename)

    async def write(
        self, *,
        mem_type: str,
        subject: str,
        title: str,
        body: str,
        tags: list[str] | None = None,
        source: str = "",
        ttl: float | None = None,
        actor: str,
    ) -> str:
        mem_id = uuid.uuid4().hex
        now = time.time()
        tags = tags or []

        # body 写文件
        path = self._body_path(mem_type, subject, mem_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")

        # 元数据入库
        await self._db.execute(
            "INSERT INTO memory_index "
            "(id, mem_type, subject, title, tags, source, created_at, updated_at, ttl) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                mem_id, mem_type, subject, title,
                json.dumps(tags, ensure_ascii=False),
                source, now, now, ttl,
            ),
        )
        await self._db.commit()
        logger.info(
            "[世界树] {}·记忆写入  {}/{}: {}",
            actor, mem_type, subject, title[:40],
        )
        return mem_id

    async def get(self, mem_id: str) -> Memory | None:
        async with self._db.execute(
            "SELECT id, mem_type, subject, title, tags, source, "
            "created_at, updated_at, ttl "
            "FROM memory_index WHERE id = ?",
            (mem_id,),
        ) as cur:
            row = await cur.fetchone()
        if not row:
            return None
        meta = _row_to_meta(row)
        try:
            path = self._body_path(meta.mem_type, meta.subject, meta.id)
            body = path.read_text(encoding="utf-8") if path.is_file() else ""
        except ValueError:
            body = ""
        return Memory(
            id=meta.id, mem_type=meta.mem_type, subject=meta.subject,
            title=meta.title, tags=meta.tags, source=meta.source,
            created_at=meta.created_at, updated_at=meta.updated_at,
            ttl=meta.ttl, body=body,
        )

    async def list(
        self, *,
        mem_type: str | None = None,
        subject: str | None = None,
        tags_any: list[str] | None = None,
        limit: int = 100,
    ) -> list[MemoryMeta]:
        """不返回 body。tags_any 用 LIKE 匹配（简化，未来可上 json_each）。"""
        clauses, params = [], []
        if mem_type is not None:
            clauses.append("mem_type = ?")
            params.append(mem_type)
        if subject is not None:
            clauses.append("subject = ?")
            params.append(subject)
        if tags_any:
            # tags 字段是 JSON 数组字符串；用 OR+LIKE 简化匹配
            or_clauses = []
            for t in tags_any:
                or_clauses.append("tags LIKE ?")
                params.append(f'%"{t}"%')
            clauses.append(f"({' OR '.join(or_clauses)})")
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        sql = (
            "SELECT id, mem_type, subject, title, tags, source, "
            "created_at, updated_at, ttl "
            f"FROM memory_index {where} "
            "ORDER BY updated_at DESC LIMIT ?"
        )
        params.append(limit)
        async with self._db.execute(sql, tuple(params)) as cur:
            rows = await cur.fetchall()
        return [_row_to_meta(r) for r in rows]

    async def update(
        self, mem_id: str, *,
        title: str | None = None,
        body: str | None = None,
        tags: list[str] | None = None,
        ttl: float | None = None,
        actor: str,
    ) -> bool:
        # 先拿当前元数据
        meta = await self._get_meta(mem_id)
        if not meta:
            return False
        now = time.time()
        sets, params = ["updated_at = ?"], [now]
        if title is not None:
            sets.append("title = ?"); params.append(title)
        if tags is not None:
            sets.append("tags = ?"); params.append(json.dumps(tags, ensure_ascii=False))
        if ttl is not None:
            sets.append("ttl = ?"); params.append(ttl)
        params.append(mem_id)

        if body is not None:
            try:
                path = self._body_path(meta.mem_type, meta.subject, meta.id)
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(body, encoding="utf-8")
            except ValueError:
                return False

        await self._db.execute(
            f"UPDATE memory_index SET {', '.join(sets)} WHERE id = ?",
            tuple(params),
        )
        await self._db.commit()
        logger.info("[世界树] {}·记忆更新  {}", actor, mem_id)
        return True

    async def delete(self, mem_id: str, *, actor: str) -> bool:
        meta = await self._get_meta(mem_id)
        if not meta:
            return False
        # 先删文件（失败不阻塞 DB 删除，孤儿文件后续再收拾）
        try:
            path = self._body_path(meta.mem_type, meta.subject, meta.id)
            if path.is_file():
                path.unlink()
        except ValueError:
            pass
        await self._db.execute("DELETE FROM memory_index WHERE id = ?", (mem_id,))
        await self._db.commit()
        logger.info("[世界树] {}·记忆删除  {}", actor, mem_id)
        return True

    async def expire(self, now: float, *, actor: str) -> int:
        """三月定时调。返回清理的条数。"""
        async with self._db.execute(
            "SELECT id FROM memory_index WHERE ttl IS NOT NULL AND ttl < ?",
            (now,),
        ) as cur:
            ids = [r[0] async for r in cur]
        count = 0
        for mid in ids:
            if await self.delete(mid, actor=actor):
                count += 1
        if count:
            logger.info("[世界树] {}·记忆过期清理  共 {} 条", actor, count)
        return count

    async def _get_meta(self, mem_id: str) -> MemoryMeta | None:
        async with self._db.execute(
            "SELECT id, mem_type, subject, title, tags, source, "
            "created_at, updated_at, ttl "
            "FROM memory_index WHERE id = ?",
            (mem_id,),
        ) as cur:
            row = await cur.fetchone()
        return _row_to_meta(row) if row else None


def _row_to_meta(row) -> MemoryMeta:
    return MemoryMeta(
        id=row[0], mem_type=row[1], subject=row[2], title=row[3],
        tags=json.loads(row[4]) if row[4] else [],
        source=row[5], created_at=row[6], updated_at=row[7], ttl=row[8],
    )
