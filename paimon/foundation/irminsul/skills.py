"""Skill 生态声明域 —— 世界树域 2

唯一写入者：冰神（扫 skills/ + 运行时装载 plugin + AI 自举生成）
读取者：派蒙 / 死执（启动 snapshot 灌缓存）
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field

import aiosqlite
from loguru import logger


@dataclass
class SkillDecl:
    name: str
    source: str = "builtin"                   # 'builtin' | 'plugin' | 'ai_gen'
    origin: str = ""                          # ai_gen 场景记 proposed_by_session
    sensitivity: str = "normal"               # 'normal' | 'sensitive'
    description: str = ""
    triggers: str = ""
    allowed_tools: list[str] = field(default_factory=list)
    manifest_json: dict = field(default_factory=dict)
    orphaned: bool = False
    installed_at: float = 0.0                 # 0 → 写入时 repo 填 time.time()
    updated_at: float = 0.0


class SkillRepo:
    def __init__(self, db: aiosqlite.Connection):
        self._db = db

    async def declare(self, decl: SkillDecl, *, actor: str) -> None:
        """UPSERT：同名 skill 覆盖（幂等扫描安全）"""
        now = time.time()
        installed_at = decl.installed_at if decl.installed_at > 0 else now
        await self._db.execute(
            "INSERT INTO skill_declarations "
            "(name, source, origin, sensitivity, description, triggers, "
            " allowed_tools, manifest_json, orphaned, installed_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(name) DO UPDATE SET "
            "  source = excluded.source, "
            "  origin = excluded.origin, "
            "  sensitivity = excluded.sensitivity, "
            "  description = excluded.description, "
            "  triggers = excluded.triggers, "
            "  allowed_tools = excluded.allowed_tools, "
            "  manifest_json = excluded.manifest_json, "
            "  orphaned = excluded.orphaned, "
            "  updated_at = excluded.updated_at",
            (
                decl.name, decl.source, decl.origin, decl.sensitivity,
                decl.description, decl.triggers,
                json.dumps(decl.allowed_tools, ensure_ascii=False),
                json.dumps(decl.manifest_json, ensure_ascii=False),
                1 if decl.orphaned else 0,
                installed_at, now,
            ),
        )
        await self._db.commit()
        logger.info(
            "[世界树] {}·Skill 声明  {} ({}, sensitivity={})",
            actor, decl.name, decl.source, decl.sensitivity,
        )

    async def get(self, name: str) -> SkillDecl | None:
        async with self._db.execute(
            "SELECT name, source, origin, sensitivity, description, triggers, "
            "allowed_tools, manifest_json, orphaned, installed_at, updated_at "
            "FROM skill_declarations WHERE name = ?",
            (name,),
        ) as cur:
            row = await cur.fetchone()
        return _row_to_skill(row) if row else None

    async def list(
        self, *,
        source: str | None = None,
        include_orphaned: bool = False,
    ) -> list[SkillDecl]:
        clauses, params = [], []
        if source is not None:
            clauses.append("source = ?")
            params.append(source)
        if not include_orphaned:
            clauses.append("orphaned = 0")
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        sql = (
            "SELECT name, source, origin, sensitivity, description, triggers, "
            "allowed_tools, manifest_json, orphaned, installed_at, updated_at "
            f"FROM skill_declarations {where} ORDER BY name"
        )
        async with self._db.execute(sql, tuple(params)) as cur:
            rows = await cur.fetchall()
        return [_row_to_skill(r) for r in rows]

    async def mark_orphaned(self, name: str, orphaned: bool, *, actor: str) -> None:
        now = time.time()
        await self._db.execute(
            "UPDATE skill_declarations SET orphaned = ?, updated_at = ? WHERE name = ?",
            (1 if orphaned else 0, now, name),
        )
        await self._db.commit()
        action = "Skill 标记孤儿" if orphaned else "Skill 清除孤儿标记"
        logger.info("[世界树] {}·{}  {}", actor, action, name)

    async def remove(self, name: str, *, actor: str) -> bool:
        async with self._db.execute(
            "DELETE FROM skill_declarations WHERE name = ?", (name,),
        ) as cur:
            deleted = cur.rowcount > 0
        await self._db.commit()
        if deleted:
            logger.info("[世界树] {}·Skill 移除  {}", actor, name)
        return deleted

    async def snapshot(self, *, include_orphaned: bool = False) -> list[SkillDecl]:
        return await self.list(include_orphaned=include_orphaned)


def _row_to_skill(row) -> SkillDecl:
    return SkillDecl(
        name=row[0], source=row[1], origin=row[2], sensitivity=row[3],
        description=row[4], triggers=row[5],
        allowed_tools=json.loads(row[6]) if row[6] else [],
        manifest_json=json.loads(row[7]) if row[7] else {},
        orphaned=bool(row[8]),
        installed_at=row[9], updated_at=row[10],
    )
