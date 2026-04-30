"""用户关注股数据域 —— 世界树域 8.6

与 `dividend.py` 的岩神自动 watchlist 解耦：
- 本表 user_watchlist 是用户手动添加的自选股（任意数量、无行业均衡约束）
- 配套 user_watchlist_price 存每日 close/PE/PB，首次 add 拉 3 年历史、后续日更追加

唯一写入者：岩神（daily scan 拉价）+ WebUI `/api/wealth/user_watchlist/*`（用户增删改）
读取者：岩神（波动检测）、WebUI /wealth 面板
"""
from __future__ import annotations

from dataclasses import dataclass

import aiosqlite
from loguru import logger


@dataclass
class UserWatchEntry:
    stock_code: str
    stock_name: str = ""
    note: str = ""
    added_date: str = ""
    alert_pct: float = 3.0


@dataclass
class UserWatchPrice:
    stock_code: str
    date: str
    close: float = 0.0
    change_pct: float = 0.0
    pe: float = 0.0
    pb: float = 0.0
    volume: float = 0.0


class UserWatchlistRepo:
    def __init__(self, db: aiosqlite.Connection):
        self._db = db

    # ---------- watchlist CRUD ----------

    async def add(self, entry: UserWatchEntry, *, actor: str) -> bool:
        """添加关注。已存在则返回 False，新增返回 True。"""
        async with self._db.execute(
            "SELECT 1 FROM user_watchlist WHERE stock_code = ?",
            (entry.stock_code,),
        ) as cur:
            if await cur.fetchone():
                return False
        await self._db.execute(
            "INSERT INTO user_watchlist (stock_code, stock_name, note, added_date, alert_pct) "
            "VALUES (?,?,?,?,?)",
            (entry.stock_code, entry.stock_name, entry.note, entry.added_date, entry.alert_pct),
        )
        await self._db.commit()
        logger.info("[世界树] {}·user_watchlist 新增 {} ({})", actor, entry.stock_code, entry.stock_name)
        return True

    async def remove(self, stock_code: str, *, actor: str) -> bool:
        async with self._db.execute(
            "DELETE FROM user_watchlist WHERE stock_code = ?",
            (stock_code,),
        ) as cur:
            n = cur.rowcount
        await self._db.execute(
            "DELETE FROM user_watchlist_price WHERE stock_code = ?",
            (stock_code,),
        )
        await self._db.commit()
        if n > 0:
            logger.info("[世界树] {}·user_watchlist 删除 {}", actor, stock_code)
        return n > 0

    async def update(
        self, stock_code: str, *,
        note: str | None = None, alert_pct: float | None = None,
        stock_name: str | None = None,
        actor: str,
    ) -> bool:
        fields = []
        values: list = []
        if note is not None:
            fields.append("note = ?"); values.append(note)
        if alert_pct is not None:
            fields.append("alert_pct = ?"); values.append(alert_pct)
        if stock_name is not None:
            fields.append("stock_name = ?"); values.append(stock_name)
        if not fields:
            return False
        values.append(stock_code)
        async with self._db.execute(
            f"UPDATE user_watchlist SET {', '.join(fields)} WHERE stock_code = ?",
            tuple(values),
        ) as cur:
            n = cur.rowcount
        await self._db.commit()
        if n > 0:
            logger.info("[世界树] {}·user_watchlist 更新 {}", actor, stock_code)
        return n > 0

    async def list(self) -> list[UserWatchEntry]:
        async with self._db.execute(
            "SELECT stock_code, stock_name, note, added_date, alert_pct "
            "FROM user_watchlist ORDER BY added_date DESC, stock_code",
        ) as cur:
            rows = await cur.fetchall()
        return [
            UserWatchEntry(
                stock_code=r[0], stock_name=r[1], note=r[2],
                added_date=r[3], alert_pct=r[4],
            )
            for r in rows
        ]

    async def get(self, stock_code: str) -> UserWatchEntry | None:
        async with self._db.execute(
            "SELECT stock_code, stock_name, note, added_date, alert_pct "
            "FROM user_watchlist WHERE stock_code = ?",
            (stock_code,),
        ) as cur:
            row = await cur.fetchone()
        if not row:
            return None
        return UserWatchEntry(
            stock_code=row[0], stock_name=row[1], note=row[2],
            added_date=row[3], alert_pct=row[4],
        )

    async def codes(self) -> list[str]:
        async with self._db.execute("SELECT stock_code FROM user_watchlist") as cur:
            rows = await cur.fetchall()
        return [r[0] for r in rows]

    # ---------- price history ----------

    async def price_upsert(self, rows: list[UserWatchPrice], *, actor: str) -> int:
        """批量 upsert 价格。(stock_code, date) PRIMARY KEY 保证幂等。"""
        if not rows:
            return 0
        for p in rows:
            await self._db.execute(
                "INSERT INTO user_watchlist_price "
                "(stock_code, date, close, change_pct, pe, pb, volume) "
                "VALUES (?,?,?,?,?,?,?) "
                "ON CONFLICT(stock_code, date) DO UPDATE SET "
                " close = excluded.close, change_pct = excluded.change_pct, "
                " pe = excluded.pe, pb = excluded.pb, volume = excluded.volume",
                (p.stock_code, p.date, p.close, p.change_pct, p.pe, p.pb, p.volume),
            )
        await self._db.commit()
        logger.debug("[世界树] {}·user_price upsert {} 条", actor, len(rows))
        return len(rows)

    async def price_latest(self, stock_code: str) -> UserWatchPrice | None:
        async with self._db.execute(
            "SELECT stock_code, date, close, change_pct, pe, pb, volume "
            "FROM user_watchlist_price WHERE stock_code = ? "
            "ORDER BY date DESC LIMIT 1",
            (stock_code,),
        ) as cur:
            row = await cur.fetchone()
        if not row:
            return None
        return UserWatchPrice(
            stock_code=row[0], date=row[1], close=row[2],
            change_pct=row[3], pe=row[4], pb=row[5], volume=row[6],
        )

    async def price_recent(self, stock_code: str, days: int = 30) -> list[UserWatchPrice]:
        """取近 N 个交易日（按 date 升序，画 sparkline 用）。"""
        async with self._db.execute(
            "SELECT stock_code, date, close, change_pct, pe, pb, volume "
            "FROM user_watchlist_price WHERE stock_code = ? "
            "ORDER BY date DESC LIMIT ?",
            (stock_code, days),
        ) as cur:
            rows = await cur.fetchall()
        return [
            UserWatchPrice(
                stock_code=r[0], date=r[1], close=r[2],
                change_pct=r[3], pe=r[4], pb=r[5], volume=r[6],
            )
            for r in reversed(rows)  # 返回升序，便于前端直接画
        ]

    async def price_series(self, stock_code: str, column: str) -> list[float]:
        """取全量某列数值序列（算估值分位用）。column ∈ 'pe' | 'pb' | 'close'。"""
        if column not in ("pe", "pb", "close"):
            raise ValueError(f"非法 column: {column}")
        async with self._db.execute(
            f"SELECT {column} FROM user_watchlist_price "
            f"WHERE stock_code = ? AND {column} > 0 "
            "ORDER BY date ASC",
            (stock_code,),
        ) as cur:
            rows = await cur.fetchall()
        return [float(r[0]) for r in rows if r[0] is not None]

    async def price_max_date(self, stock_code: str) -> str | None:
        """最新已入库日期，决定 daily 抓取从哪天起。"""
        async with self._db.execute(
            "SELECT MAX(date) FROM user_watchlist_price WHERE stock_code = ?",
            (stock_code,),
        ) as cur:
            row = await cur.fetchone()
        return row[0] if row and row[0] else None
