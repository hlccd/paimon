"""水神·游戏 · 账号绑定 mixin：扫码 / cookie / device 注册 / 平台判定。"""
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


class _AccountMixin:
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

    @staticmethod
    def _is_os(uid: str, game: str) -> bool:
        """国服/国际服判定，对齐 mihoyo/server.is_os。"""
        uid = str(uid).strip()
        if not uid:
            return False
        if game == "zzz":
            return len(uid) >= 10 and uid[:2] in ("17", "18", "19", "20")
        try:
            return int(uid[0]) >= 6
        except ValueError:
            return False

    @staticmethod
    def _mid_from_cookie(cookie: str) -> str:
        if not cookie:
            return ""
        for part in cookie.split(";"):
            kv = part.strip()
            if kv.startswith("mid="):
                return kv[4:]
        return ""
