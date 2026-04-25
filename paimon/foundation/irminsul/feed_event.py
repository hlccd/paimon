"""事件聚类数据域 —— 域 11.5（风神 L1 舆情）

唯一写入者：风神 EventClusterer（订阅采集时 upsert）
读取者：风神（聚类候选 / 推送决策）、WebUI 舆情面板（事件列表 / 时间线 / 情感）

职责：
- feed_events 表：事件主体（标题/摘要/严重度/情感/实体/时间线/信源/计数）
- 跨批次合并语义：聚类 LLM 决定 new/merge；merge 通过 update + item_count_inc 累加
- 升级冷却所需字段：last_pushed_at / last_severity / pushed_count

docs/archons/venti.md §L1 事件级舆情监测
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4

import aiosqlite
from loguru import logger


@dataclass
class FeedEvent:
    id: str = ""
    subscription_id: str = ""
    title: str = ""
    summary: str = ""
    entities: list[str] = field(default_factory=list)
    timeline: list[dict] = field(default_factory=list)        # [{ts, point}]
    severity: str = "p3"                                       # p0/p1/p2/p3
    sentiment_score: float = 0.0
    sentiment_label: str = "neutral"
    item_count: int = 0
    first_seen_at: float = 0.0
    last_seen_at: float = 0.0
    last_pushed_at: float | None = None
    last_severity: str = ""
    pushed_count: int = 0
    sources: list[str] = field(default_factory=list)
    created_at: float = 0.0
    updated_at: float = 0.0


# 严重度排序：用于"是否升级"判定（数字越小越紧急）
_SEVERITY_RANK = {"p0": 0, "p1": 1, "p2": 2, "p3": 3, "": 4}


def is_severity_upgrade(old: str, new: str) -> bool:
    """判定 severity 是否提升。

    'p2' → 'p1' 视作升级；反向（p1 → p2）不算。空字符串视作"无历史"，
    新事件首次推送也算升级。
    """
    return _SEVERITY_RANK.get(new, 4) < _SEVERITY_RANK.get(old, 4)


class FeedEventRepo:
    def __init__(self, db: aiosqlite.Connection):
        self._db = db

    # ---------- CRUD ----------

    async def create(self, event: FeedEvent, *, actor: str) -> str:
        """新建事件；id 为空时自动生成 12 位 hex。返回 id。"""
        if not event.id:
            event.id = uuid4().hex[:12]
        now = time.time()
        if not event.created_at:
            event.created_at = now
        event.updated_at = now
        if not event.first_seen_at:
            event.first_seen_at = now
        if not event.last_seen_at:
            event.last_seen_at = now

        await self._db.execute(
            "INSERT INTO feed_events ("
            "id, subscription_id, title, summary, entities_json, timeline_json, "
            "severity, sentiment_score, sentiment_label, item_count, "
            "first_seen_at, last_seen_at, last_pushed_at, last_severity, "
            "pushed_count, sources_json, created_at, updated_at"
            ") VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                event.id, event.subscription_id, event.title, event.summary,
                json.dumps(event.entities, ensure_ascii=False),
                json.dumps(event.timeline, ensure_ascii=False),
                event.severity, float(event.sentiment_score), event.sentiment_label,
                event.item_count,
                event.first_seen_at, event.last_seen_at,
                event.last_pushed_at, event.last_severity,
                event.pushed_count,
                json.dumps(event.sources, ensure_ascii=False),
                event.created_at, event.updated_at,
            ),
        )
        await self._db.commit()
        logger.info(
            "[世界树] {}·创建事件 {} sub={} severity={} title='{}'",
            actor, event.id, event.subscription_id,
            event.severity, event.title[:30],
        )
        return event.id

    async def get(self, event_id: str) -> FeedEvent | None:
        async with self._db.execute(
            "SELECT id, subscription_id, title, summary, entities_json, "
            "timeline_json, severity, sentiment_score, sentiment_label, "
            "item_count, first_seen_at, last_seen_at, last_pushed_at, "
            "last_severity, pushed_count, sources_json, created_at, updated_at "
            "FROM feed_events WHERE id = ?",
            (event_id,),
        ) as cur:
            row = await cur.fetchone()
        return self._row_to_event(row) if row else None

    async def update(
        self, event_id: str, *, actor: str,
        item_count_inc: int = 0,
        pushed_count_inc: int = 0,
        **fields,
    ) -> bool:
        """更新事件字段。

        - item_count_inc / pushed_count_inc 为增量（非赋值）
        - entities / timeline / sources 走 list 入参，函数内 JSON 序列化
        - 调用方未传 updated_at 时自动 set 为 now
        """
        if not fields and item_count_inc == 0 and pushed_count_inc == 0:
            return False

        sets: list[str] = []
        params: list[Any] = []

        # list/dict 字段需序列化
        for key, val in list(fields.items()):
            if key == "entities":
                fields["entities_json"] = json.dumps(val, ensure_ascii=False)
                fields.pop("entities")
            elif key == "timeline":
                fields["timeline_json"] = json.dumps(val, ensure_ascii=False)
                fields.pop("timeline")
            elif key == "sources":
                fields["sources_json"] = json.dumps(val, ensure_ascii=False)
                fields.pop("sources")

        for k, v in fields.items():
            sets.append(f"{k} = ?")
            params.append(v)

        if item_count_inc:
            sets.append("item_count = item_count + ?")
            params.append(item_count_inc)
        if pushed_count_inc:
            sets.append("pushed_count = pushed_count + ?")
            params.append(pushed_count_inc)

        # 自动更新 updated_at
        if "updated_at" not in fields:
            sets.append("updated_at = ?")
            params.append(time.time())

        params.append(event_id)
        async with self._db.execute(
            f"UPDATE feed_events SET {', '.join(sets)} WHERE id = ?",
            params,
        ) as cur:
            ok = cur.rowcount > 0
        await self._db.commit()
        if ok:
            logger.info(
                "[世界树] {}·更新事件 {} ({} 字段, item+={}, push+={})",
                actor, event_id, len(fields), item_count_inc, pushed_count_inc,
            )
        return ok

    async def list(
        self, *,
        sub_id: str | None = None,
        since: float | None = None,
        severity: str | None = None,
        limit: int = 100,
    ) -> list[FeedEvent]:
        """按订阅 / 时间窗 / 严重度过滤，按 last_seen_at 倒序。"""
        clauses: list[str] = []
        params: list[Any] = []
        if sub_id is not None:
            clauses.append("subscription_id = ?"); params.append(sub_id)
        if since is not None:
            clauses.append("last_seen_at >= ?"); params.append(since)
        if severity is not None:
            clauses.append("severity = ?"); params.append(severity)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""

        sql = (
            "SELECT id, subscription_id, title, summary, entities_json, "
            "timeline_json, severity, sentiment_score, sentiment_label, "
            "item_count, first_seen_at, last_seen_at, last_pushed_at, "
            "last_severity, pushed_count, sources_json, created_at, updated_at "
            f"FROM feed_events {where} ORDER BY last_seen_at DESC LIMIT ?"
        )
        params.append(limit)
        async with self._db.execute(sql, tuple(params)) as cur:
            rows = await cur.fetchall()
        return [self._row_to_event(r) for r in rows]

    async def count(
        self, *,
        sub_id: str | None = None,
        since: float | None = None,
        severity: str | None = None,
    ) -> int:
        clauses: list[str] = []
        params: list[Any] = []
        if sub_id is not None:
            clauses.append("subscription_id = ?"); params.append(sub_id)
        if since is not None:
            clauses.append("last_seen_at >= ?"); params.append(since)
        if severity is not None:
            clauses.append("severity = ?"); params.append(severity)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        async with self._db.execute(
            f"SELECT COUNT(*) FROM feed_events {where}", tuple(params),
        ) as cur:
            row = await cur.fetchone()
        return int(row[0]) if row else 0

    async def count_by_severity(
        self, *,
        since: float | None = None,
        sub_id: str | None = None,
    ) -> dict[str, int]:
        """返回 {p0:n, p1:n, p2:n, p3:n}。"""
        clauses: list[str] = []
        params: list[Any] = []
        if sub_id is not None:
            clauses.append("subscription_id = ?"); params.append(sub_id)
        if since is not None:
            clauses.append("last_seen_at >= ?"); params.append(since)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        async with self._db.execute(
            f"SELECT severity, COUNT(*) FROM feed_events {where} "
            "GROUP BY severity",
            tuple(params),
        ) as cur:
            rows = await cur.fetchall()
        result = {"p0": 0, "p1": 0, "p2": 0, "p3": 0}
        for sev, n in rows:
            if sev in result:
                result[sev] = int(n)
        return result

    async def timeline(
        self, *, days: int, sub_id: str | None = None,
    ) -> list[dict]:
        """按天聚合最近 N 天 feed_events。

        返回 [{date(YYYY-MM-DD), events, avg_sentiment, p0, p1, p2, p3}]，
        日期升序填充（即便某天 0 事件也返回）。

        - 时间桶用 last_seen_at 落桶（事件最近活跃的那天）
        - 跨订阅汇总；sub_id 给定时仅该订阅
        - 用 SQLite date(epoch, 'unixepoch', 'localtime') 切成本地日历日
        """
        if days < 1:
            days = 1
        if days > 365:
            days = 365
        cutoff = time.time() - days * 24 * 3600

        clauses = ["last_seen_at >= ?"]
        params: list[Any] = [cutoff]
        if sub_id:
            clauses.append("subscription_id = ?")
            params.append(sub_id)
        where = "WHERE " + " AND ".join(clauses)

        sql = (
            "SELECT date(last_seen_at, 'unixepoch', 'localtime') AS d, "
            "COUNT(*) AS n, "
            "AVG(sentiment_score) AS avg_s, "
            "SUM(CASE WHEN severity='p0' THEN 1 ELSE 0 END) AS p0, "
            "SUM(CASE WHEN severity='p1' THEN 1 ELSE 0 END) AS p1, "
            "SUM(CASE WHEN severity='p2' THEN 1 ELSE 0 END) AS p2, "
            "SUM(CASE WHEN severity='p3' THEN 1 ELSE 0 END) AS p3 "
            f"FROM feed_events {where} GROUP BY d ORDER BY d ASC"
        )
        async with self._db.execute(sql, tuple(params)) as cur:
            rows = await cur.fetchall()

        # 把数据填到完整的 days 列表（含空日，方便前端折线连续）
        from datetime import date, timedelta
        today = date.today()
        full: dict[str, dict] = {}
        for i in range(days):
            d_str = (today - timedelta(days=days - 1 - i)).isoformat()
            full[d_str] = {
                "date": d_str, "events": 0, "avg_sentiment": 0.0,
                "p0": 0, "p1": 0, "p2": 0, "p3": 0,
            }
        for r in rows:
            d_str = r[0]
            if d_str in full:
                full[d_str].update({
                    "events": int(r[1]) if r[1] else 0,
                    "avg_sentiment": float(r[2]) if r[2] is not None else 0.0,
                    "p0": int(r[3]) if r[3] else 0,
                    "p1": int(r[4]) if r[4] else 0,
                    "p2": int(r[5]) if r[5] else 0,
                    "p3": int(r[6]) if r[6] else 0,
                })
        return list(full.values())

    async def sources_top(
        self, *, days: int, limit: int = 10,
        sub_id: str | None = None,
    ) -> list[dict]:
        """近 N 天 feed_events.sources_json flatten 后按域名计数 Top。

        返回 [{domain, count}]（按 count 降序）。
        sources_json 是 list[str]，需在 Python 侧 flatten + count（SQLite 没原生 JSON 数组聚合）。
        """
        if days < 1:
            days = 1
        cutoff = time.time() - days * 24 * 3600
        clauses = ["last_seen_at >= ?"]
        params: list[Any] = [cutoff]
        if sub_id is not None:
            clauses.append("subscription_id = ?"); params.append(sub_id)
        where = " AND ".join(clauses)
        async with self._db.execute(
            f"SELECT sources_json FROM feed_events WHERE {where}",
            tuple(params),
        ) as cur:
            rows = await cur.fetchall()
        from collections import Counter
        counter: Counter = Counter()
        for r in rows:
            try:
                sources = json.loads(r[0] or "[]")
                if isinstance(sources, list):
                    for s in sources:
                        s_str = str(s).strip().lower()
                        if s_str:
                            counter[s_str] += 1
            except (json.JSONDecodeError, TypeError):
                continue
        return [
            {"domain": dom, "count": cnt}
            for dom, cnt in counter.most_common(limit)
        ]

    async def avg_sentiment(
        self, *,
        since: float | None = None,
        sub_id: str | None = None,
    ) -> float:
        """返回 since 之后所有事件 sentiment_score 的均值；无数据返 0.0。"""
        clauses: list[str] = []
        params: list[Any] = []
        if sub_id is not None:
            clauses.append("subscription_id = ?"); params.append(sub_id)
        if since is not None:
            clauses.append("last_seen_at >= ?"); params.append(since)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        async with self._db.execute(
            f"SELECT AVG(sentiment_score) FROM feed_events {where}",
            tuple(params),
        ) as cur:
            row = await cur.fetchone()
        return float(row[0]) if row and row[0] is not None else 0.0

    async def delete(self, event_id: str, *, actor: str) -> bool:
        async with self._db.execute(
            "DELETE FROM feed_events WHERE id = ?", (event_id,),
        ) as cur:
            ok = cur.rowcount > 0
        # feed_items.event_id 留着指向已删事件——查询时按 LEFT JOIN 容错
        await self._db.commit()
        if ok:
            logger.info("[世界树] {}·删除事件 {}", actor, event_id)
        return ok

    async def sweep_old(
        self, *, retention_seconds: float, actor: str,
    ) -> int:
        """清理 last_seen_at 早于 (now - retention_seconds) 的事件。"""
        cutoff = time.time() - retention_seconds
        async with self._db.execute(
            "DELETE FROM feed_events WHERE last_seen_at < ?", (cutoff,),
        ) as cur:
            n = cur.rowcount
        await self._db.commit()
        if n:
            logger.info(
                "[世界树] {}·清理过期事件 删除 {} 条 (cutoff={:.0f})",
                actor, n, cutoff,
            )
        return n

    # ---------- helpers ----------

    @staticmethod
    def _row_to_event(row: tuple) -> FeedEvent:
        try:
            entities = json.loads(row[4] or "[]")
        except (json.JSONDecodeError, TypeError):
            entities = []
        try:
            timeline = json.loads(row[5] or "[]")
        except (json.JSONDecodeError, TypeError):
            timeline = []
        try:
            sources = json.loads(row[15] or "[]")
        except (json.JSONDecodeError, TypeError):
            sources = []
        return FeedEvent(
            id=row[0], subscription_id=row[1],
            title=row[2], summary=row[3],
            entities=entities, timeline=timeline,
            severity=row[6], sentiment_score=row[7], sentiment_label=row[8],
            item_count=row[9],
            first_seen_at=row[10], last_seen_at=row[11],
            last_pushed_at=row[12], last_severity=row[13],
            pushed_count=row[14],
            sources=sources,
            created_at=row[16], updated_at=row[17],
        )
