"""水神·游戏 · 深渊 / 困难挑战 / 朔行连星 / 剧诗 mixin。"""
from __future__ import annotations

import asyncio
import json
import time
from datetime import date
from typing import TYPE_CHECKING, Any

from loguru import logger

from paimon.foundation.irminsul import (
    MihoyoAbyss, MihoyoAccount, MihoyoCharacter, MihoyoGacha, MihoyoNote,
)

if TYPE_CHECKING:
    from paimon.foundation.irminsul import Irminsul
    from paimon.foundation.march import MarchService


class _BattleMixin:
    async def collect_abyss(self, game: str, uid: str) -> MihoyoAbyss | None:
        if game != "gs":
            return None
        acc = await self._ir.mihoyo_account_get(game, uid)
        if not acc or not acc.cookie:
            return None
        try:
            data = await self._run_skill("spiral-abyss", {
                "uid": uid, "cookie": acc.cookie,
                "fp": acc.fp, "device_id": acc.device_id, "schedule": 1,
            })
        except Exception as e:
            logger.warning("[水神·游戏] 深渊抓取失败 {}/{}: {}", game, uid, e)
            return None
        if data.get("retcode") != 0:
            return None
        d = data.get("data") or {}
        a = MihoyoAbyss(
            game=game, uid=uid, abyss_type="spiral",
            schedule_id=str(d.get("schedule_id", "")),
            scan_ts=time.time(),
            max_floor=str(d.get("max_floor", "")),
            total_star=int(d.get("total_star", 0) or 0),
            total_battle=int(d.get("total_battle_times", 0) or 0),
            total_win=int(d.get("total_win_times", 0) or 0),
            start_time=str(d.get("start_time", "")),
            end_time=str(d.get("end_time", "")),
            raw=d,
        )
        await self._ir.mihoyo_abyss_upsert(a, actor="水神")
        return a

    async def collect_hard_challenge(self, game: str, uid: str) -> MihoyoAbyss | None:
        """幽境危战（Stygian Onslaught，5.6+）。结构同 role_combat：
        `{data: {data: [期数], is_unlock}}`，每期 `schedule/single.best`。
        """
        if game != "gs":
            return None
        acc = await self._ir.mihoyo_account_get(game, uid)
        if not acc or not acc.cookie:
            return None
        try:
            data = await self._run_skill("hard-challenge", {
                "uid": uid, "cookie": acc.cookie, "fp": acc.fp, "device_id": acc.device_id,
            })
        except Exception as e:
            logger.warning("[水神·游戏] 幽境危战抓取失败 {}/{}: {}", game, uid, e)
            return None
        if data.get("retcode") != 0:
            return None
        wrapper = data.get("data") or {}
        if not wrapper.get("is_unlock"):
            return None
        periods = wrapper.get("data") or []
        if not periods:
            return None
        periods.sort(key=lambda p: (p.get("schedule") or {}).get("start_time", 0), reverse=True)
        latest = periods[0]
        schedule = latest.get("schedule") or {}
        single = latest.get("single") or {}
        best = single.get("best") or {}
        schedule_id = str(schedule.get("schedule_id", ""))
        if not schedule_id:
            return None
        a = MihoyoAbyss(
            game=game, uid=uid, abyss_type="stygian",
            schedule_id=schedule_id, scan_ts=time.time(),
            max_floor=str(best.get("difficulty", "")),
            total_star=int(best.get("second", 0) or 0),   # 最快通关秒数
            start_time=str(schedule.get("start_time", "")),
            end_time=str(schedule.get("end_time", "")),
            raw=latest,
        )
        await self._ir.mihoyo_abyss_upsert(a, actor="水神")
        logger.info("[水神·游戏] 幽境危战入库 {}/{} difficulty={} second={}",
                    game, uid, a.max_floor, a.total_star)
        return a

    async def _collect_sr_challenge_generic(
        self, uid: str, skill_cmd: str, abyss_type: str, label: str,
    ) -> MihoyoAbyss | None:
        """崩铁三深渊共用抓取：结构一致，只有 URL / abyss_type 不同。"""
        acc = await self._ir.mihoyo_account_get("sr", uid)
        if not acc or not acc.cookie:
            return None
        try:
            data = await self._run_skill(skill_cmd, {
                "uid": uid, "cookie": acc.cookie, "fp": acc.fp, "device_id": acc.device_id,
                "schedule": 1,
            })
        except Exception as e:
            logger.warning("[水神·游戏] {} 抓取失败 {}: {}", label, uid, e)
            return None
        rc = data.get("retcode")
        if rc != 0:
            logger.warning("[水神·游戏] {} retcode={} msg={} {}",
                           label, rc, data.get("message", ""), uid)
            return None
        d = data.get("data") or {}
        if not d.get("has_data"):
            logger.info("[水神·游戏] {} has_data=false（未挑战）uid={}", label, uid)
            return None
        a = MihoyoAbyss(
            game="sr", uid=uid, abyss_type=abyss_type,
            schedule_id=str(d.get("schedule_id", "")),
            scan_ts=time.time(),
            max_floor=str(d.get("max_floor", "")),
            total_star=int(d.get("star_num", 0) or 0),
            total_battle=int(d.get("battle_num", 0) or 0),
            start_time=str(d.get("begin_time", "")),
            end_time=str(d.get("end_time", "")),
            raw=d,
        )
        await self._ir.mihoyo_abyss_upsert(a, actor="水神")
        logger.info("[水神·游戏] {} 入库 sr/{} max={} star={}",
                    label, uid, a.max_floor, a.total_star)
        return a

    async def collect_sr_forgotten_hall(self, uid: str) -> MihoyoAbyss | None:
        """崩铁忘却之庭。"""
        return await self._collect_sr_challenge_generic(
            uid, "sr-forgotten-hall", "forgotten_hall", "忘却之庭",
        )

    async def collect_sr_pure_fiction(self, uid: str) -> MihoyoAbyss | None:
        """崩铁虚构叙事。"""
        return await self._collect_sr_challenge_generic(
            uid, "sr-pure-fiction", "pure_fiction", "虚构叙事",
        )

    async def collect_sr_apocalyptic(self, uid: str) -> MihoyoAbyss | None:
        """崩铁末日幻影。"""
        return await self._collect_sr_challenge_generic(
            uid, "sr-apocalyptic", "apocalyptic", "末日幻影",
        )

    async def collect_sr_peak(self, uid: str) -> MihoyoAbyss | None:
        """崩铁异相仲裁（challenge_peak）。raw 结构和其他三副本完全不同：
        challenge_peak_records[] / challenge_peak_best_record_brief，没 has_data 字段。
        """
        acc = await self._ir.mihoyo_account_get("sr", uid)
        if not acc or not acc.cookie:
            return None
        try:
            data = await self._run_skill("sr-peak", {
                "uid": uid, "cookie": acc.cookie, "fp": acc.fp, "device_id": acc.device_id,
                "schedule": 1,
            })
        except Exception as e:
            logger.warning("[水神·游戏] 异相仲裁 抓取失败 {}: {}", uid, e)
            return None
        rc = data.get("retcode")
        if rc != 0:
            logger.warning("[水神·游戏] 异相仲裁 retcode={} msg={} {}",
                           rc, data.get("message", ""), uid)
            return None
        d = data.get("data") or {}
        records = d.get("challenge_peak_records") or []
        if not records:
            logger.info("[水神·游戏] 异相仲裁 无挑战记录 uid={}", uid)
            return None
        brief = d.get("challenge_peak_best_record_brief") or {}
        total_star = int(brief.get("boss_stars", 0) or 0) + int(brief.get("mob_stars", 0) or 0)
        # 奖牌 ChallengePeakRankIconTypeGold → 金/银/铜
        rank_icon = str(brief.get("challenge_peak_rank_icon_type", "") or "")
        rank_label = {
            "ChallengePeakRankIconTypeGold":   "金",
            "ChallengePeakRankIconTypeSilver": "银",
            "ChallengePeakRankIconTypeBronze": "铜",
        }.get(rank_icon, str(len(records)))
        a = MihoyoAbyss(
            game="sr", uid=uid, abyss_type="peak",
            schedule_id="",
            scan_ts=time.time(),
            max_floor=rank_label,
            total_star=total_star,
            total_battle=int(brief.get("total_battle_num", 0) or 0),
            raw=d,
        )
        await self._ir.mihoyo_abyss_upsert(a, actor="水神")
        logger.info("[水神·游戏] 异相仲裁 入库 sr/{} 记录={} 星={}",
                    uid, len(records), total_star)
        return a

    async def collect_zzz_shiyu(self, uid: str) -> MihoyoAbyss | None:
        """绝区零式舆防卫战。"""
        acc = await self._ir.mihoyo_account_get("zzz", uid)
        if not acc or not acc.cookie:
            return None
        try:
            data = await self._run_skill("zzz-shiyu", {
                "uid": uid, "cookie": acc.cookie, "fp": acc.fp, "device_id": acc.device_id,
                "schedule": 1,
            })
        except Exception as e:
            logger.warning("[水神·游戏] 式舆防卫战抓取失败 {}: {}", uid, e)
            return None
        rc = data.get("retcode")
        if rc != 0:
            logger.warning("[水神·游戏] 式舆 retcode={} msg={} snippet={} uid={}",
                           rc, data.get("message", ""),
                           (data.get("_raw_snippet") or "")[:120], uid)
            return None
        d = data.get("data") or {}
        src = data.get("_source", "challenge")
        # challenge（旧）结构：has_data / max_layer / rating_list / schedule_id
        # hadal_info_v2（新"第五防线"）结构：hadal_info_v2.zone_id / brief.score / rank_percent
        if src == "hadal":
            hadal = d.get("hadal_info_v2") or {}
            brief = hadal.get("brief") or {}
            if not hadal.get("zone_id"):
                logger.info("[水神·游戏] 第五防线 无数据 uid={}", uid)
                return None
            a = MihoyoAbyss(
                game="zzz", uid=uid, abyss_type="shiyu",
                schedule_id=str(hadal.get("zone_id", "")),
                scan_ts=time.time(),
                max_floor=str(brief.get("rating", "")),       # 评级 S+/S/A/B
                total_star=int(brief.get("score", 0) or 0),   # 得分
                total_battle=int(brief.get("battle_time", 0) or 0),
                total_win=int(brief.get("max_score", 0) or 0),
                start_time=str(hadal.get("begin_time", "")),
                end_time=str(hadal.get("end_time", "")),
                raw=d,
            )
        else:
            if not d.get("has_data"):
                logger.info("[水神·游戏] 式舆 has_data=false uid={}", uid)
                return None
            a = MihoyoAbyss(
                game="zzz", uid=uid, abyss_type="shiyu",
                schedule_id=str(d.get("schedule_id", "")),
                scan_ts=time.time(),
                max_floor=str(d.get("max_layer", "")),
                total_star=int(sum(r.get("times", 0) or 0 for r in (d.get("rating_list") or []))),
                start_time=str(d.get("begin_time", "")),
                end_time=str(d.get("end_time", "")),
                raw=d,
            )
        await self._ir.mihoyo_abyss_upsert(a, actor="水神")
        return a

    async def collect_zzz_mem(self, uid: str) -> MihoyoAbyss | None:
        """绝区零危局强袭战（Deadly Assault / mem_detail）。"""
        acc = await self._ir.mihoyo_account_get("zzz", uid)
        if not acc or not acc.cookie:
            return None
        try:
            data = await self._run_skill("zzz-mem", {
                "uid": uid, "cookie": acc.cookie, "fp": acc.fp, "device_id": acc.device_id,
                "schedule": 1,
            })
        except Exception as e:
            logger.warning("[水神·游戏] 危局强袭抓取失败 {}: {}", uid, e)
            return None
        rc = data.get("retcode")
        if rc != 0:
            logger.warning("[水神·游戏] 危局 retcode={} msg={} snippet={} uid={}",
                           rc, data.get("message", ""),
                           (data.get("_raw_snippet") or "")[:120], uid)
            return None
        d = data.get("data") or {}
        if not d.get("list"):
            logger.info("[水神·游戏] 危局 无挑战记录 uid={}", uid)
            return None
        a = MihoyoAbyss(
            game="zzz", uid=uid, abyss_type="mem",
            schedule_id=str(d.get("start_time", "")),   # mem 没明确 schedule_id，用 start_time 做键
            scan_ts=time.time(),
            max_floor=str(len(d.get("list") or [])),
            total_star=int(d.get("total_star", 0) or 0),
            total_battle=int(d.get("total_score", 0) or 0),
            start_time=str(d.get("start_time", "")),
            end_time=str(d.get("end_time", "")),
            raw=d,
        )
        await self._ir.mihoyo_abyss_upsert(a, actor="水神")
        return a

    async def collect_zzz_void(self, uid: str) -> MihoyoAbyss | None:
        """绝区零临界推演（void_front_battle_detail）。"""
        acc = await self._ir.mihoyo_account_get("zzz", uid)
        if not acc or not acc.cookie:
            return None
        try:
            data = await self._run_skill("zzz-void", {
                "uid": uid, "cookie": acc.cookie, "fp": acc.fp, "device_id": acc.device_id,
            })
        except Exception as e:
            logger.warning("[水神·游戏] 临界推演抓取失败 {}: {}", uid, e)
            return None
        rc = data.get("retcode")
        if rc != 0:
            logger.warning("[水神·游戏] 临界推演 retcode={} msg={} snippet={} uid={}",
                           rc, data.get("message", ""),
                           (data.get("_raw_snippet") or "")[:120], uid)
            return None
        d = data.get("data") or {}
        # raw 结构当前未文档化，先全保 raw，前端能看到再调
        a = MihoyoAbyss(
            game="zzz", uid=uid, abyss_type="void",
            schedule_id=str(d.get("void_front_id", "") or d.get("schedule_id", "")),
            scan_ts=time.time(),
            max_floor=str(d.get("rating", "") or d.get("max_layer", "") or ""),
            total_star=int(d.get("score", 0) or d.get("total_star", 0) or 0),
            start_time=str(d.get("begin_time", "") or d.get("start_time", "")),
            end_time=str(d.get("end_time", "")),
            raw=d,
        )
        await self._ir.mihoyo_abyss_upsert(a, actor="水神")
        return a

    async def collect_poetry(self, game: str, uid: str) -> MihoyoAbyss | None:
        """幻想真境剧诗。国服独占。

        米游社 `role_combat` 接口返回结构：
            {data: {data: [PoetryAbyssData, ...], is_unlock, links}}
        每期含 schedule（start_time/end_time/schedule_id）+ stat（max_round_id/medal_num）。
        上一版错把外层当 detail，导致 schedule_id / 分数全是空 → 前端显示"暂无数据"。
        """
        if game != "gs":
            return None
        acc = await self._ir.mihoyo_account_get(game, uid)
        if not acc or not acc.cookie:
            return None
        try:
            data = await self._run_skill("poetry-abyss", {
                "uid": uid, "cookie": acc.cookie,
                "fp": acc.fp, "device_id": acc.device_id,
            })
        except Exception as e:
            logger.warning("[水神·游戏] 剧诗抓取失败 {}/{}: {}", game, uid, e)
            return None
        if data.get("retcode") != 0:
            logger.debug("[水神·游戏] 剧诗 retcode!=0 {}/{}: {}", game, uid, data.get("message"))
            return None
        wrapper = data.get("data") or {}
        if not wrapper.get("is_unlock"):
            logger.debug("[水神·游戏] 剧诗未解锁 {}/{}", game, uid)
            return None
        periods = wrapper.get("data") or []
        if not periods:
            return None
        # 按 schedule.start_time 取最新一期
        periods.sort(
            key=lambda p: (p.get("schedule") or {}).get("start_time", 0),
            reverse=True,
        )
        latest = periods[0]
        schedule = latest.get("schedule") or {}
        stat = latest.get("stat") or {}
        schedule_id = str(schedule.get("schedule_id", ""))
        if not schedule_id:
            return None
        a = MihoyoAbyss(
            game=game, uid=uid, abyss_type="poetry",
            schedule_id=schedule_id,
            scan_ts=time.time(),
            max_floor=str(stat.get("max_round_id", "")),
            total_star=int(stat.get("medal_num", 0) or 0),  # 梦藏数
            start_time=str(schedule.get("start_time", "")),
            end_time=str(schedule.get("end_time", "")),
            raw=latest,
        )
        await self._ir.mihoyo_abyss_upsert(a, actor="水神")
        logger.info("[水神·游戏] 剧诗入库 {}/{} schedule={} max_round={} medal={}",
                    game, uid, schedule_id, a.max_floor, a.total_star)
        return a
