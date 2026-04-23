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
    status: str = "pending"                   # pending / running / completed / failed / skipped / superseded
    result: str = ""
    created_at: float = 0.0
    updated_at: float = 0.0
    # 四影闭环扩展（2026-04-23）
    deps: list[str] | None = None             # 前置子任务 id 列表；None/空表示无依赖
    round: int = 1                            # 所属轮次（每轮生成/修订 +1）
    sensitive_ops: list[str] | None = None    # 预计调用的敏感工具（供死执 scan_plan 使用）
    verdict_status: str = ""                  # 水神裁决后打标：passed / needs_revise / needs_redo
    compensate: str = ""                      # saga 补偿动作（自然语言；失败回滚时交火神执行）


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
            " created_at, updated_at, deps, round, sensitive_ops, verdict_status, compensate) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                sub.id, sub.task_id, sub.parent_id, sub.assignee,
                sub.description, sub.status, sub.result,
                created_at, now,
                json.dumps(sub.deps or [], ensure_ascii=False),
                sub.round,
                json.dumps(sub.sensitive_ops or [], ensure_ascii=False),
                sub.verdict_status,
                sub.compensate or "",
            ),
        )
        await self._db.commit()
        logger.info(
            "[世界树] {}·子任务创建  task={} subtask={} ({}) round={} deps={}",
            actor, sub.task_id, sub.id, sub.assignee, sub.round, sub.deps or [],
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

    async def subtask_update_verdict(
        self, subtask_id: str, verdict_status: str, *, actor: str,
    ) -> None:
        """水神裁决后为单个子任务打标。"""
        now = time.time()
        await self._db.execute(
            "UPDATE task_subtasks SET verdict_status = ?, updated_at = ? WHERE id = ?",
            (verdict_status, now, subtask_id),
        )
        await self._db.commit()
        logger.info(
            "[世界树] {}·子任务裁决  {} → {}",
            actor, subtask_id, verdict_status,
        )

    async def subtask_list(self, task_id: str) -> list[Subtask]:
        async with self._db.execute(
            "SELECT id, task_id, parent_id, assignee, description, status, result, "
            "created_at, updated_at, deps, round, sensitive_ops, verdict_status, compensate "
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
    # 兼容旧行（新列迁移过渡；缺列时用默认值）
    deps_raw = row[9] if len(row) > 9 else None
    round_n = row[10] if len(row) > 10 else 1
    sops_raw = row[11] if len(row) > 11 else None
    verdict = row[12] if len(row) > 12 else ""
    compensate = row[13] if len(row) > 13 else ""
    try:
        deps = json.loads(deps_raw) if deps_raw else []
    except Exception:
        deps = []
    try:
        sensitive_ops = json.loads(sops_raw) if sops_raw else []
    except Exception:
        sensitive_ops = []
    return Subtask(
        id=row[0], task_id=row[1], parent_id=row[2], assignee=row[3],
        description=row[4], status=row[5], result=row[6],
        created_at=row[7], updated_at=row[8],
        deps=deps, round=round_n or 1,
        sensitive_ops=sensitive_ops, verdict_status=verdict or "",
        compensate=compensate or "",
    )
