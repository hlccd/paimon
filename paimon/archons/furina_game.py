"""水神 · 游戏信息服务 — 米哈游游戏（原神/星铁/绝区零）

- 扫码登录绑定 → 写 mihoyo_account
- 每日便笺采集 → 写 mihoyo_note + 树脂阈值推送
- 签到（三游戏）
- 深渊/剧诗战报采集 → 写 mihoyo_abyss
- 抽卡记录抓取（authkey）→ 写 mihoyo_gacha + 统计

skill 层调用统一走 subprocess + stdin JSON；水神只做业务编排。
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING, Any

from loguru import logger

from paimon.foundation.irminsul import (
    Irminsul, MihoyoAbyss, MihoyoAccount, MihoyoCharacter, MihoyoGacha, MihoyoNote,
)

if TYPE_CHECKING:
    from paimon.foundation.march import MarchService


_SKILL_MIHOYO = (
    Path(__file__).resolve().parent.parent.parent / "skills" / "mihoyo" / "main.py"
)

# 便笺抓取常量
RESIN_ALERT_THRESHOLD = 150   # ≥此值推送提醒（上限 160，留点缓冲）

# 签到间隔保护：同一账号一天只签一次
SIGN_COOLDOWN = 23 * 3600     # 23 小时


class FurinaGameService:
    """游戏信息聚合服务。由 FurinaArchon 持有，WebUI / cron 直调。"""

    def __init__(self, irminsul: Irminsul):
        self._ir = irminsul
        # 扫码登录的中间态（ticket → {device, started_at}）
        self._pending_qr: dict[str, dict[str, Any]] = {}

    # ===================== skill 桥接 =====================

    async def _run_skill(
        self, cmd: str, payload: dict | None = None, *, timeout: int = 60,
    ) -> dict:
        """subprocess 调 mihoyo skill，stdin 传 JSON，stdout 读 JSON。"""
        if not _SKILL_MIHOYO.exists():
            raise RuntimeError(f"mihoyo skill 不存在: {_SKILL_MIHOYO}")

        env = {**os.environ, "PAIMON_SKILL_RUNTIME": "1", "PYTHONIOENCODING": "utf-8"}
        proc = await asyncio.create_subprocess_exec(
            sys.executable, str(_SKILL_MIHOYO), cmd,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
        )
        stdin_bytes = json.dumps(payload or {}).encode("utf-8")
        try:
            out, err = await asyncio.wait_for(
                proc.communicate(stdin_bytes), timeout=timeout,
            )
        except asyncio.TimeoutError:
            try:
                proc.kill(); await proc.wait()
            except Exception:
                pass
            raise RuntimeError(f"mihoyo skill 超时 cmd={cmd}")

        if proc.returncode != 0:
            err_text = err.decode("utf-8", "ignore")[:500]
            raise RuntimeError(
                f"mihoyo skill 失败 cmd={cmd} rc={proc.returncode}: {err_text}"
            )
        try:
            return json.loads(out.decode("utf-8", "ignore"))
        except json.JSONDecodeError as e:
            raise RuntimeError(f"mihoyo skill 输出非 JSON: {e}")

    # ===================== 扫码登录 =====================

    async def qr_create(self) -> dict[str, Any]:
        """创建扫码登录 QR。前端拿 url 显示二维码让用户扫。"""
        r = await self._run_skill("qr-create")
        self._pending_qr[r["ticket"]] = {
            "device": r["device"], "started_at": time.time(),
        }
        # 过期清理（超 10 分钟的 pending）
        self._pending_qr = {
            k: v for k, v in self._pending_qr.items()
            if time.time() - v["started_at"] < 600
        }
        return r

    async def qr_poll(self, app_id: str, ticket: str, device: str) -> dict[str, Any]:
        """轮询扫码状态。Confirmed 时自动绑定所有游戏 UID。"""
        r = await self._run_skill("qr-poll", {
            "app_id": app_id, "ticket": ticket, "device": device,
        })
        if r.get("stat") != "Confirmed":
            return r

        mys_id = str(r["uid"])
        game_token = r["game_token"]

        # Step 1: GameToken → Stoken（含 user_info.mid）
        stoken_info = await self._run_skill("stoken-exchange", {
            "account_id": mys_id, "game_token": game_token,
        })
        stoken = stoken_info.get("token", {}).get("token", "")
        mid = stoken_info.get("user_info", {}).get("mid", "")
        aid = str(stoken_info.get("user_info", {}).get("aid", mys_id))
        if not stoken or not mid:
            logger.warning("[水神·游戏] Stoken 拿取失败: {}", stoken_info)
            return {
                "stat": "Confirmed", "mys_id": mys_id, "bound": [],
                "error": "扫码成功但拿 Stoken 失败",
            }

        # Step 2: Stoken + mid → Cookie（走 stoken 路径，米游社 2024 后废弃了 game_token 直换）
        cookie_info = await self._run_skill("cookie-exchange", {
            "stoken": stoken, "mys_id": aid, "mid": mid,
        })
        cookie = cookie_info["cookie"]

        # 先为"查玩家卡片"生成一个临时 fp（不绑任何 UID）
        probe_fp = await self._run_skill("gen-fp")

        # 查所有绑定的游戏 UID（带 fp/device_id 避免风控）
        games = await self._run_skill("game-record", {
            "mys_id": mys_id, "cookie": cookie,
            "fp": probe_fp["fp"], "device_id": probe_fp["device_id"],
        })
        if games.get("retcode") not in (0, None):
            # 风控/Cookie 失败：仍把 mys_id 这一层信息返回给用户，但绑定失败
            logger.warning("[水神·游戏] 获取游戏列表失败: {}", games)
            return {
                "stat": "Confirmed", "mys_id": mys_id, "bound": [],
                "error": f"拉玩家卡片失败 retcode={games.get('retcode')}: {games.get('message','')}",
            }
        game_list = (games.get("data") or {}).get("list") or []

        # game_id: 2=原神, 6=星铁, 8=绝区零
        game_code_map = {2: "gs", 6: "sr", 8: "zzz"}
        bound: list[dict[str, str]] = []
        for g in game_list:
            code = game_code_map.get(g.get("game_id"))
            if not code:
                continue
            uid = str(g.get("game_role_id", ""))
            if not uid:
                continue
            # 每个游戏 UID 独立 fp（对齐 gsuid_core 行为，降低风控联动）
            try:
                per_fp = await self._run_skill("gen-fp")
            except Exception as e:
                logger.warning("[水神·游戏] 生成 fp 失败 {}/{}: {}", code, uid, e)
                per_fp = probe_fp  # fallback

            # 注册设备 —— 关键步骤！不调 deviceLogin+saveDevice 的话，崩铁/绝区零
            # game_record 接口会把新 device_id+fp 视为陌生设备，返 retcode=10035 风控。
            # 需要 app_cookie 格式 `stuid={aid};stoken={stoken};mid={mid}` 给设备接口
            app_cookie_for_device = f"stuid={aid};stoken={stoken};mid={mid}"
            try:
                await self._run_skill("device-login", {
                    "device_id": per_fp["device_id"],
                    "fp": per_fp["fp"],
                    "device_info": per_fp["device_info"],
                    "app_cookie": app_cookie_for_device,
                })
            except Exception as e:
                logger.warning("[水神·游戏] 设备注册失败 {}/{}: {}", code, uid, e)

            acc = MihoyoAccount(
                game=code, uid=uid, mys_id=mys_id,
                cookie=cookie, stoken=stoken,
                fp=per_fp["fp"], device_id=per_fp["device_id"],
                device_info=per_fp["device_info"],
                note=g.get("nickname", "") or "",
                added_date=date.today().isoformat(),
            )
            await self._ir.mihoyo_account_upsert(acc, actor="水神")
            bound.append({"game": code, "uid": uid, "nickname": g.get("nickname", "")})

        logger.info("[水神·游戏] 扫码绑定成功 mys_id={} 账号 {} 个", mys_id, len(bound))
        return {
            "stat": "Confirmed", "mys_id": mys_id,
            "bound": bound,
        }

    # ===================== 便笺（原神） =====================

    # 每游戏满额阈值（树脂/开拓力/电量满才推送，比例接近）
    _FULL_RATIO = 0.9  # ≥ 90% 推送提醒（原神 144/160 / 崩铁 216/240 / 绝区零 216/240）

    @staticmethod
    def _extract_cookie_field(cookie: str, key: str) -> str:
        """从 Cookie 字符串里提指定字段值（mid/stuid 等）。"""
        for part in (cookie or "").split(";"):
            part = part.strip()
            if part.startswith(f"{key}="):
                return part[len(key) + 1:]
        return ""

    async def _ensure_device_registered(self, acc: MihoyoAccount) -> bool:
        """给已绑账号补一次 deviceLogin+saveDevice。对旧版（未做这步绑的）账号，
        便笺接口会返 10035；调用本方法后下一次请求一般就认识设备了。
        """
        mid = self._extract_cookie_field(acc.cookie, "mid")
        if not mid or not acc.stoken:
            logger.warning("[水神·游戏] {} / {} 无 mid/stoken 跳过设备注册", acc.game, acc.uid)
            return False
        app_cookie = f"stuid={acc.mys_id};stoken={acc.stoken};mid={mid}"
        try:
            await self._run_skill("device-login", {
                "device_id": acc.device_id, "fp": acc.fp,
                "device_info": acc.device_info, "app_cookie": app_cookie,
            })
            logger.info("[水神·游戏] {} / {} 设备补注册成功", acc.game, acc.uid)
            return True
        except Exception as e:
            logger.warning("[水神·游戏] {} / {} 设备补注册失败: {}", acc.game, acc.uid, e)
            return False

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

    # ===================== 深渊 / 剧诗 =====================

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

    async def collect_gs_characters(self, uid: str) -> int:
        """原神角色列表抓取 + 入库。返回写入条数。

        米游社返回 `data.avatars: [...]`，每个 avatar 含 id/name/level/actived_constellation_num
        /element/rarity/weapon/reliquaries/image 等。
        """
        acc = await self._ir.mihoyo_account_get("gs", uid)
        if not acc or not acc.cookie:
            return 0
        try:
            data = await self._run_skill("gs-characters", {
                "uid": uid, "cookie": acc.cookie, "fp": acc.fp, "device_id": acc.device_id,
                "character_ids": [],
            })
        except Exception as e:
            logger.warning("[水神·游戏] 原神角色抓取失败 {}: {}", uid, e)
            return 0
        rc = data.get("retcode")
        if rc != 0:
            logger.warning("[水神·游戏] 原神角色 retcode={} msg={} uid={}",
                           rc, data.get("message", ""), uid)
            return 0
        # 米游社 /character/list 返回的是 `data.list`（不是 `data.avatars`）
        # 字段名搞错会静默返 0 —— 加 warning 让下次掉这里有痕迹
        d = data.get("data") or {}
        avatars = d.get("list") or d.get("avatars") or []
        if not avatars:
            logger.warning("[水神·游戏] 原神角色列表为空 uid={} data_keys={}",
                           uid, list(d.keys()))
            return 0
        now_ts = time.time()
        items: list[MihoyoCharacter] = []
        for av in avatars:
            weapon_raw = av.get("weapon") or {}
            items.append(MihoyoCharacter(
                game="gs", uid=uid,
                avatar_id=str(av.get("id", "")),
                name=str(av.get("name", "")),
                element=str(av.get("element", "")),   # Anemo / Pyro / 等
                rarity=int(av.get("rarity", 4) or 4),
                level=int(av.get("level", 1) or 1),
                constellation=int(av.get("actived_constellation_num", 0) or 0),
                fetter=int(av.get("fetter", 0) or 0),
                weapon={
                    "name": weapon_raw.get("name", ""),
                    "level": weapon_raw.get("level", 0),
                    "affix": weapon_raw.get("affix_level", 0),
                    "rarity": weapon_raw.get("rarity", 3),
                    "icon": weapon_raw.get("icon", ""),
                },
                relics=[
                    {"name": r.get("name",""), "pos": r.get("pos_name",""),
                     "rarity": r.get("rarity",4), "level": r.get("level",0),
                     "icon": r.get("icon","")}
                    for r in (av.get("reliquaries") or [])
                ],
                icon_url=str(av.get("image", "") or av.get("icon", "")),
                scan_ts=now_ts,
                raw=av,
            ))
        n = await self._ir.mihoyo_character_upsert(items, actor="水神")
        logger.info("[水神·游戏] 原神角色入库 gs/{} 共 {} 个", uid, n)
        return n

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

    # ===================== 抽卡（authkey） =====================

    async def import_gacha_from_url(
        self, game_url: str, *, game: str = "gs", gacha_types: list[str] | None = None,
    ) -> dict[str, Any]:
        """用户从游戏内"祈愿历史"复制链接 → 提 authkey → 拉全量 → 入库。

        gacha_types 默认 ['301','302','200','500']（角色/武器/常驻/集录）。
        """
        from paimon.foundation.irminsul import MihoyoGacha as G

        # 提 authkey + is_os
        r = await self._run_skill("parse-authkey", {"url": game_url})
        if not r.get("ok"):
            return {"ok": False, "msg": "URL 里没解析到 authkey"}
        authkey = r["authkey"]; is_os = r.get("is_os", False)

        types = gacha_types or ["301", "302", "200", "500"]
        summary: dict[str, int] = {}
        target_uid: str | None = None

        for gt in types:
            since_id = ""
            # 首抓先不给 since_id 拉全量，后续增量 scan 才用 since_id
            # 这里检测已有 max_id → 增量
            if target_uid:
                since_id = await self._ir.mihoyo_gacha_max_id(target_uid, gt)

            try:
                data = await self._run_skill("gacha-log", {
                    "authkey": authkey, "gacha_type": gt,
                    "is_os": is_os, "since_id": since_id,
                }, timeout=300)
            except Exception as e:
                summary[gt] = -1
                logger.warning("[水神·游戏] 抽卡抓取失败 type={} : {}", gt, e)
                continue

            items = data.get("items") or []
            to_save: list[G] = []
            for it in items:
                if not target_uid:
                    target_uid = str(it.get("uid", ""))
                # 时间戳解析
                tstr = it.get("time", "")
                ts = 0.0
                try:
                    from datetime import datetime as _dt
                    ts = _dt.strptime(tstr, "%Y-%m-%d %H:%M:%S").timestamp()
                except Exception:
                    ts = 0.0
                to_save.append(G(
                    id=str(it.get("id", "")),
                    uid=str(it.get("uid", "")),
                    gacha_type=str(gt),
                    item_id=str(it.get("item_id", "")),
                    item_type=str(it.get("item_type", "")),
                    name=str(it.get("name", "")),
                    rank_type=int(it.get("rank_type", 3)),
                    time=tstr, time_ts=ts,
                    raw=it,
                ))
            n = await self._ir.mihoyo_gacha_insert(to_save, actor="水神")
            summary[gt] = n

            # 保存 authkey 到 account（以备增量复用）
            if target_uid and authkey:
                await self._ir.mihoyo_account_update_authkey(
                    target_uid, authkey, game=game, actor="水神",
                )

        return {"ok": True, "uid": target_uid, "summary": summary}

    async def gacha_stats(self, uid: str, gacha_type: str = "301") -> dict[str, Any]:
        """取抽卡统计（小保底/总数/历次 5 星）。"""
        return await self._ir.mihoyo_gacha_stats(uid, gacha_type)

    # ===================== 聚合视图（给面板用）=====================

    async def overview(self) -> dict[str, Any]:
        """所有账号 + 最新便笺的聚合，供 /game 面板。"""
        accs = await self._ir.mihoyo_account_list()
        items = []
        for a in accs:
            note = await self._ir.mihoyo_note_get(a.game, a.uid)
            gacha_301_stats = None
            if a.game == "gs":
                gacha_301_stats = await self._ir.mihoyo_gacha_stats(a.uid, "301")
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
                "gacha_301": gacha_301_stats,
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

    @staticmethod
    def _empty_counts() -> dict[str, int]:
        return {"sign": 0, "note": 0, "abyss": 0, "poetry": 0, "stygian": 0,
                "gs_chars": 0,
                "sr_fh": 0, "sr_pf": 0, "sr_apc": 0,
                "zzz_shiyu": 0, "zzz_mem": 0}

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
        elif a.game == "zzz":
            try:
                if await self.collect_zzz_shiyu(a.uid): counts["zzz_shiyu"] += 1
            except Exception as e: logger.warning("[水神·游戏] 式舆 {}: {}", a.uid, e)
            await asyncio.sleep(1.0)
            try:
                if await self.collect_zzz_mem(a.uid): counts["zzz_mem"] += 1
            except Exception as e: logger.warning("[水神·游戏] 危局 {}: {}", a.uid, e)
        await asyncio.sleep(1.0)


# ============================================================
# task_types 注册（供三月 cron 分派）
# ============================================================


def register_task_types() -> None:
    """注册水神·游戏名下的周期任务类型。bootstrap 启动时调一次。

    `mihoyo_collect`：每日 8:05 签到 + 便笺 + 深渊一次打包。
    """
    from paimon.foundation import task_types

    async def _desc(source_entity_id: str, irminsul) -> str:
        return "米哈游每日采集（签到 + 便笺 + 深渊）"

    async def _dispatch(task, state) -> None:
        if not state.furina_game:
            logger.error("[水神·游戏] service 未就绪，跳过采集")
            return
        try:
            await state.furina_game.collect_all(
                march=state.march,
                chat_id=task.chat_id, channel_name=task.channel_name,
            )
        except Exception as e:
            logger.exception("[水神·游戏] 采集异常: {}", e)

    task_types.register(task_types.TaskTypeMeta(
        task_type="mihoyo_collect",
        display_label="米哈游采集",
        manager_panel="/game",
        icon="gamepad",
        description_builder=_desc,
        anchor_builder=None,
        dispatcher=_dispatch,
    ))
