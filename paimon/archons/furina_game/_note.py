"""水神·游戏 · 便笺采集 + 树脂提醒 + 签到 mixin。"""
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


# 签到间隔保护：同一账号一天只签一次（原 service.py 顶部，mixin 拆分后留这里）
SIGN_COOLDOWN = 23 * 3600


if TYPE_CHECKING:
    from paimon.foundation.irminsul import Irminsul
    from paimon.foundation.march import MarchService


class _NoteMixin:
    async def collect_daily_note(
        self, game: str, uid: str,
        march: "MarchService | None" = None,
        chat_id: str = "", channel_name: str = "",
    ) -> MihoyoNote | None:
        """抓便笺 → 入库 → 满额阈值推送。三游戏统一入口，内部按 game 映射字段。

        MihoyoNote 的字段命名沿用原神语义（resin/tasks/expedition），复用给崩铁/绝区零：
        - 崩铁：开拓力 stamina → resin、实训任务 → tasks、委托派遣 → expedition
        - 绝区零：电量 battery → resin、每日活跃 vitality → tasks（tasks 无委托概念则 expedition=0）
        raw_json 存原始结构，前端按 game 显示不同标签。
        """
        if game not in ("gs", "sr", "zzz"):
            return None
        acc = await self._ir.mihoyo_account_get(game, uid)
        if not acc or not acc.cookie:
            return None

        cmd_map = {"gs": "daily-note", "sr": "sr-note", "zzz": "zzz-note"}
        payload = {"uid": uid, "cookie": acc.cookie, "fp": acc.fp, "device_id": acc.device_id}
        try:
            data = await self._run_skill(cmd_map[game], payload)
        except Exception as e:
            logger.warning("[水神·游戏] 便笺抓取失败 {}/{}: {}", game, uid, e)
            return None

        # 10035 = 米游社把新 device 当陌生设备拦了。尝试补一次 deviceLogin 再重试。
        if data.get("retcode") == 10035:
            logger.info("[水神·游戏] {} / {} 收到 10035 风控，尝试补设备注册后重试", game, uid)
            if await self._ensure_device_registered(acc):
                await asyncio.sleep(1.0)
                try:
                    data = await self._run_skill(cmd_map[game], payload)
                except Exception as e:
                    logger.warning("[水神·游戏] 重试失败 {}/{}: {}", game, uid, e)
                    return None

        if data.get("retcode") != 0:
            logger.warning("[水神·游戏] 便笺返回异常 {}/{}: {}", game, uid, data)
            return None

        d = data.get("data") or {}
        now_ts = time.time()
        note = self._note_from_raw(game, uid, d, now_ts)
        await self._ir.mihoyo_note_upsert(note, actor="水神")

        # 满额阈值推送（三游戏通用：current / max ≥ 90% 推送）
        if (note.max_resin > 0
                and note.current_resin >= note.max_resin * self._FULL_RATIO
                and march and chat_id and channel_name):
            try:
                md = self._compose_resin_alert(note, acc.note, game)
                await march.ring_event(
                    channel_name=channel_name, chat_id=chat_id,
                    source="水神·便笺提醒", message=md, dedup_per_day=True,
                )
            except Exception as e:
                logger.error("[水神·游戏] 便笺推送失败: {}", e)

        return note

    @staticmethod
    def _note_from_raw(game: str, uid: str, d: dict, now_ts: float) -> MihoyoNote:
        """米游社便笺 raw JSON → MihoyoNote，按 game 映射字段。"""
        if game == "gs":
            recovery = int(d.get("resin_recovery_time", 0) or 0)
            return MihoyoNote(
                game=game, uid=uid, scan_ts=now_ts,
                current_resin=int(d.get("current_resin", 0) or 0),
                max_resin=int(d.get("max_resin", 160) or 160),
                resin_full_ts=now_ts + recovery if recovery > 0 else now_ts,
                finished_tasks=int(d.get("finished_task_num", 0) or 0),
                total_tasks=int(d.get("total_task_num", 4) or 4),
                daily_reward=1 if d.get("is_extra_task_reward_received") else 0,
                remain_discount=int(d.get("remain_resin_discount_num", 0) or 0),
                current_expedition=int(d.get("current_expedition_num", 0) or 0),
                max_expedition=int(d.get("max_expedition_num", 5) or 5),
                expeditions=list(d.get("expeditions") or []),
                transformer_ready=bool(
                    ((d.get("transformer") or {}).get("recovery_time") or {}).get("reached", False)
                ),
                raw=d,
            )
        if game == "sr":
            recovery = int(d.get("stamina_recover_time", 0) or 0)
            return MihoyoNote(
                game=game, uid=uid, scan_ts=now_ts,
                current_resin=int(d.get("current_stamina", 0) or 0),
                max_resin=int(d.get("max_stamina", 240) or 240),
                resin_full_ts=now_ts + recovery if recovery > 0 else now_ts,
                finished_tasks=int(d.get("current_train_score", 0) or 0),
                total_tasks=int(d.get("max_train_score", 500) or 500),
                daily_reward=0,  # 崩铁无"当日奖励已领"标记
                # 周本减半复用模拟宇宙周进度（current_rogue_score/max）
                remain_discount=int(d.get("current_rogue_score", 0) or 0),
                current_expedition=int(d.get("accepted_expedition_num", 0) or 0),
                max_expedition=int(d.get("total_expedition_num", 4) or 4),
                expeditions=list(d.get("expeditions") or []),
                transformer_ready=False,
                raw=d,
            )
        if game == "zzz":
            energy = (d.get("energy") or {}).get("progress") or {}
            recovery = int((d.get("energy") or {}).get("restore", 0) or 0)
            vitality = d.get("vitality") or {}
            bounty = d.get("bounty_commission") or {}
            return MihoyoNote(
                game=game, uid=uid, scan_ts=now_ts,
                current_resin=int(energy.get("current", 0) or 0),
                max_resin=int(energy.get("max", 240) or 240),
                resin_full_ts=now_ts + recovery if recovery > 0 else now_ts,
                finished_tasks=int(vitality.get("current", 0) or 0),
                total_tasks=int(vitality.get("max", 400) or 400),
                daily_reward=1 if d.get("card_sign") == "CardSignDone" else 0,
                # 悬赏委托进度复用 remain_discount 字段
                remain_discount=int(bounty.get("cur_completed", 0) or 0),
                current_expedition=0, max_expedition=0,
                expeditions=[],
                transformer_ready=False,
                raw=d,
            )
        raise ValueError(f"未知 game: {game}")

    @staticmethod
    def _compose_resin_alert(note: MihoyoNote, acc_note: str, game: str) -> str:
        """按 game 生成便笺满额提醒。三游戏术语不同：
        原神"树脂"+"每日委托"、崩铁"开拓力"+"每日实训"、绝区零"电量"+"每日活跃"。
        """
        uid_display = acc_note or f"UID {note.uid}"
        if game == "gs":
            title, stamina_label, daily_label = "⚗️ 原神树脂提醒", "树脂", "每日委托"
        elif game == "sr":
            title, stamina_label, daily_label = "🚆 崩铁开拓力提醒", "开拓力", "每日实训"
        else:
            title, stamina_label, daily_label = "⚡ 绝区零电量提醒", "电量", "每日活跃"
        lines = [
            f"## {title} · {uid_display}",
            "",
            f"- **{stamina_label}**：{note.current_resin}/{note.max_resin}"
            + ("（已满）" if note.current_resin >= note.max_resin else ""),
            f"- **{daily_label}**：{note.finished_tasks}/{note.total_tasks}",
        ]
        if game == "gs":
            if note.daily_reward:
                lines[-1] += "（奖励已领）"
            else:
                lines[-1] += "（**奖励未领**）"
            lines.append(f"- **周本减半**：剩余 {note.remain_discount} 次")
            lines.append(f"- **探索派遣**：{note.current_expedition}/{note.max_expedition}")
            if note.transformer_ready:
                lines.append("- **参量质变仪**:✅ 就绪")
        elif game == "sr":
            if note.remain_discount:
                lines.append(f"- **模拟宇宙周进度**：{note.remain_discount}")
            lines.append(f"- **委托派遣**：{note.current_expedition}/{note.max_expedition}")
        else:  # zzz
            lines.append(f"- **悬赏委托已完成**：{note.remain_discount}")
            if note.daily_reward:
                lines.append("- **今日电视签到**：✅ 已签")
        return "\n".join(lines)

    # ===================== 签到 =====================

    async def sign_in(self, game: str, uid: str) -> dict[str, Any]:
        """单账号签到，内置冷却保护（23h 内不重复签）。"""
        acc = await self._ir.mihoyo_account_get(game, uid)
        if not acc or not acc.cookie:
            return {"ok": False, "msg": "账号不存在或 Cookie 为空"}
        if time.time() - acc.last_sign_at < SIGN_COOLDOWN:
            return {"ok": True, "msg": "今日已签", "skipped": True}

        try:
            r = await self._run_skill("sign", {
                "game": game, "uid": uid, "cookie": acc.cookie,
                "fp": acc.fp, "device_id": acc.device_id,
            })
        except Exception as e:
            return {"ok": False, "msg": str(e)}

        if r.get("ok") or r.get("is_signed"):
            await self._ir.mihoyo_account_set_sign_time(game, uid, time.time())
        logger.info("[水神·游戏] 签到 {}/{} ok={} msg={}", game, uid, r.get("ok"), r.get("msg", "")[:80])
        return r

    async def sign_all(self) -> list[dict[str, Any]]:
        """给所有启用账号签到。"""
        accs = await self._ir.mihoyo_account_list()
        results: list[dict[str, Any]] = []
        for a in accs:
            if not a.enabled:
                continue
            r = await self.sign_in(a.game, a.uid)
            r.update({"game": a.game, "uid": a.uid, "note": a.note})
            results.append(r)
            # baostock 同款限速（米游社不明，稳妥 1s 一次）
            await asyncio.sleep(1.0)
        return results
