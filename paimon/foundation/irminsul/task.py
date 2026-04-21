"""活跃任务域 —— 世界树域 5

唯一写入者：生执 / 空执 / 七神（各自的生命周期阶段）
读取者：派蒙 / 三月面板 / 时执（归档时读出）

4 张表：
- task_edicts   顶层任务
- task_subtasks 子任务（DAG 节点）
- task_flow_history append-only 流转轨迹
- task_progress_log append-only 进度点
"""
from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass

import aiosqlite
from loguru import logger


@dataclass
class TaskEdict:
    id: str
    title: str
    description: str = ""
    creator: str = ""                         # 服务方中文名
    status: str = "pending"
    lifecycle_stage: str = "hot"              # 'hot' | 'cold' | 'archived'
    session_id: str = ""
    created_at: float = 0.0
    updated_at: float = 0.0
    archived_at: float | None = None


@dataclass
class Subtask:
    id: str
    task_id: str
    parent_id: str | None
    assignee: str                             # '草神' / '雷神' / ...
    description: str
    status: str = "pending"
    result: str = ""
    created_at: float = 0.0
    updated_at: float = 0.0


@dataclass
class FlowEntry:
    id: int
    task_id: str
    from_agent: str
    to_agent: str
    action: str
    payload: dict
    created_at: float


@dataclass
class ProgressEntry:
    id: int
    task_id: str
    subtask_id: str | None
    agent: str
    progress_pct: int
    message: str
    created_at: float


class TaskRepo:
    def __init__(self, db: aiosqlite.Connection):
        self._db = db

    # ---------- task_edicts ----------
    async def create(self, edict: TaskEdict, *, actor: str) -> None:
        now = time.time()
        if not edict.id:
            edict.id = uuid.uuid4().hex
        created_at = edict.created_at if edict.created_at > 0 else now
        await self._db.execute(
            "INSERT INTO task_edicts "
            "(id, title, description, creator, status, lifecycle_stage, "
            " session_id, created_at, updated_at, archived_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                edict.id, edict.title, edict.description, edict.creator,
                edict.status, edict.lifecycle_stage, edict.session_id,
                created_at, now, edict.archived_at,
            ),
        )
        await self._db.commit()
        logger.info("[世界树] {}·活跃任务创建  {}", actor, edict.id)

    async def get(self, task_id: str) -> TaskEdict | None:
        async with self._db.execute(
            "SELECT id, title, description, creator, status, lifecycle_stage, "
            "session_id, created_at, updated_at, archived_at "
            "FROM task_edicts WHERE id = ?",
            (task_id,),
        ) as cur:
            row = await cur.fetchone()
        return _row_to_edict(row) if row else None

    async def update_status(
        self, task_id: str, status: str, *, actor: str,
    ) -> None:
        now = time.time()
        # 先取旧状态用于日志
        old = None
        async with self._db.execute(
            "SELECT status FROM task_edicts WHERE id = ?", (task_id,),
        ) as cur:
            r = await cur.fetchone()
            if r:
                old = r[0]
        await self._db.execute(
            "UPDATE task_edicts SET status = ?, updated_at = ? WHERE id = ?",
            (status, now, task_id),
        )
        await self._db.commit()
        logger.info(
            "[世界树] {}·任务状态更新  {}: {} → {}",
            actor, task_id, old or "(none)", status,
        )

    async def update_lifecycle(
        self, task_id: str, stage: str, *, actor: str,
    ) -> None:
        now = time.time()
        archived_at = now if stage == "archived" else None
        await self._db.execute(
            "UPDATE task_edicts SET lifecycle_stage = ?, updated_at = ?, "
            "archived_at = COALESCE(?, archived_at) WHERE id = ?",
            (stage, now, archived_at, task_id),
        )
        await self._db.commit()
        action = "任务归档" if stage == "archived" else f"任务生命周期更新→{stage}"
        logger.info("[世界树] {}·{}  {}", actor, action, task_id)

    async def list(
        self, *,
        status: str | None = None,
        lifecycle_stage: str | None = None,
        session_id: str | None = None,
        limit: int = 100,
    ) -> list[TaskEdict]:
        clauses, params = [], []
        if status is not None:
            clauses.append("status = ?"); params.append(status)
        if lifecycle_stage is not None:
            clauses.append("lifecycle_stage = ?"); params.append(lifecycle_stage)
        if session_id is not None:
            clauses.append("session_id = ?"); params.append(session_id)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        sql = (
            "SELECT id, title, description, creator, status, lifecycle_stage, "
            "session_id, created_at, updated_at, archived_at "
            f"FROM task_edicts {where} ORDER BY updated_at DESC LIMIT ?"
        )
        params.append(limit)
        async with self._db.execute(sql, tuple(params)) as cur:
            rows = await cur.fetchall()
        return [_row_to_edict(r) for r in rows]

    # ---------- subtasks ----------
    async def subtask_create(self, sub: Subtask, *, actor: str) -> None:
        now = time.time()
        if not sub.id:
            sub.id = uuid.uuid4().hex
        created_at = sub.created_at if sub.created_at > 0 else now
        await self._db.execute(
            "INSERT INTO task_subtasks "
            "(id, task_id, parent_id, assignee, description, status, result, "
            " created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                sub.id, sub.task_id, sub.parent_id, sub.assignee,
                sub.description, sub.status, sub.result,
                created_at, now,
            ),
        )
        await self._db.commit()
        logger.info(
            "[世界树] {}·子任务创建  task={} subtask={} ({})",
            actor, sub.task_id, sub.id, sub.assignee,
        )

    async def subtask_update_status(
        self, subtask_id: str, status: str, result: str = "", *, actor: str,
    ) -> None:
        now = time.time()
        await self._db.execute(
            "UPDATE task_subtasks SET status = ?, result = ?, updated_at = ? "
            "WHERE id = ?",
            (status, result, now, subtask_id),
        )
        await self._db.commit()
        logger.info(
            "[世界树] {}·子任务状态更新  {} → {}",
            actor, subtask_id, status,
        )

    async def subtask_list(self, task_id: str) -> list[Subtask]:
        async with self._db.execute(
            "SELECT id, task_id, parent_id, assignee, description, status, result, "
            "created_at, updated_at "
            "FROM task_subtasks WHERE task_id = ? ORDER BY created_at",
            (task_id,),
        ) as cur:
            rows = await cur.fetchall()
        return [_row_to_subtask(r) for r in rows]

    # ---------- flow_history ----------
    async def flow_append(
        self, task_id: str, from_agent: str, to_agent: str, action: str,
        payload: dict | None = None, *, actor: str,
    ) -> None:
        await self._db.execute(
            "INSERT INTO task_flow_history "
            "(task_id, from_agent, to_agent, action, payload, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                task_id, from_agent, to_agent, action,
                json.dumps(payload or {}, ensure_ascii=False),
                time.time(),
            ),
        )
        await self._db.commit()
        logger.info(
            "[世界树] {}·流转记录  task={} {}→{} ({})",
            actor, task_id, from_agent, to_agent, action,
        )

    async def flow_list(self, task_id: str) -> list[FlowEntry]:
        async with self._db.execute(
            "SELECT id, task_id, from_agent, to_agent, action, payload, created_at "
            "FROM task_flow_history WHERE task_id = ? ORDER BY id",
            (task_id,),
        ) as cur:
            rows = await cur.fetchall()
        return [
            FlowEntry(
                id=r[0], task_id=r[1], from_agent=r[2], to_agent=r[3],
                action=r[4], payload=json.loads(r[5]) if r[5] else {},
                created_at=r[6],
            )
            for r in rows
        ]

    # ---------- progress_log ----------
    async def progress_append(
        self, task_id: str, agent: str, progress_pct: int,
        message: str = "", subtask_id: str | None = None,
        *, actor: str,
    ) -> None:
        await self._db.execute(
            "INSERT INTO task_progress_log "
            "(task_id, subtask_id, agent, progress_pct, message, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (task_id, subtask_id, agent, progress_pct, message, time.time()),
        )
        await self._db.commit()
        logger.info(
            "[世界树] {}·进度记录  task={} {}% ({})",
            actor, task_id, progress_pct, agent,
        )

    async def progress_list(self, task_id: str) -> list[ProgressEntry]:
        async with self._db.execute(
            "SELECT id, task_id, subtask_id, agent, progress_pct, message, created_at "
            "FROM task_progress_log WHERE task_id = ? ORDER BY id",
            (task_id,),
        ) as cur:
            rows = await cur.fetchall()
        return [
            ProgressEntry(
                id=r[0], task_id=r[1], subtask_id=r[2], agent=r[3],
                progress_pct=r[4], message=r[5], created_at=r[6],
            )
            for r in rows
        ]


def _row_to_edict(row) -> TaskEdict:
    return TaskEdict(
        id=row[0], title=row[1], description=row[2], creator=row[3],
        status=row[4], lifecycle_stage=row[5], session_id=row[6],
        created_at=row[7], updated_at=row[8], archived_at=row[9],
    )


def _row_to_subtask(row) -> Subtask:
    return Subtask(
        id=row[0], task_id=row[1], parent_id=row[2], assignee=row[3],
        description=row[4], status=row[5], result=row[6],
        created_at=row[7], updated_at=row[8],
    )
