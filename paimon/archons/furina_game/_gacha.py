"""水神·游戏 · 抽卡同步 mixin（authkey 自动 / 手动 URL / 后台 worker / 统计）。"""
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


class _GachaMixin:
    async def auto_sync_gacha(
        self, uid: str, game: str = "gs",
        *, override_authkey: str | None = None, override_is_os: bool | None = None,
    ) -> dict[str, Any]:
        """拉抽卡全量 → 入库。

        - 默认路径：从已绑账号 stoken 自动换 authkey（参考 gsuid_core get_authkey_by_cookie）。
          GS/ZZZ 米哈游放行；SR 在 getGachaLog 接口被拒（米哈游限制）。
        - override_authkey：调用方直接提供 authkey（如从用户复制的 URL 解析），跳过 gen-authkey。
          SR 必走这条；GS/ZZZ 也可作 fallback。
        """
        from paimon.foundation.irminsul import MihoyoGacha as G
        from datetime import datetime as _dt

        logger.info(
            "[水神·游戏] 抽卡同步 auto_sync_gacha 进入 {}/{}  source={}",
            game, uid, "url" if override_authkey else "stoken",
        )

        if override_authkey:
            authkey = override_authkey
            is_os = override_is_os if override_is_os is not None else self._is_os(uid, game)
        else:
            acc = await self._ir.mihoyo_account_get(game, uid)
            if not acc:
                return {"ok": False, "msg": f"未绑定 {game}/{uid}"}
            if not acc.stoken or not acc.mys_id:
                return {"ok": False, "msg": "账号缺 stoken/mys_id，请重新扫码绑定"}
            mid = self._mid_from_cookie(acc.cookie)
            if not mid:
                return {"ok": False, "msg": "cookie 缺 mid，请重新扫码绑定"}
            is_os = self._is_os(uid, game)
            logger.info("[水神·游戏] 抽卡同步换 authkey {}/{}  is_os={}", game, uid, is_os)
            ak = await self._run_skill("gen-authkey", {
                "game": game, "uid": uid, "stoken": acc.stoken,
                "mys_id": acc.mys_id, "mid": mid, "is_os": is_os,
                "device_id": acc.device_id or None,
            })
            if not ak.get("ok"):
                # USB-001：retcode 数字 → 中文行动建议；与 _account._RETCODE_HINT 复用
                from ._account import _RETCODE_HINT
                rc = ak.get('retcode')
                msg = ak.get('msg', '')
                hint = _RETCODE_HINT.get(rc) or f"换 authkey 失败（retcode={rc} {msg}），请重新扫码绑定"
                logger.warning(
                    "[水神·游戏] 抽卡同步换 authkey 失败 {}/{}  retcode={} msg={}",
                    game, uid, rc, msg,
                )
                return {"ok": False, "msg": hint}
            authkey = ak["authkey"]

        pools = self._GACHA_POOLS_BY_GAME.get(game) or []
        if not pools:
            return {"ok": False, "msg": f"未知 game: {game}"}
        logger.info(
            "[水神·游戏] 抽卡同步开始拉取 {}/{}  pools={}",
            game, uid, [p[0] for p in pools],
        )

        summary: dict[str, int] = {}
        errors: dict[str, str] = {}
        # 状态机进度记录（前端轮询）
        sync_state = self._gacha_sync_state.get(self._gacha_sync_key(game, uid))
        for db_type, api_type in pools:
            since_id = await self._ir.mihoyo_gacha_max_id(game, uid, db_type)
            try:
                data = await self._run_skill("gacha-log", {
                    "authkey": authkey, "gacha_type": api_type,
                    "game": game, "is_os": is_os, "since_id": since_id,
                }, timeout=300)
            except Exception as e:
                summary[db_type] = -1
                errors[db_type] = str(e)
                logger.warning(
                    "[水神·游戏] 抽卡抓取失败 {}/{} api_type={}: {}",
                    game, uid, api_type, e,
                )
                if sync_state is not None:
                    sync_state["progress"] = dict(summary)
                    sync_state["errors"] = dict(errors)
                continue

            err = data.get("error")
            if err:
                summary[db_type] = -1
                errors[db_type] = f"retcode={err.get('retcode')} {err.get('message', '')}"
                logger.warning(
                    "[水神·游戏] 抽卡接口拒绝 {}/{} api_type={} retcode={} msg={!r}",
                    game, uid, api_type, err.get("retcode"), err.get("message"),
                )
                if sync_state is not None:
                    sync_state["progress"] = dict(summary)
                    sync_state["errors"] = dict(errors)
                continue

            items = data.get("items") or []
            to_save: list[G] = []
            for it in items:
                tstr = it.get("time", "")
                try:
                    ts = _dt.strptime(tstr, "%Y-%m-%d %H:%M:%S").timestamp()
                except Exception:
                    ts = 0.0
                to_save.append(G(
                    id=str(it.get("id", "")),
                    game=game,
                    uid=str(it.get("uid", uid)),
                    gacha_type=db_type,   # 入库统一用 base_type，避免 ZZZ 多期号脏数据
                    item_id=str(it.get("item_id", "")),
                    item_type=str(it.get("item_type", "")),
                    name=str(it.get("name", "")),
                    rank_type=int(it.get("rank_type", 3)),
                    time=tstr, time_ts=ts,
                    raw=it,
                ))
            n = await self._ir.mihoyo_gacha_insert(to_save, actor="水神")
            summary[db_type] = n
            if sync_state is not None:
                sync_state["progress"] = dict(summary)

        # 缓存 authkey（24h），后续增量同步可省一次换签
        await self._ir.mihoyo_account_update_authkey(
            uid, authkey, game=game, actor="水神",
        )
        result = {"ok": True, "uid": uid, "game": game, "summary": summary}
        if errors:
            result["errors"] = errors
        return result

    # ---------- 抽卡 background sync 状态机 ----------
    # 前端「同步抽卡」按钮 → start_gacha_sync 立即返回 → 前端轮询 status
    # 解决：旧版 fetch 阻塞 30s+ 导致刷新中断 + 看起来卡死

    @staticmethod
    def _gacha_sync_key(game: str, uid: str) -> str:
        return f"{game}::{uid}"

    async def start_gacha_sync(self, uid: str, game: str = "gs") -> dict[str, Any]:
        """启动后台同步任务（stoken→authkey 路径）。重复触发返 conflict。"""
        key = self._gacha_sync_key(game, uid)
        st = self._gacha_sync_state.get(key)
        if st and st.get("state") == "running":
            logger.info("[水神·游戏] 抽卡同步重复触发 {}/{}（已在跑，忽略）", game, uid)
            return {"ok": False, "msg": "已在同步中，请稍候"}
        acc = await self._ir.mihoyo_account_get(game, uid)
        if not acc:
            logger.warning("[水神·游戏] 抽卡同步预检失败 {}/{} 未绑定", game, uid)
            return {"ok": False, "msg": f"未绑定 {game}/{uid}"}
        if not acc.stoken or not acc.mys_id:
            logger.warning("[水神·游戏] 抽卡同步预检失败 {}/{} stoken/mys_id 缺失", game, uid)
            return {"ok": False, "msg": "账号缺 stoken/mys_id，请重新扫码绑定"}
        self._gacha_sync_state[key] = {
            "state": "running", "progress": {}, "errors": {},
            "started_at": time.time(),
        }
        logger.info("[水神·游戏] 抽卡同步启动 {}/{}（stoken）", game, uid)
        from paimon.foundation.bg import bg
        bg(self._gacha_sync_worker(uid, game, key), label=f"furina·gacha·stoken·{game}·{uid}")
        return {"ok": True}

    async def start_gacha_sync_from_url(
        self, uid: str, game: str, gacha_url: str,
    ) -> dict[str, Any]:
        """启动后台同步任务（URL 路径）。SR 必走，GS/ZZZ 也可作 fallback。"""
        key = self._gacha_sync_key(game, uid)
        st = self._gacha_sync_state.get(key)
        if st and st.get("state") == "running":
            return {"ok": False, "msg": "已在同步中，请稍候"}
        # 解析 authkey
        parsed = await self._run_skill("parse-authkey", {"url": gacha_url})
        if not parsed.get("ok"):
            return {"ok": False, "msg": "URL 中没解析到 authkey，请检查链接是否含 authkey=... 参数"}
        authkey = parsed["authkey"]
        is_os = bool(parsed.get("is_os", False))
        self._gacha_sync_state[key] = {
            "state": "running", "progress": {}, "errors": {},
            "started_at": time.time(),
        }
        logger.info(
            "[水神·游戏] 抽卡同步启动 {}/{}（URL 导入）  authkey_len={} is_os={}",
            game, uid, len(authkey), is_os,
        )
        from paimon.foundation.bg import bg
        bg(self._gacha_sync_worker(
            uid, game, key, override_authkey=authkey, override_is_os=is_os,
        ), label=f"furina·gacha·url·{game}·{uid}")
        return {"ok": True}

    async def _gacha_sync_worker(
        self, uid: str, game: str, key: str,
        *, override_authkey: str | None = None, override_is_os: bool | None = None,
    ) -> None:
        try:
            result = await self.auto_sync_gacha(
                uid, game=game,
                override_authkey=override_authkey,
                override_is_os=override_is_os,
            )
            self._gacha_sync_state[key].update({
                "state": "done", "result": result, "ended_at": time.time(),
            })
            logger.info(
                "[水神·游戏] 抽卡同步完成 {}/{}  summary={} errors={}",
                game, uid, result.get("summary"), result.get("errors"),
            )
        except Exception as e:
            logger.exception("[水神·游戏] 抽卡同步异常 {}/{}", game, uid)
            self._gacha_sync_state[key].update({
                "state": "failed", "error": str(e), "ended_at": time.time(),
            })

    def get_gacha_sync_state(self, uid: str, game: str = "gs") -> dict[str, Any]:
        key = self._gacha_sync_key(game, uid)
        return self._gacha_sync_state.get(key) or {"state": "idle"}

    async def gacha_stats(
        self, game: str, uid: str, gacha_type: str,
    ) -> dict[str, Any]:
        """取抽卡统计（小保底/总数/历次 5 星）。"""
        return await self._ir.mihoyo_gacha_stats(game, uid, gacha_type)
