"""水神·游戏 · 总览 + 全量采集编排 mixin（合并便笺 / 深渊 / 角色 / 抽卡）。"""
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


class _OverviewMixin:
    async def overview(self) -> dict[str, Any]:
        """所有账号 + 最新便笺的聚合，供 /game 面板。"""
        accs = await self._ir.mihoyo_account_list()
        items = []
        for a in accs:
            note = await self._ir.mihoyo_note_get(a.game, a.uid)
            items.append({
                "game": a.game, "uid": a.uid, "mys_id": a.mys_id,
                "note": a.note, "added_date": a.added_date,
                "last_sign_at": a.last_sign_at,
                "enabled": a.enabled,
                "has_cookie": bool(a.cookie),
                "has_authkey": bool(a.authkey),
                "authkey_age_hours": (
                    round((time.time() - a.authkey_ts) / 3600, 1)
                    if a.authkey_ts else None
                ),
                "daily_note": {
                    "scan_ts": note.scan_ts,
                    "current_resin": note.current_resin,
                    "max_resin": note.max_resin,
                    "resin_full_ts": note.resin_full_ts,
                    "finished_tasks": note.finished_tasks,
                    "total_tasks": note.total_tasks,
                    "daily_reward": note.daily_reward,
                    "remain_discount": note.remain_discount,
                    "current_expedition": note.current_expedition,
                    "max_expedition": note.max_expedition,
                    "transformer_ready": note.transformer_ready,
                } if note else None,
            })
        return {"accounts": items}

    async def collect_all(
        self,
        march: "MarchService | None" = None,
        chat_id: str = "", channel_name: str = "",
    ) -> dict[str, Any]:
        """三月 daily cron 调：全账号全副本一次采。

        每游戏采集范围：
        - 所有游戏：签到 + 便笺
        - 原神 gs：深境螺旋 + 剧诗 + 幽境危战
        - 崩铁 sr：忘却之庭（暂只抓最主流，虚构叙事 / 末日幻影后续加）
        - 绝区零 zzz：式舆防卫战 + 危局强袭战
        """
        accs = await self._ir.mihoyo_account_list()
        counts = self._empty_counts()
        for a in accs:
            if not a.enabled:
                continue
            await self._collect_one_account(a, counts, march=march, chat_id=chat_id, channel_name=channel_name)
        logger.info("[水神·游戏] 定时采集完成 {}", counts)
        return counts

    async def collect_one(
        self, game: str, uid: str,
        march: "MarchService | None" = None,
        chat_id: str = "", channel_name: str = "",
    ) -> dict[str, Any]:
        """只采一个账号（WebUI "刷新此账号数据" 按钮用）。复用 _collect_one_account。"""
        acc = await self._ir.mihoyo_account_get(game, uid)
        if not acc or not acc.enabled:
            return {}
        counts = self._empty_counts()
        await self._collect_one_account(acc, counts, march=march, chat_id=chat_id, channel_name=channel_name)
        logger.info("[水神·游戏] 单账号采集完成 {}/{} {}", game, uid, counts)
        return counts

    # ---------- collect_one background 状态机 ----------
    # WebUI 点"刷新此账号数据"立即返回 → 前端轮询 status → 完成自动 reload UI
    @staticmethod
    def _collect_key(game: str, uid: str) -> str:
        return f"{game}::{uid}"

    async def start_collect_one(self, game: str, uid: str) -> dict[str, Any]:
        key = self._collect_key(game, uid)
        st = self._collect_state.get(key)
        if st and st.get("state") == "running":
            return {"ok": False, "msg": "已在采集中，请稍候"}
        acc = await self._ir.mihoyo_account_get(game, uid)
        if not acc or not acc.enabled:
            return {"ok": False, "msg": f"未绑定 {game}/{uid}"}
        self._collect_state[key] = {
            "state": "running", "phase": "启动",
            "counts": self._empty_counts(),
            "started_at": time.time(),
        }
        logger.info("[水神·游戏] 单账号采集启动 {}/{}", game, uid)
        from paimon.foundation.bg import bg
        bg(self._collect_worker(game, uid, key), label=f"furina·collect·{game}·{uid}")
        return {"ok": True}

    async def _collect_worker(self, game: str, uid: str, key: str) -> None:
        try:
            counts = await self.collect_one(game, uid)
            self._collect_state[key].update({
                "state": "done", "counts": counts or self._empty_counts(),
                "ended_at": time.time(),
            })
        except Exception as e:
            logger.exception("[水神·游戏] 采集异常 {}/{}", game, uid)
            self._collect_state[key].update({
                "state": "failed", "error": str(e), "ended_at": time.time(),
            })

    def get_collect_state(self, game: str, uid: str) -> dict[str, Any]:
        return self._collect_state.get(self._collect_key(game, uid)) or {"state": "idle"}

    @staticmethod
    def _empty_counts() -> dict[str, int]:
        return {"sign": 0, "note": 0, "abyss": 0, "poetry": 0, "stygian": 0,
                "gs_chars": 0, "sr_chars": 0, "zzz_chars": 0,
                "sr_fh": 0, "sr_pf": 0, "sr_apc": 0, "sr_peak": 0,
                "zzz_shiyu": 0, "zzz_mem": 0, "zzz_void": 0}

    async def _collect_one_account(
        self, a: MihoyoAccount, counts: dict[str, int],
        *, march: "MarchService | None" = None,
        chat_id: str = "", channel_name: str = "",
    ) -> None:
        """单账号采集逻辑：签到 + 便笺 + 该游戏专属副本/角色。"""
        # 签到（所有游戏）
        try:
            r = await self.sign_in(a.game, a.uid)
            if r.get("ok"):
                counts["sign"] += 1
        except Exception as e:
            logger.warning("[水神·游戏] 签到异常 {}/{}: {}", a.game, a.uid, e)
        await asyncio.sleep(1.0)

        # 便笺（三游戏统一）
        try:
            if await self.collect_daily_note(
                a.game, a.uid, march=march, chat_id=chat_id, channel_name=channel_name,
            ):
                counts["note"] += 1
        except Exception as e:
            logger.warning("[水神·游戏] 便笺异常 {}/{}: {}", a.game, a.uid, e)
        await asyncio.sleep(1.0)

        # 分游戏副本采集
        if a.game == "gs":
            try:
                if await self.collect_abyss(a.game, a.uid): counts["abyss"] += 1
            except Exception as e: logger.warning("[水神·游戏] 深渊 {}: {}", a.uid, e)
            await asyncio.sleep(1.0)
            try:
                if await self.collect_poetry(a.game, a.uid): counts["poetry"] += 1
            except Exception as e: logger.warning("[水神·游戏] 剧诗 {}: {}", a.uid, e)
            await asyncio.sleep(1.0)
            try:
                if await self.collect_hard_challenge(a.game, a.uid): counts["stygian"] += 1
            except Exception as e: logger.warning("[水神·游戏] 幽境 {}: {}", a.uid, e)
            await asyncio.sleep(1.0)
            try:
                n = await self.collect_gs_characters(a.uid)
                if n > 0: counts["gs_chars"] += n
            except Exception as e: logger.warning("[水神·游戏] 角色 {}: {}", a.uid, e)
        elif a.game == "sr":
            try:
                if await self.collect_sr_forgotten_hall(a.uid): counts["sr_fh"] += 1
            except Exception as e: logger.warning("[水神·游戏] 忘却之庭 {}: {}", a.uid, e)
            await asyncio.sleep(1.0)
            try:
                if await self.collect_sr_pure_fiction(a.uid): counts["sr_pf"] += 1
            except Exception as e: logger.warning("[水神·游戏] 虚构叙事 {}: {}", a.uid, e)
            await asyncio.sleep(1.0)
            try:
                if await self.collect_sr_apocalyptic(a.uid): counts["sr_apc"] += 1
            except Exception as e: logger.warning("[水神·游戏] 末日幻影 {}: {}", a.uid, e)
            await asyncio.sleep(1.0)
            try:
                if await self.collect_sr_peak(a.uid): counts["sr_peak"] += 1
            except Exception as e: logger.warning("[水神·游戏] 异相仲裁 {}: {}", a.uid, e)
            await asyncio.sleep(1.0)
            try:
                n = await self.collect_sr_characters(a.uid)
                if n > 0: counts["sr_chars"] += n
            except Exception as e: logger.warning("[水神·游戏] 崩铁角色 {}: {}", a.uid, e)
        elif a.game == "zzz":
            try:
                if await self.collect_zzz_shiyu(a.uid): counts["zzz_shiyu"] += 1
            except Exception as e: logger.warning("[水神·游戏] 式舆 {}: {}", a.uid, e)
            await asyncio.sleep(1.0)
            try:
                if await self.collect_zzz_mem(a.uid): counts["zzz_mem"] += 1
            except Exception as e: logger.warning("[水神·游戏] 危局 {}: {}", a.uid, e)
            await asyncio.sleep(1.0)
            # TODO 临界推演接口 endpoint 404 page not found，等抓包确认真实 path 后启用
            # try:
            #     if await self.collect_zzz_void(a.uid): counts["zzz_void"] += 1
            # except Exception as e: logger.warning("[水神·游戏] 临界推演 {}: {}", a.uid, e)
            # await asyncio.sleep(1.0)
            try:
                n = await self.collect_zzz_characters(a.uid)
                if n > 0: counts["zzz_chars"] += n
            except Exception as e: logger.warning("[水神·游戏] 绝区零代理人 {}: {}", a.uid, e)
        await asyncio.sleep(1.0)
