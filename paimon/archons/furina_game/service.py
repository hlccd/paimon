"""水神·游戏服务主类 FurinaGameService：__init__ + _run_skill + mixin 组合。

各业务领域方法按职责拆 6 个 mixin（account/note/battle/character/gacha/overview），
service.py 只保留实例状态 + skill 调用 helper。

SEC-014 subprocess env 黑名单：
- 旧版 `{**os.environ, ...}` 全 env 透传，cookie/token/api_key 类敏感环境变量
  会泄漏到 mihoyo / dividend-tracker skill 子进程
- 第一版改白名单导致 Windows Python 子进程缺 APPDATA / LOCALAPPDATA 等系统必需 env
  连 import asyncio 都失败（实测崩 dividend-tracker daily_update）
- 现版改黑名单：保留所有系统 env 让子进程能正常运行，只剔除 *_KEY / *_TOKEN /
  *_SECRET / *_PASSWORD 等敏感模式 + 显式 OPENAI/ANTHROPIC/CLAUDE/DEEPSEEK/MIMO
  类 LLM 凭据
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import sys
import time
from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING, Any

from loguru import logger


# SEC-014 敏感 env 黑名单：命中名字模式即剔除
# 设计：宁多留几个无害的（PATH/APPDATA/...）也不能少给 Python 必需的；
# 只挡命名上明显是凭据/密钥/会话 token 的变量
_ENV_BLOCKLIST_RE = re.compile(
    r"(?:"
    r"_KEY$|_TOKEN$|_SECRET$|_PASSWORD$|_PASSWD$|_PASS$|"
    r"_API_KEY$|_AUTH$|_AUTHKEY$|_BEARER$|_CREDENTIAL$|"
    r"^OPENAI_|^ANTHROPIC_|^CLAUDE_|^DEEPSEEK_|^MIMO_|"
    r"^GROQ_|^GEMINI_|^AZURE_OPENAI_|"
    r"COOKIE|STOKEN|AUTHKEY|MYS_ID"
    r")",
    re.IGNORECASE,
)


def _safe_env(extra: dict[str, str] | None = None) -> dict[str, str]:
    """从 os.environ 剔除敏感凭据后叠加 extra 透传给子进程。

    阻断 LLM API key / cookie / stoken 等敏感环境变量泄漏到 skill 子进程，
    同时保留所有 Windows/Python 系统运行必需的 env（APPDATA/LOCALAPPDATA/PATH 等）。
    """
    env: dict[str, str] = {
        k: v for k, v in os.environ.items() if not _ENV_BLOCKLIST_RE.search(k)
    }
    if extra:
        env.update(extra)
    return env

from paimon.foundation.irminsul import (
    Irminsul, MihoyoAbyss, MihoyoAccount, MihoyoCharacter, MihoyoGacha, MihoyoNote,
)

if TYPE_CHECKING:
    from paimon.foundation.march import MarchService


# 路径：paimon/archons/furina_game/service.py → 上 4 级到项目根 → skills/mihoyo/main.py
_SKILL_MIHOYO = (
    Path(__file__).resolve().parent.parent.parent.parent / "skills" / "mihoyo" / "main.py"
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

    # 树脂满量报警比例：current_resin / max_resin >= 此值 → 推送（_note.py:75 引用）
    # e037ba1 拆子包时漏迁移此常量
    _FULL_RATIO = 0.9

    # 抽卡池表（_gacha.py:68 引用）：{game: [(db_type 内部标识, api_type mihoyo 卡池 ID)]}
    # 参考 skills/mihoyo/mihoyo/actions.py:693 GACHA_TYPES_* 重建（同样是 e037ba1 漏迁移）
    _GACHA_POOLS_BY_GAME: dict[str, list[tuple[str, str]]] = {
        "gs": [
            ("character", "301"), ("weapon", "302"),
            ("permanent", "200"), ("chronicled", "500"),
        ],
        "sr": [
            ("character", "11"), ("lightcone", "12"), ("permanent", "1"),
        ],
        "zzz": [
            ("agent", "2"), ("wengine", "3"),
            ("permanent", "1"), ("bangboo", "5"),
        ],
    }

    def __init__(self, irminsul: Irminsul):
        self._ir = irminsul
        # 扫码登录的中间态（ticket → {device, started_at}）
        # REL-005 加锁：多 user 同时扫码时 dict 写竞争
        self._pending_qr: dict[str, dict[str, Any]] = {}
        self._pending_qr_lock = asyncio.Lock()
        # 抽卡 background sync 状态机（key='game::uid' → {state, progress, ...}）
        self._gacha_sync_state: dict[str, dict[str, Any]] = {}
        # 「刷新此账号数据」background 状态机
        self._collect_state: dict[str, dict[str, Any]] = {}
        # 后台 GC 任务句柄（lazy 启动；首次调 _ensure_qr_gc 起）
        self._qr_gc_task: asyncio.Task | None = None

    def _ensure_qr_gc(self) -> None:
        """启动后台 GC 任务（每 60s 清理过期 _pending_qr）。幂等。

        REL-005 修复：旧实现仅 qr_create 时清理，user 不再 create 时旧 ticket 永留。
        """
        if self._qr_gc_task is not None and not self._qr_gc_task.done():
            return
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return  # 无运行 loop（应该不会发生在业务路径）
        from paimon.foundation.bg import bg
        self._qr_gc_task = bg(self._qr_gc_loop(), label="furina_game·qr_gc")

    async def _qr_gc_loop(self) -> None:
        """每 60s 扫一次，清理超过 600s 的 pending QR ticket。"""
        while True:
            try:
                await asyncio.sleep(60)
            except asyncio.CancelledError:
                return
            now = time.time()
            async with self._pending_qr_lock:
                stale = [
                    k for k, v in self._pending_qr.items()
                    if now - v.get("started_at", 0) > 600
                ]
                for k in stale:
                    self._pending_qr.pop(k, None)
            if stale:
                logger.debug("[水神·游戏] _pending_qr GC 清理 {} 条", len(stale))

    # ===================== skill 桥接 =====================

    async def _run_skill(
        self, cmd: str, payload: dict | None = None, *, timeout: int = 60,
    ) -> dict:
        """subprocess 调 mihoyo skill，stdin 传 JSON，stdout 读 JSON。"""
        if not _SKILL_MIHOYO.exists():
            raise RuntimeError(f"mihoyo skill 不存在: {_SKILL_MIHOYO}")

        env = _safe_env({"PAIMON_SKILL_RUNTIME": "1", "PYTHONIOENCODING": "utf-8"})
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
