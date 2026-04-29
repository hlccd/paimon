"""域 10: 定时任务（三月调度）"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4

import aiosqlite
from loguru import logger


@dataclass
class ScheduledTask:
    id: str = ""
    chat_id: str = ""
    channel_name: str = ""
    task_prompt: str = ""           # type='user' 时是喂 LLM 的自然语言；内部类型此字段无语义
    trigger_type: str = ""          # "once" | "interval" | "cron"
    trigger_value: dict = field(default_factory=dict)
    enabled: bool = True
    next_run_at: float = 0.0
    last_run_at: float = 0.0
    last_error: str = ""
    consecutive_failures: int = 0
    created_at: float = 0.0
    updated_at: float = 0.0
    # 方案 D：task_type 一等公民（替代旧 task_prompt 里的 [PREFIX] 编码）
    task_type: str = "user"         # 'user' | 'feed_collect' | 'dividend_scan' | ...
    source_entity_id: str = ""      # 业务实体 id（sub_id / mode 等）；'user' 类型下为空


class ScheduleRepo:
    def __init__(self, db: aiosqlite.Connection):
        self._db = db

    async def create(self, task: ScheduledTask, actor: str) -> str:
        if not task.id:
            task.id = uuid4().hex[:12]
        now = time.time()
        if not task.created_at:
            task.created_at = now
        task.updated_at = now

        await self._db.execute(
            "INSERT INTO scheduled_tasks "
            "(id, chat_id, channel_name, task_prompt, trigger_type, trigger_value, "
            "enabled, next_run_at, last_run_at, last_error, consecutive_failures, "
            "created_at, updated_at, task_type, source_entity_id) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                task.id, task.chat_id, task.channel_name, task.task_prompt,
                task.trigger_type, json.dumps(task.trigger_value, ensure_ascii=False),
                1 if task.enabled else 0, task.next_run_at, task.last_run_at,
                task.last_error, task.consecutive_failures,
                task.created_at, task.updated_at,
                task.task_type or "user", task.source_entity_id or "",
            ),
        )
        await self._db.commit()
        logger.info("[世界树] {}·创建定时任务 {} ({})", actor, task.id, task.trigger_type)
        return task.id

    async def get(self, task_id: str) -> ScheduledTask | None:
        async with self._db.execute(
            "SELECT * FROM scheduled_tasks WHERE id = ?", (task_id,),
        ) as cur:
            row = await cur.fetchone()
        return self._row_to_task(row) if row else None

    async def list_all(self, enabled_only: bool = False) -> list[ScheduledTask]:
        sql = "SELECT * FROM scheduled_tasks"
        params: tuple = ()
        if enabled_only:
            sql += " WHERE enabled = 1"
        sql += " ORDER BY next_run_at"
        async with self._db.execute(sql, params) as cur:
            rows = await cur.fetchall()
        return [self._row_to_task(r) for r in rows]

    async def list_due(self, now: float) -> list[ScheduledTask]:
        async with self._db.execute(
            "SELECT * FROM scheduled_tasks WHERE enabled = 1 AND next_run_at > 0 AND next_run_at <= ?",
            (now,),
        ) as cur:
            rows = await cur.fetchall()
        return [self._row_to_task(r) for r in rows]

    async def update(self, task_id: str, actor: str, **fields: Any) -> bool:
        if not fields:
            return False
        fields["updated_at"] = time.time()

        if "trigger_value" in fields and isinstance(fields["trigger_value"], dict):
            fields["trigger_value"] = json.dumps(fields["trigger_value"], ensure_ascii=False)
        if "enabled" in fields:
            fields["enabled"] = 1 if fields["enabled"] else 0

        set_clause = ", ".join(f"{k} = ?" for k in fields)
        values = list(fields.values()) + [task_id]
        async with self._db.execute(
            f"UPDATE scheduled_tasks SET {set_clause} WHERE id = ?", values,
        ) as cur:
            changed = cur.rowcount > 0
        await self._db.commit()
        if changed:
            logger.debug("[世界树] {}·更新定时任务 {}", actor, task_id)
        return changed

    async def delete(self, task_id: str, actor: str) -> bool:
        async with self._db.execute(
            "DELETE FROM scheduled_tasks WHERE id = ?", (task_id,),
        ) as cur:
            deleted = cur.rowcount > 0
        await self._db.commit()
        if deleted:
            logger.info("[世界树] {}·删除定时任务 {}", actor, task_id)
        return deleted

    def _row_to_task(self, row) -> ScheduledTask:
        # 用 SELECT * 取行，列顺序跟 CREATE TABLE + 后续 ALTER 一致：
        # 前 13 列为初始 schema，后 2 列为方案 D 加的 task_type / source_entity_id
        cols = [
            "id", "chat_id", "channel_name", "task_prompt",
            "trigger_type", "trigger_value", "enabled",
            "next_run_at", "last_run_at", "last_error",
            "consecutive_failures", "created_at", "updated_at",
            "task_type", "source_entity_id",
        ]
        d = dict(zip(cols, row))
        try:
            d["trigger_value"] = json.loads(d["trigger_value"])
        except (json.JSONDecodeError, TypeError):
            d["trigger_value"] = {}
        d["enabled"] = bool(d["enabled"])
        # 兜底：旧数据行可能比新 schema 少字段
        d.setdefault("task_type", "user")
        d.setdefault("source_entity_id", "")
        return ScheduledTask(**d)
