"""订阅数据域 —— 世界树域 11

唯一写入者：风神（采集入库）、派蒙（指令写订阅 / 撤销）、WebUI 面板（增删改）
读取者：风神（采集前读订阅 / 去重）、派蒙指令（列表）、WebUI 面板

职责：
- subscriptions 表：用户关注的主题（query + cron + 推送目标）
- feed_items 表：采集到的条目（去重 + 推送状态）
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any
from uuid import uuid4

import aiosqlite
from loguru import logger


@dataclass
class Subscription:
    id: str = ""
    user_id: str = "default"
    query: str = ""
    channel_name: str = ""
    chat_id: str = ""
    schedule_cron: str = ""
    max_items: int = 10
    engine: str = ""                  # "" = 双引擎 / "baidu" / "bing"
    enabled: bool = True
    linked_task_id: str = ""
    last_run_at: float = 0.0
    last_error: str = ""
    created_at: float = 0.0
    updated_at: float = 0.0


@dataclass
class FeedItem:
    id: int = 0
    subscription_id: str = ""
    url: str = ""
    title: str = ""
    description: str = ""
    engine: str = ""
    captured_at: float = 0.0
    pushed_at: float | None = None
    digest_id: str = ""


class SubscriptionRepo:
    def __init__(self, db: aiosqlite.Connection):
        self._db = db

    # ---------- 订阅 ----------

    async def create(self, sub: Subscription, actor: str) -> str:
        if not sub.id:
            sub.id = uuid4().hex[:12]
        now = time.time()
        if not sub.created_at:
            sub.created_at = now
        sub.updated_at = now

        await self._db.execute(
            "INSERT INTO subscriptions "
            "(id, user_id, query, channel_name, chat_id, schedule_cron, "
            "max_items, engine, enabled, linked_task_id, last_run_at, "
            "last_error, created_at, updated_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                sub.id, sub.user_id, sub.query, sub.channel_name, sub.chat_id,
                sub.schedule_cron, sub.max_items, sub.engine,
                1 if sub.enabled else 0, sub.linked_task_id,
                sub.last_run_at, sub.last_error,
                sub.created_at, sub.updated_at,
            ),
        )
        await self._db.commit()
        logger.info(
            "[世界树] {}·创建订阅 {} query='{}' cron='{}'",
            actor, sub.id, sub.query[:30], sub.schedule_cron,
        )
        return sub.id

    async def get(self, sub_id: str) -> Subscription | None:
        async with self._db.execute(
            "SELECT * FROM subscriptions WHERE id = ?", (sub_id,),
        ) as cur:
            row = await cur.fetchone()
        return self._row_to_sub(row) if row else None

    async def list(
        self, *,
        user_id: str | None = None,
        enabled_only: bool = False,
    ) -> list[Subscription]:
        clauses, params = [], []
        if user_id is not None:
            clauses.append("user_id = ?"); params.append(user_id)
        if enabled_only:
            clauses.append("enabled = 1")
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        sql = f"SELECT * FROM subscriptions {where} ORDER BY created_at DESC"
        async with self._db.execute(sql, tuple(params)) as cur:
            rows = await cur.fetchall()
        return [self._row_to_sub(r) for r in rows]

    async def update(self, sub_id: str, actor: str, **fields: Any) -> bool:
        if not fields:
            return False
        fields["updated_at"] = time.time()
        if "enabled" in fields:
            fields["enabled"] = 1 if fields["enabled"] else 0

        set_clause = ", ".join(f"{k} = ?" for k in fields)
        values = list(fields.values()) + [sub_id]
        async with self._db.execute(
            f"UPDATE subscriptions SET {set_clause} WHERE id = ?", values,
        ) as cur:
            changed = cur.rowcount > 0
        await self._db.commit()
        if changed:
            logger.debug("[世界树] {}·更新订阅 {}", actor, sub_id)
        return changed

    async def delete(self, sub_id: str, actor: str) -> bool:
        # 先级联删 feed_items（FK 声明了但没开 CASCADE，这里主动清）
        await self._db.execute(
            "DELETE FROM feed_items WHERE subscription_id = ?", (sub_id,),
        )
        async with self._db.execute(
            "DELETE FROM subscriptions WHERE id = ?", (sub_id,),
        ) as cur:
            deleted = cur.rowcount > 0
        await self._db.commit()
        if deleted:
            logger.info("[世界树] {}·删除订阅 {}", actor, sub_id)
        return deleted

    # ---------- feed_items ----------

    async def insert_feed_items(
        self, sub_id: str, items: list[dict], actor: str,
    ) -> list[int]:
        """批量插入条目，已存在的 url 跳过。返回实际插入的 rowid 列表。"""
        if not items:
            return []
        now = time.time()
        inserted_ids: list[int] = []
        for it in items:
            url = (it.get("url") or "").strip()
            if not url:
                continue
            async with self._db.execute(
                "INSERT OR IGNORE INTO feed_items "
                "(subscription_id, url, title, description, engine, captured_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (
                    sub_id, url,
                    (it.get("title") or "")[:500],
                    (it.get("description") or "")[:2000],
                    (it.get("engine") or "")[:20],
                    now,
                ),
            ) as cur:
                if cur.rowcount > 0 and cur.lastrowid:
                    inserted_ids.append(cur.lastrowid)
        await self._db.commit()
        if inserted_ids:
            logger.info(
                "[世界树] {}·订阅条目入库 sub={} 新增={}",
                actor, sub_id, len(inserted_ids),
            )
        return inserted_ids

    async def list_feed_items(
        self, *,
        sub_id: str | None = None,
        since: float | None = None,
        only_unpushed: bool = False,
        limit: int = 200,
    ) -> list[FeedItem]:
        clauses, params = [], []
        if sub_id is not None:
            clauses.append("subscription_id = ?"); params.append(sub_id)
        if since is not None:
            clauses.append("captured_at >= ?"); params.append(since)
        if only_unpushed:
            clauses.append("pushed_at IS NULL")
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        sql = (
            "SELECT id, subscription_id, url, title, description, engine, "
            "captured_at, pushed_at, digest_id "
            f"FROM feed_items {where} ORDER BY captured_at DESC LIMIT ?"
        )
        params.append(limit)
        async with self._db.execute(sql, tuple(params)) as cur:
            rows = await cur.fetchall()
        return [
            FeedItem(
                id=r[0], subscription_id=r[1], url=r[2], title=r[3],
                description=r[4], engine=r[5], captured_at=r[6],
                pushed_at=r[7], digest_id=r[8],
            )
            for r in rows
        ]

    async def mark_feed_items_pushed(
        self, ids: list[int], digest_id: str, actor: str,
    ) -> int:
        if not ids:
            return 0
        now = time.time()
        placeholders = ",".join("?" * len(ids))
        async with self._db.execute(
            f"UPDATE feed_items SET pushed_at = ?, digest_id = ? "
            f"WHERE id IN ({placeholders})",
            (now, digest_id, *ids),
        ) as cur:
            changed = cur.rowcount
        await self._db.commit()
        if changed > 0:
            logger.debug(
                "[世界树] {}·条目标记推送 digest={} count={}",
                actor, digest_id[:8], changed,
            )
        return changed

    async def existing_urls(
        self, sub_id: str, since_ts: float = 0,
    ) -> set[str]:
        """返回该订阅下 captured_at >= since_ts 的所有 url（去重用）。"""
        async with self._db.execute(
            "SELECT url FROM feed_items "
            "WHERE subscription_id = ? AND captured_at >= ?",
            (sub_id, since_ts),
        ) as cur:
            rows = await cur.fetchall()
        return {r[0] for r in rows}

    async def count_feed_items(
        self, *,
        sub_id: str | None = None,
        since: float | None = None,
    ) -> int:
        clauses, params = [], []
        if sub_id is not None:
            clauses.append("subscription_id = ?"); params.append(sub_id)
        if since is not None:
            clauses.append("captured_at >= ?"); params.append(since)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        async with self._db.execute(
            f"SELECT COUNT(*) FROM feed_items {where}", tuple(params),
        ) as cur:
            row = await cur.fetchone()
        return int(row[0]) if row else 0

    # ---------- 行映射 ----------

    def _row_to_sub(self, row) -> Subscription:
        cols = [
            "id", "user_id", "query", "channel_name", "chat_id",
            "schedule_cron", "max_items", "engine", "enabled",
            "linked_task_id", "last_run_at", "last_error",
            "created_at", "updated_at",
        ]
        d = dict(zip(cols, row))
        d["enabled"] = bool(d["enabled"])
        return Subscription(**d)
