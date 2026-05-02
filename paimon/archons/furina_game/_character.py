"""水神·游戏 · 角色仓库采集 mixin（gs / sr / zzz 三游戏）。"""
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


class _CharacterMixin:
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
        if avatars:
            a0 = avatars[0]
            logger.info("[水神·游戏] 原神角色入库 gs/{} 共 {} 个 · debug 首角色 image:[{}] icon:[{}]",
                        uid, n, str(a0.get("image","-"))[:80], str(a0.get("icon","-"))[:80])
        return n

    async def collect_sr_characters(self, uid: str) -> int:
        """崩铁角色列表入库。字段映射：rank→constellation, equip→weapon, element→element。"""
        acc = await self._ir.mihoyo_account_get("sr", uid)
        if not acc or not acc.cookie:
            return 0
        try:
            data = await self._run_skill("sr-avatars", {
                "uid": uid, "cookie": acc.cookie, "fp": acc.fp, "device_id": acc.device_id,
            })
        except Exception as e:
            logger.warning("[水神·游戏] 崩铁角色抓取失败 {}: {}", uid, e)
            return 0
        rc = data.get("retcode")
        if rc != 0:
            logger.warning("[水神·游戏] 崩铁角色 retcode={} msg={} uid={}",
                           rc, data.get("message", ""), uid)
            return 0
        d = data.get("data") or {}
        avatars = d.get("avatar_list") or []
        if not avatars:
            logger.warning("[水神·游戏] 崩铁角色列表空 uid={} data_keys={}", uid, list(d.keys()))
            return 0
        now_ts = time.time()
        items: list[MihoyoCharacter] = []
        for av in avatars:
            equip_raw = av.get("equip") or {}
            relics_raw = (av.get("relics") or []) + (av.get("ornaments") or [])
            items.append(MihoyoCharacter(
                game="sr", uid=uid,
                avatar_id=str(av.get("id", "")),
                name=str(av.get("name", "")),
                element=str(av.get("element", "")),
                rarity=int(av.get("rarity", 4) or 4),
                level=int(av.get("level", 1) or 1),
                constellation=int(av.get("rank", 0) or 0),
                weapon={
                    "name": equip_raw.get("name", ""),
                    "level": equip_raw.get("level", 0),
                    "affix": equip_raw.get("rank", 0),   # 叠影 rank
                    "rarity": equip_raw.get("rarity", 3),
                    "icon": equip_raw.get("icon", ""),
                } if equip_raw else {},
                relics=[
                    {"name": r.get("name",""), "pos": r.get("pos",0),
                     "rarity": r.get("rarity",4), "level": r.get("level",0),
                     "icon": r.get("icon","")}
                    for r in relics_raw
                ],
                icon_url=str(av.get("icon", "") or av.get("image", "") or av.get("figure_path", "")),
                scan_ts=now_ts,
                raw=av,
            ))
        n = await self._ir.mihoyo_character_upsert(items, actor="水神")
        # debug：打第一个角色的 icon 相关字段，方便排查"没图标"
        if avatars:
            a0 = avatars[0]
            logger.info("[水神·游戏] 崩铁角色入库 sr/{} 共 {} 个 · debug 首角色 icon:[{}] image:[{}] figure_path:[{}]",
                        uid, n, a0.get("icon","-")[:80], a0.get("image","-")[:80], a0.get("figure_path","-")[:80])
        return n

    async def collect_zzz_characters(self, uid: str) -> int:
        """绝区零代理人列表入库（只取 basic 接口，不拉音擎/驱动盘）。

        字段映射：rank→constellation, rarity(S/A → 5/4), element_type→element,
        camp_name_mi18n→weapon.name 仅占位，name_mi18n→name。
        音擎 + 驱动盘 详情要走 /avatar/info 单个 id 循环，下轮视需要再加。
        """
        acc = await self._ir.mihoyo_account_get("zzz", uid)
        if not acc or not acc.cookie:
            return 0
        try:
            data = await self._run_skill("zzz-avatars", {
                "uid": uid, "cookie": acc.cookie, "fp": acc.fp, "device_id": acc.device_id,
            })
        except Exception as e:
            logger.warning("[水神·游戏] 绝区零代理人抓取失败 {}: {}", uid, e)
            return 0
        rc = data.get("retcode")
        if rc != 0:
            logger.warning("[水神·游戏] 绝区零代理人 retcode={} msg={} uid={}",
                           rc, data.get("message", ""), uid)
            return 0
        d = data.get("data") or {}
        avatars = d.get("avatar_list") or []
        if not avatars:
            logger.warning("[水神·游戏] 绝区零代理人列表空 uid={} data_keys={}", uid, list(d.keys()))
            return 0
        # ZZZ rarity: S=5, A=4, B=3（米游社 rarity 字段是字符串 S/A/B 或者已是数字）
        rarity_map = {"S": 5, "A": 4, "B": 3}
        now_ts = time.time()
        items: list[MihoyoCharacter] = []
        for av in avatars:
            rarity_raw = av.get("rarity", 4)
            if isinstance(rarity_raw, str):
                rarity_val = rarity_map.get(rarity_raw, 4)
            else:
                rarity_val = int(rarity_raw or 4)
            # 米游社 zzz basic 实际返回是扁平结构（不是 ZZZeroUID TypedDict 里的
            # icon_paths 嵌套，那层是文档错位）。优先 role_square_url 方形头像，
            # 其次 hollow/group icon path 兜底。
            items.append(MihoyoCharacter(
                game="zzz", uid=uid,
                avatar_id=str(av.get("id", "")),
                name=str(av.get("name_mi18n", "") or av.get("full_name_mi18n", "")),
                element=str(av.get("element_type", "")),
                rarity=rarity_val,
                level=int(av.get("level", 1) or 1),
                constellation=int(av.get("rank", 0) or 0),
                weapon={},   # basic 接口不返，下轮从 /avatar/info 取
                relics=[],
                icon_url=str(
                    av.get("role_square_url", "")
                    or av.get("hollow_icon_path", "")
                    or av.get("group_icon_path", "")
                ),
                scan_ts=now_ts,
                raw=av,
            ))
        n = await self._ir.mihoyo_character_upsert(items, actor="水神")
        if avatars:
            a0 = avatars[0]
            # 把首个代理人的**全部 key** 打出来，米游社 basic 接口可能改版
            logger.info("[水神·游戏] 绝区零代理人入库 zzz/{} 共 {} 个 · debug 首代理 keys={}",
                        uid, n, sorted(a0.keys()))
            # 找含 path/icon/image/avatar 子串的字段值
            for k, v in a0.items():
                kl = k.lower()
                if "path" in kl or "icon" in kl or "image" in kl or "avatar" in kl:
                    vs = str(v)[:100] if not isinstance(v, dict) else json.dumps(v, ensure_ascii=False)[:120]
                    logger.info("[水神·游戏]   zzz debug {}: {}", k, vs)
        return n
