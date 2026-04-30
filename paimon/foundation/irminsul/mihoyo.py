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
class MihoyoCharacter:
    game: str
    uid: str
    avatar_id: str
    name: str = ""
    element: str = ""
    rarity: int = 4
    level: int = 1
    constellation: int = 0
    fetter: int = 0
    weapon: dict = field(default_factory=dict)   # {name, level, affix, rarity}
    relics: list = field(default_factory=list)
    icon_url: str = ""
    scan_ts: float = 0.0
    raw: dict = field(default_factory=dict)


@dataclass
class MihoyoGacha:
    id: str
    uid: str
    gacha_type: str                 # gs:301/302/200/100/500 sr:1/2/11/12 zzz:1/2/3/5
    game: str = "gs"
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
        await self._db.execute("DELETE FROM mihoyo_gacha WHERE game=? AND uid=?", (game, uid))
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
        """批量 insert（id 唯一 → 重复忽略）。返回**真实新增**条数（不含被 IGNORE 跳过的）。"""
        if not items:
            return 0
        added = 0
        skipped = 0
        for it in items:
            try:
                cur = await self._db.execute(
                    "INSERT OR IGNORE INTO mihoyo_gacha "
                    "(id, game, uid, gacha_type, item_id, item_type, name, "
                    " rank_type, time, time_ts, raw_json) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        it.id, it.game, it.uid, it.gacha_type,
                        it.item_id, it.item_type, it.name,
                        it.rank_type, it.time, it.time_ts,
                        json.dumps(it.raw or {}, ensure_ascii=False),
                    ),
                )
                # aiosqlite 的 cursor.rowcount：真插入 1；IGNORE 跳过 0
                if cur.rowcount > 0:
                    added += 1
                else:
                    skipped += 1
            except Exception as e:
                logger.warning("[世界树] mihoyo_gacha insert 失败 id={}: {}", it.id, e)
        await self._db.commit()
        if skipped:
            logger.info(
                "[世界树] {}·mihoyo_gacha insert 新增 {} 条（跳过已存在 {} 条）",
                actor, added, skipped,
            )
        else:
            logger.info("[世界树] {}·mihoyo_gacha insert 新增 {} 条", actor, added)
        return added

    async def gacha_max_id(self, game: str, uid: str, gacha_type: str) -> str:
        async with self._db.execute(
            "SELECT MAX(id) FROM mihoyo_gacha WHERE game=? AND uid=? AND gacha_type=?",
            (game, uid, gacha_type),
        ) as cur:
            row = await cur.fetchone()
        return (row[0] or "") if row else ""

    async def gacha_list(
        self, game: str, uid: str, gacha_type: str, *, limit: int = 500,
    ) -> list[MihoyoGacha]:
        async with self._db.execute(
            "SELECT id, game, uid, gacha_type, item_id, item_type, name, "
            " rank_type, time, time_ts, raw_json "
            "FROM mihoyo_gacha WHERE game=? AND uid=? AND gacha_type=? "
            "ORDER BY time_ts DESC LIMIT ?",
            (game, uid, gacha_type, limit),
        ) as cur:
            rows = await cur.fetchall()
        return [
            MihoyoGacha(
                id=r[0], game=r[1], uid=r[2], gacha_type=r[3],
                item_id=r[4], item_type=r[5], name=r[6], rank_type=r[7],
                time=r[8], time_ts=r[9], raw=self._loads(r[10], {}),
            )
            for r in rows
        ]

    # ---------- character ----------

    async def character_upsert(
        self, items: list[MihoyoCharacter], *, actor: str,
    ) -> int:
        """批量 upsert 角色。PK=(game, uid, avatar_id) 保证幂等。"""
        if not items:
            return 0
        for c in items:
            await self._db.execute(
                "INSERT INTO mihoyo_character "
                "(game, uid, avatar_id, name, element, rarity, level, "
                " constellation, fetter, weapon_json, relics_json, "
                " icon_url, scan_ts, raw_json) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?) "
                "ON CONFLICT(game, uid, avatar_id) DO UPDATE SET "
                " name = excluded.name, element = excluded.element, "
                " rarity = excluded.rarity, level = excluded.level, "
                " constellation = excluded.constellation, fetter = excluded.fetter, "
                " weapon_json = excluded.weapon_json, relics_json = excluded.relics_json, "
                " icon_url = excluded.icon_url, scan_ts = excluded.scan_ts, "
                " raw_json = excluded.raw_json",
                (
                    c.game, c.uid, c.avatar_id, c.name, c.element,
                    c.rarity, c.level, c.constellation, c.fetter,
                    json.dumps(c.weapon or {}, ensure_ascii=False),
                    json.dumps(c.relics or [], ensure_ascii=False),
                    c.icon_url, c.scan_ts,
                    json.dumps(c.raw or {}, ensure_ascii=False),
                ),
            )
        await self._db.commit()
        logger.info("[世界树] {}·mihoyo_character upsert {} 个角色", actor, len(items))
        return len(items)

    async def character_list(self, game: str, uid: str) -> list[MihoyoCharacter]:
        async with self._db.execute(
            "SELECT game, uid, avatar_id, name, element, rarity, level, "
            " constellation, fetter, weapon_json, relics_json, "
            " icon_url, scan_ts, raw_json "
            "FROM mihoyo_character WHERE game=? AND uid=? "
            "ORDER BY rarity DESC, level DESC",
            (game, uid),
        ) as cur:
            rows = await cur.fetchall()
        return [
            MihoyoCharacter(
                game=r[0], uid=r[1], avatar_id=r[2], name=r[3], element=r[4],
                rarity=r[5], level=r[6], constellation=r[7], fetter=r[8],
                weapon=self._loads(r[9], {}),
                relics=self._loads(r[10], []),
                icon_url=r[11], scan_ts=r[12],
                raw=self._loads(r[13], {}),
            )
            for r in rows
        ]

    async def gacha_stats(self, game: str, uid: str, gacha_type: str) -> dict[str, Any]:
        """抽卡统计：总数、最高级数、保底计数、次级数、历次最高级列表。

        三游戏的 rank 体系不同：GS/SR 最高 5 星、次级 4 星；ZZZ S 级=4、A 级=3。
        以"最高级 / 次级"语义统一，对外字段名仍叫 count_5/pity_5 保持兼容。
        """
        items = await self.gacha_list(game, uid, gacha_type, limit=10000)
        # DB 按 time_ts DESC 返回 → 反转成时间升序，便于逻辑直观
        items_asc = list(reversed(items))
        total = len(items_asc)
        top_rank = 4 if game == "zzz" else 5    # ZZZ S 级 = 4
        sec_rank = 3 if game == "zzz" else 4
        fives = [i for i in items_asc if i.rank_type == top_rank]
        fours = [i for i in items_asc if i.rank_type == sec_rank]
        # 大保底：自最后一个最高级之后抽了多少
        last_five_idx = -1
        for idx, it in enumerate(items_asc):
            if it.rank_type == top_rank:
                last_five_idx = idx
        pity_5 = total - 1 - last_five_idx if last_five_idx >= 0 else total
        # 次级保底
        last_four_idx = -1
        for idx, it in enumerate(items_asc):
            if it.rank_type == sec_rank:
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
