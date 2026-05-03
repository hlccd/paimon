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
    # 业务实体绑定（订阅生命周期改造）：
    # - binding_kind='manual'：用户在 /feed 手填关键词订阅（默认值，旧数据迁移后归此）
    # - binding_kind='mihoyo_game'：水神隐式订阅，binding_id='{game}:{uid}'
    # - 后续可扩 'stock_watch' 等
    # 命名区别于 ScheduledTask.source_entity_id（那个存 sub_id），避坑同名异义
    binding_kind: str = "manual"
    binding_id: str = ""


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
    event_id: str = ""
    sentiment_score: float = 0.0
    sentiment_label: str = ""


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
            "last_error, created_at, updated_at, binding_kind, binding_id) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                sub.id, sub.user_id, sub.query, sub.channel_name, sub.chat_id,
                sub.schedule_cron, sub.max_items, sub.engine,
                1 if sub.enabled else 0, sub.linked_task_id,
                sub.last_run_at, sub.last_error,
                sub.created_at, sub.updated_at,
                sub.binding_kind, sub.binding_id,
            ),
        )
        await self._db.commit()
        logger.info(
            "[世界树] {}·创建订阅 {} kind={} binding={} query='{}' cron='{}'",
            actor, sub.id, sub.binding_kind, sub.binding_id,
            sub.query[:30], sub.schedule_cron,
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

    # 列名白名单：拒绝未知 key 进入 SQL（防 SEC-001 SQL 注入面）
    # 与 Subscription 字段对齐；id/created_at 不允许通过 update 改
    _UPDATE_ALLOWED = frozenset({
        "user_id", "query", "channel_name", "chat_id",
        "schedule_cron", "max_items", "engine", "enabled",
        "linked_task_id", "last_run_at", "last_error",
        "updated_at", "binding_kind", "binding_id",
    })

    async def update(self, sub_id: str, actor: str, **fields: Any) -> bool:
        if not fields:
            return False
        unknown = set(fields) - self._UPDATE_ALLOWED
        if unknown:
            raise ValueError(
                f"SubscriptionRepo.update 不允许字段 {sorted(unknown)}; "
                f"允许 {sorted(self._UPDATE_ALLOWED)}"
            )
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
        # 先级联删 feed_items + feed_events（FK 开 ON，没声明 CASCADE，这里主动清）
        # 漏删 feed_events 会触发 FOREIGN KEY constraint failed，整个 delete 失败
        await self._db.execute(
            "DELETE FROM feed_items WHERE subscription_id = ?", (sub_id,),
        )
        await self._db.execute(
            "DELETE FROM feed_events WHERE subscription_id = ?", (sub_id,),
        )
        async with self._db.execute(
            "DELETE FROM subscriptions WHERE id = ?", (sub_id,),
        ) as cur:
            deleted = cur.rowcount > 0
        await self._db.commit()
        if deleted:
            logger.info("[世界树] {}·删除订阅 {}", actor, sub_id)
        return deleted

    # ---------- 业务实体绑定（订阅生命周期改造）----------

    async def list_by_binding(
        self, binding_kind: str, binding_id: str = "",
    ) -> list[Subscription]:
        """按 (binding_kind, binding_id) 过滤订阅。binding_id="" 时返该 kind 全部。"""
        if binding_id:
            sql = (
                "SELECT * FROM subscriptions "
                "WHERE binding_kind = ? AND binding_id = ? "
                "ORDER BY created_at ASC"
            )
            params: tuple = (binding_kind, binding_id)
        else:
            sql = (
                "SELECT * FROM subscriptions "
                "WHERE binding_kind = ? "
                "ORDER BY created_at ASC"
            )
            params = (binding_kind,)
        async with self._db.execute(sql, params) as cur:
            rows = await cur.fetchall()
        return [self._row_to_sub(r) for r in rows]

    async def ensure_for(
        self, *,
        binding_kind: str,
        binding_id: str,
        query: str,
        schedule_cron: str,
        channel_name: str,
        chat_id: str,
        max_items: int = 10,
        engine: str = "",
        actor: str,
    ) -> Subscription:
        """幂等：(binding_kind, binding_id) 已存在则更新 query/cron 并返回；不存在则 create。

        archon 业务层在"绑定实体"时调用，比如水神扫码 confirm 后给账号 ensure 游戏资讯订阅。
        """
        existing = await self.list_by_binding(binding_kind, binding_id)
        if existing:
            sub = existing[0]
            await self.update(
                sub.id, actor=actor,
                query=query, schedule_cron=schedule_cron,
                channel_name=channel_name, chat_id=chat_id,
                max_items=max_items, engine=engine,
            )
            return await self.get(sub.id) or sub
        # 不存在，create
        sub = Subscription(
            query=query, schedule_cron=schedule_cron,
            channel_name=channel_name, chat_id=chat_id,
            max_items=max_items, engine=engine,
            binding_kind=binding_kind, binding_id=binding_id,
        )
        await self.create(sub, actor=actor)
        return sub

    async def clear_for(
        self, binding_kind: str, binding_id: str, *, actor: str,
    ) -> list[str]:
        """删除该 (binding_kind, binding_id) 下所有订阅。返回被删 sub_id 列表。

        必须循环调 self.delete()——它主动清 feed_items + feed_events，
        裸 DELETE FROM subscriptions WHERE ... 会因 FK 约束失败。
        调用方拿到 sub_id 列表后自行清 march 的 ScheduledTask（Repo 不碰 march）。
        """
        subs = await self.list_by_binding(binding_kind, binding_id)
        deleted_ids: list[str] = []
        for sub in subs:
            if await self.delete(sub.id, actor=actor):
                deleted_ids.append(sub.id)
        if deleted_ids:
            logger.info(
                "[世界树] {}·清空绑定订阅 kind={} id={} 共 {} 条",
                actor, binding_kind, binding_id, len(deleted_ids),
            )
        return deleted_ids

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

    async def insert_feed_items_with_records(
        self, sub_id: str, items: list[dict], actor: str,
    ) -> list[dict]:
        """跟 insert_feed_items 等价，但返回 [{id, **orig_item}]。

        用途：风神事件聚类需要 db id + 原始字段配套传给 EventClusterer。
        - 跳过空 url / 已存在 url（INSERT OR IGNORE）
        - 返回结构：list of dict，每个 dict 含 db `id` + 原始 title/url/description/engine
        - 顺序与传入 items 一致，被跳过的不会出现在返回里
        """
        if not items:
            return []
        now = time.time()
        records: list[dict] = []
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
                    records.append({
                        "id": cur.lastrowid,
                        "title": (it.get("title") or "")[:500],
                        "url": url,
                        "description": (it.get("description") or "")[:2000],
                        "engine": (it.get("engine") or "")[:20],
                        "captured_at": now,
                    })
        await self._db.commit()
        if records:
            logger.info(
                "[世界树] {}·订阅条目入库 sub={} 新增={}（含 records）",
                actor, sub_id, len(records),
            )
        return records

    async def attach_event(
        self, item_ids: list[int], event_id: str, *,
        sentiment_score: float = 0.0,
        sentiment_label: str = "",
        actor: str,
    ) -> int:
        """把多条 feed_items 关联到一个 event_id + 写条目级情感快照。

        - event_id 用于查询时按事件聚合 / 面板内 join
        - sentiment_* 在条目层冗余存储（面板列表查询不必 join feed_events）
        - 返回实际更新行数
        """
        if not item_ids:
            return 0
        placeholders = ",".join(["?"] * len(item_ids))
        async with self._db.execute(
            f"UPDATE feed_items SET "
            f"event_id = ?, sentiment_score = ?, sentiment_label = ? "
            f"WHERE id IN ({placeholders})",
            (event_id, float(sentiment_score), sentiment_label, *item_ids),
        ) as cur:
            n = cur.rowcount
        await self._db.commit()
        if n:
            logger.info(
                "[世界树] {}·条目挂事件 {} 关联 {} 条 sentiment={}({:+.2f})",
                actor, event_id, n, sentiment_label or "-", sentiment_score,
            )
        return n

    async def list_feed_items(
        self, *,
        sub_id: str | None = None,
        since: float | None = None,
        only_unpushed: bool = False,
        event_id: str | None = None,
        limit: int = 200,
    ) -> list[FeedItem]:
        clauses, params = [], []
        if sub_id is not None:
            clauses.append("subscription_id = ?"); params.append(sub_id)
        if since is not None:
            clauses.append("captured_at >= ?"); params.append(since)
        if only_unpushed:
            clauses.append("pushed_at IS NULL")
        if event_id is not None:
            clauses.append("event_id = ?"); params.append(event_id)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        sql = (
            "SELECT id, subscription_id, url, title, description, engine, "
            "captured_at, pushed_at, digest_id, event_id, sentiment_score, "
            "sentiment_label "
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
                event_id=r[9] or "", sentiment_score=float(r[10] or 0.0),
                sentiment_label=r[11] or "",
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
            "binding_kind", "binding_id",
        ]
        d = dict(zip(cols, row))
        d["enabled"] = bool(d["enabled"])
        return Subscription(**d)
