"""水神·游戏服务主类 FurinaGameService：__init__ + _run_skill + mixin 组合。

各业务领域方法按职责拆 6 个 mixin（account/note/battle/character/gacha/overview），
service.py 只保留实例状态 + skill 调用 helper。
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




from ._account import _AccountMixin
from ._battle import _BattleMixin
from ._character import _CharacterMixin
from ._gacha import _GachaMixin
from ._note import _NoteMixin
from ._overview import _OverviewMixin


class FurinaGameService(
    _AccountMixin, _NoteMixin, _BattleMixin, _CharacterMixin,
    _GachaMixin, _OverviewMixin,
):
    """游戏信息聚合服务。由 FurinaArchon 持有，WebUI / cron 直调。"""

    def __init__(self, irminsul: Irminsul):
        self._ir = irminsul
        # 扫码登录的中间态（ticket → {device, started_at}）
        self._pending_qr: dict[str, dict[str, Any]] = {}
        # 抽卡 background sync 状态机（key='game::uid' → {state, progress, ...}）
        self._gacha_sync_state: dict[str, dict[str, Any]] = {}
        # 「刷新此账号数据」background 状态机
        self._collect_state: dict[str, dict[str, Any]] = {}

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
