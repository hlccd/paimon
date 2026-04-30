"""米哈游账号数据域 —— 世界树域 8.7

唯一写入者：水神
读取者：水神（业务流程）、WebUI /game 面板
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any

import aiosqlite
from loguru import logger


# ============ dataclasses ============


@dataclass
class MihoyoAccount:
    game: str                        # gs | sr | zzz
    uid: str
    mys_id: str = ""
    cookie: str = ""
    stoken: str = ""
    fp: str = ""
    device_id: str = ""
    device_info: str = ""
    authkey: str = ""
    authkey_ts: float = 0.0
    note: str = ""
    added_date: str = ""
    last_sign_at: float = 0.0
    enabled: bool = True


@dataclass
class MihoyoNote:
    game: str
    uid: str
    scan_ts: float = 0.0
    current_resin: int = 0
    max_resin: int = 160
    resin_full_ts: float = 0.0
    finished_tasks: int = 0
    total_tasks: int = 4
    daily_reward: int = 0
    remain_discount: int = 3
    current_expedition: int = 0
    max_expedition: int = 5
    expeditions: list[dict] = field(default_factory=list)
    transformer_ready: bool = False
    raw: dict = field(default_factory=dict)


@dataclass
class MihoyoAbyss:
    game: str
    uid: str
    abyss_type: str                 # spiral | poetry
    schedule_id: str
    scan_ts: float = 0.0
    max_floor: str = ""
    total_star: int = 0
    total_battle: int = 0
    total_win: int = 0
    start_time: str = ""
    end_time: str = ""
    raw: dict = field(default_factory=dict)


@dataclass
class MihoyoGacha:
    id: str
    uid: str
    gacha_type: str                 # 301/302/200/100/500
    item_id: str = ""
    item_type: str = ""
    name: str = ""
    rank_type: int = 3
    time: str = ""
    time_ts: float = 0.0
    raw: dict = field(default_factory=dict)


# ============ Repo ============


class MihoyoRepo:
    def __init__(self, db: aiosqlite.Connection):
        self._db = db

    # ---------- account CRUD ----------

    async def account_upsert(self, acc: MihoyoAccount, *, actor: str) -> None:
        await self._db.execute(
            "INSERT INTO mihoyo_account "
            "(game, uid, mys_id, cookie, stoken, fp, device_id, device_info, "
            " authkey, authkey_ts, note, added_date, last_sign_at, enabled) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?) "
            "ON CONFLICT(game, uid) DO UPDATE SET "
            " mys_id=excluded.mys_id, cookie=excluded.cookie, stoken=excluded.stoken, "
            " fp=excluded.fp, device_id=excluded.device_id, device_info=excluded.device_info, "
            " authkey=CASE WHEN excluded.authkey != '' THEN excluded.authkey ELSE mihoyo_account.authkey END, "
            " authkey_ts=CASE WHEN excluded.authkey != '' THEN excluded.authkey_ts ELSE mihoyo_account.authkey_ts END, "
            " note=excluded.note, last_sign_at=excluded.last_sign_at, enabled=excluded.enabled",
            (
                acc.game, acc.uid, acc.mys_id, acc.cookie, acc.stoken, acc.fp,
                acc.device_id, acc.device_info, acc.authkey, acc.authkey_ts,
                acc.note, acc.added_date, acc.last_sign_at, 1 if acc.enabled else 0,
            ),
        )
        await self._db.commit()
        logger.info("[世界树] {}·mihoyo_account upsert {}/{}", actor, acc.game, acc.uid)

    async def account_remove(self, game: str, uid: str, *, actor: str) -> bool:
        async with self._db.execute(
            "DELETE FROM mihoyo_account WHERE game=? AND uid=?", (game, uid),
        ) as cur:
            n = cur.rowcount
        # 级联清空便笺/深渊/抽卡
        await self._db.execute("DELETE FROM mihoyo_note WHERE game=? AND uid=?", (game, uid))
        await self._db.execute("DELETE FROM mihoyo_abyss WHERE game=? AND uid=?", (game, uid))
        await self._db.execute("DELETE FROM mihoyo_gacha WHERE uid=?", (uid,))
        await self._db.commit()
        if n > 0:
            logger.info("[世界树] {}·mihoyo_account 删除 {}/{}", actor, game, uid)
        return n > 0

    async def account_get(self, game: str, uid: str) -> MihoyoAccount | None:
        async with self._db.execute(
            "SELECT game, uid, mys_id, cookie, stoken, fp, device_id, device_info, "
            " authkey, authkey_ts, note, added_date, last_sign_at, enabled "
            "FROM mihoyo_account WHERE game=? AND uid=?",
            (game, uid),
        ) as cur:
            row = await cur.fetchone()
        if not row:
            return None
        return MihoyoAccount(
            game=row[0], uid=row[1], mys_id=row[2], cookie=row[3], stoken=row[4],
            fp=row[5], device_id=row[6], device_info=row[7],
            authkey=row[8], authkey_ts=row[9], note=row[10],
            added_date=row[11], last_sign_at=row[12], enabled=bool(row[13]),
        )

    async def account_list(self, *, game: str | None = None) -> list[MihoyoAccount]:
        sql = (
            "SELECT game, uid, mys_id, cookie, stoken, fp, device_id, device_info, "
            " authkey, authkey_ts, note, added_date, last_sign_at, enabled "
            "FROM mihoyo_account"
        )
        args: tuple = ()
        if game:
            sql += " WHERE game=?"
            args = (game,)
        sql += " ORDER BY added_date DESC, game, uid"
        async with self._db.execute(sql, args) as cur:
            rows = await cur.fetchall()
        return [
            MihoyoAccount(
                game=r[0], uid=r[1], mys_id=r[2], cookie=r[3], stoken=r[4],
                fp=r[5], device_id=r[6], device_info=r[7],
                authkey=r[8], authkey_ts=r[9], note=r[10],
                added_date=r[11], last_sign_at=r[12], enabled=bool(r[13]),
            )
            for r in rows
        ]

    async def account_update_authkey(
        self, uid: str, authkey: str, *, game: str = "gs", actor: str,
    ) -> None:
        await self._db.execute(
            "UPDATE mihoyo_account SET authkey=?, authkey_ts=? WHERE game=? AND uid=?",
            (authkey, time.time(), game, uid),
        )
        await self._db.commit()
        logger.info("[世界树] {}·mihoyo_account authkey 更新 {}/{}", actor, game, uid)

    async def account_set_sign_time(self, game: str, uid: str, ts: float) -> None:
        await self._db.execute(
            "UPDATE mihoyo_account SET last_sign_at=? WHERE game=? AND uid=?",
            (ts, game, uid),
        )
        await self._db.commit()

    # ---------- note ----------

    async def note_upsert(self, n: MihoyoNote, *, actor: str) -> None:
        await self._db.execute(
            "INSERT INTO mihoyo_note "
            "(game, uid, scan_ts, current_resin, max_resin, resin_full_ts, "
            " finished_tasks, total_tasks, daily_reward, remain_discount, "
            " current_expedition, max_expedition, expeditions_json, "
            " transformer_ready, raw_json) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?) "
            "ON CONFLICT(game, uid) DO UPDATE SET "
            " scan_ts=excluded.scan_ts, current_resin=excluded.current_resin, "
            " max_resin=excluded.max_resin, resin_full_ts=excluded.resin_full_ts, "
            " finished_tasks=excluded.finished_tasks, total_tasks=excluded.total_tasks, "
            " daily_reward=excluded.daily_reward, remain_discount=excluded.remain_discount, "
            " current_expedition=excluded.current_expedition, max_expedition=excluded.max_expedition, "
            " expeditions_json=excluded.expeditions_json, transformer_ready=excluded.transformer_ready, "
            " raw_json=excluded.raw_json",
            (
                n.game, n.uid, n.scan_ts, n.current_resin, n.max_resin, n.resin_full_ts,
                n.finished_tasks, n.total_tasks, n.daily_reward, n.remain_discount,
                n.current_expedition, n.max_expedition,
                json.dumps(n.expeditions or [], ensure_ascii=False),
                1 if n.transformer_ready else 0,
                json.dumps(n.raw or {}, ensure_ascii=False),
            ),
        )
        await self._db.commit()
        logger.debug("[世界树] {}·mihoyo_note upsert {}/{} resin={}/{}",
                     actor, n.game, n.uid, n.current_resin, n.max_resin)

    async def note_get(self, game: str, uid: str) -> MihoyoNote | None:
        async with self._db.execute(
            "SELECT game, uid, scan_ts, current_resin, max_resin, resin_full_ts, "
            " finished_tasks, total_tasks, daily_reward, remain_discount, "
            " current_expedition, max_expedition, expeditions_json, "
            " transformer_ready, raw_json "
            "FROM mihoyo_note WHERE game=? AND uid=?",
            (game, uid),
        ) as cur:
            row = await cur.fetchone()
        if not row:
            return None
        return MihoyoNote(
            game=row[0], uid=row[1], scan_ts=row[2], current_resin=row[3],
            max_resin=row[4], resin_full_ts=row[5], finished_tasks=row[6],
            total_tasks=row[7], daily_reward=row[8], remain_discount=row[9],
            current_expedition=row[10], max_expedition=row[11],
            expeditions=self._loads(row[12], []),
            transformer_ready=bool(row[13]),
            raw=self._loads(row[14], {}),
        )

    async def note_list(self) -> list[MihoyoNote]:
        async with self._db.execute(
            "SELECT game, uid, scan_ts, current_resin, max_resin, resin_full_ts, "
            " finished_tasks, total_tasks, daily_reward, remain_discount, "
            " current_expedition, max_expedition, expeditions_json, "
            " transformer_ready, raw_json "
            "FROM mihoyo_note ORDER BY scan_ts DESC",
        ) as cur:
            rows = await cur.fetchall()
        return [
            MihoyoNote(
                game=r[0], uid=r[1], scan_ts=r[2], current_resin=r[3],
                max_resin=r[4], resin_full_ts=r[5], finished_tasks=r[6],
                total_tasks=r[7], daily_reward=r[8], remain_discount=r[9],
                current_expedition=r[10], max_expedition=r[11],
                expeditions=self._loads(r[12], []),
                transformer_ready=bool(r[13]),
                raw=self._loads(r[14], {}),
            )
            for r in rows
        ]

    # ---------- abyss ----------

    async def abyss_upsert(self, a: MihoyoAbyss, *, actor: str) -> None:
        await self._db.execute(
            "INSERT INTO mihoyo_abyss "
            "(game, uid, abyss_type, schedule_id, scan_ts, max_floor, "
            " total_star, total_battle, total_win, start_time, end_time, raw_json) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?) "
            "ON CONFLICT(game, uid, abyss_type, schedule_id) DO UPDATE SET "
            " scan_ts=excluded.scan_ts, max_floor=excluded.max_floor, "
            " total_star=excluded.total_star, total_battle=excluded.total_battle, "
            " total_win=excluded.total_win, start_time=excluded.start_time, "
            " end_time=excluded.end_time, raw_json=excluded.raw_json",
            (
                a.game, a.uid, a.abyss_type, a.schedule_id, a.scan_ts,
                a.max_floor, a.total_star, a.total_battle, a.total_win,
                a.start_time, a.end_time,
                json.dumps(a.raw or {}, ensure_ascii=False),
            ),
        )
        await self._db.commit()

    async def abyss_latest(
        self, game: str, uid: str, abyss_type: str,
    ) -> MihoyoAbyss | None:
        async with self._db.execute(
            "SELECT game, uid, abyss_type, schedule_id, scan_ts, max_floor, "
            " total_star, total_battle, total_win, start_time, end_time, raw_json "
            "FROM mihoyo_abyss WHERE game=? AND uid=? AND abyss_type=? "
            "ORDER BY schedule_id DESC LIMIT 1",
            (game, uid, abyss_type),
        ) as cur:
            row = await cur.fetchone()
        if not row:
            return None
        return MihoyoAbyss(
            game=row[0], uid=row[1], abyss_type=row[2], schedule_id=row[3],
            scan_ts=row[4], max_floor=row[5], total_star=row[6],
            total_battle=row[7], total_win=row[8],
            start_time=row[9], end_time=row[10],
            raw=self._loads(row[11], {}),
        )

    # ---------- gacha ----------

    async def gacha_insert(self, items: list[MihoyoGacha], *, actor: str) -> int:
        """批量 insert（id 唯一 → 重复忽略）。返回真实新增条数。"""
        if not items:
            return 0
        n = 0
        for it in items:
            try:
                await self._db.execute(
                    "INSERT OR IGNORE INTO mihoyo_gacha "
                    "(id, uid, gacha_type, item_id, item_type, name, "
                    " rank_type, time, time_ts, raw_json) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?)",
                    (
                        it.id, it.uid, it.gacha_type, it.item_id, it.item_type,
                        it.name, it.rank_type, it.time, it.time_ts,
                        json.dumps(it.raw or {}, ensure_ascii=False),
                    ),
                )
                n += 1
            except Exception as e:
                logger.warning("[世界树] mihoyo_gacha insert 失败 id={}: {}", it.id, e)
        await self._db.commit()
        logger.info("[世界树] {}·mihoyo_gacha insert {} 条", actor, n)
        return n

    async def gacha_max_id(self, uid: str, gacha_type: str) -> str:
        async with self._db.execute(
            "SELECT MAX(id) FROM mihoyo_gacha WHERE uid=? AND gacha_type=?",
            (uid, gacha_type),
        ) as cur:
            row = await cur.fetchone()
        return (row[0] or "") if row else ""

    async def gacha_list(
        self, uid: str, gacha_type: str, *, limit: int = 500,
    ) -> list[MihoyoGacha]:
        async with self._db.execute(
            "SELECT id, uid, gacha_type, item_id, item_type, name, "
            " rank_type, time, time_ts, raw_json "
            "FROM mihoyo_gacha WHERE uid=? AND gacha_type=? "
            "ORDER BY time_ts DESC LIMIT ?",
            (uid, gacha_type, limit),
        ) as cur:
            rows = await cur.fetchall()
        return [
            MihoyoGacha(
                id=r[0], uid=r[1], gacha_type=r[2], item_id=r[3],
                item_type=r[4], name=r[5], rank_type=r[6],
                time=r[7], time_ts=r[8], raw=self._loads(r[9], {}),
            )
            for r in rows
        ]

    async def gacha_stats(self, uid: str, gacha_type: str) -> dict[str, Any]:
        """抽卡统计：总数、5 星数、自上个 5 星以来的小保底计数、4 星数、历次 5 星列表。"""
        items = await self.gacha_list(uid, gacha_type, limit=10000)
        # DB 按 time_ts DESC 返回 → 反转成时间升序，便于逻辑直观
        items_asc = list(reversed(items))
        total = len(items_asc)
        fives = [i for i in items_asc if i.rank_type == 5]
        fours = [i for i in items_asc if i.rank_type == 4]
        # 小保底：自最后一个 5 星之后抽了多少
        last_five_idx = -1
        for idx, it in enumerate(items_asc):
            if it.rank_type == 5:
                last_five_idx = idx
        pity_5 = total - 1 - last_five_idx if last_five_idx >= 0 else total
        # 4 星小保底
        last_four_idx = -1
        for idx, it in enumerate(items_asc):
            if it.rank_type == 4:
                last_four_idx = idx
        pity_4 = total - 1 - last_four_idx if last_four_idx >= 0 else total
        return {
            "total": total,
            "count_5": len(fives),
            "count_4": len(fours),
            "pity_5": pity_5,
            "pity_4": pity_4,
            "avg_pity_5": round(total / len(fives), 1) if fives else 0,
            "fives": [
                {"name": f.name, "time": f.time, "item_type": f.item_type}
                for f in reversed(fives)   # 新 → 旧
            ],
        }

    # ---------- util ----------

    @staticmethod
    def _loads(raw: Any, default: Any) -> Any:
        if not raw:
            return default
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return default
