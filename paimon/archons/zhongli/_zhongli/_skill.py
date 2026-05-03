"""岩神 · skill 调用层 mixin：subprocess 跑 dividend-tracker.main.py 6 个动作。"""
from __future__ import annotations

import asyncio
import json
import os
import re
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any

from loguru import logger

from paimon.archons.zhongli.scorer import (
    build_advice, build_reasons, classify_stock, score_stock,
)
from paimon.foundation.irminsul import (
    ChangeEvent, ScoreSnapshot, UserWatchPrice, WatchlistEntry,
)


# skill CLI 入口（原 zhongli.py 顶部；mixin 拆分后留在使用方 _skill.py 内）
# 路径：paimon/archons/zhongli/_zhongli/_skill.py → 上 5 级到项目根 → skills/dividend-tracker/main.py
_SKILL_MAIN_PY = (
    Path(__file__).resolve().parent.parent.parent.parent.parent
    / "skills" / "dividend-tracker" / "main.py"
)
# subprocess 活性超时：连续 5 分钟无 stderr 活动才 kill。
_SKILL_IDLE_TIMEOUT = 5 * 60


if TYPE_CHECKING:
    from paimon.foundation.irminsul import Irminsul
    from paimon.foundation.march import MarchService
    from paimon.llm.model import Model


class _SkillMixin:
    async def _run_skill(self, args: list[str]) -> dict:
        """调 skill main.py 子进程，返回解析后的 JSON dict。

        - stderr 透传到 paimon 日志，并解析 ``PROGRESS: {...}`` 行 update self._progress
        - 活性超时：连续 _SKILL_IDLE_TIMEOUT 秒无 stderr 活动才 kill（旧版用全程死线，
          BaoStock 速率方差太大会错杀）
        - 子进程环境：PAIMON_SKILL_RUNTIME=1 让 skill loguru 切极简 format（避免双重时间戳）；
          PYTHONIOENCODING=utf-8 兜底 Windows cp936 中文乱码
        """
        if not _SKILL_MAIN_PY.exists():
            raise RuntimeError(f"skill 入口不存在: {_SKILL_MAIN_PY}")

        cmd = [sys.executable, str(_SKILL_MAIN_PY), *args]
        skill_tag = args[0] if args else "skill"
        logger.info("[岩神·skill/{}] 启动子进程 args={}", skill_tag, args)
        start_ts = time.time()
        # SEC-014 env 白名单透传（与 furina_game 复用同一 helper）
        from paimon.archons.furina_game.service import _safe_env
        env = _safe_env({"PAIMON_SKILL_RUNTIME": "1", "PYTHONIOENCODING": "utf-8"})
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
        )

        stdout_chunks: list[bytes] = []
        stderr_chunks: list[bytes] = []
        last_activity_ts = time.time()

        async def _pump_stdout() -> None:
            """收 stdout 到内存（JSON 完整拿回来再 parse，不流式打日志避免刷屏）。"""
            assert proc.stdout is not None
            while True:
                chunk = await proc.stdout.read(8192)
                if not chunk:
                    break
                stdout_chunks.append(chunk)

        async def _pump_stderr() -> None:
            """stderr 按行实时打 paimon INFO + 解析 PROGRESS 行更新进度。"""
            nonlocal last_activity_ts
            assert proc.stderr is not None
            async for raw_line in proc.stderr:
                last_activity_ts = time.time()  # 续命
                line = raw_line.decode("utf-8", "ignore").rstrip()
                stderr_chunks.append(raw_line)
                if not line:
                    continue
                # PROGRESS: {...} 是 skill 给 paimon 的结构化信号，不打日志（噪音）
                if line.startswith("PROGRESS: "):
                    try:
                        prog = json.loads(line[len("PROGRESS: "):])
                        if isinstance(prog, dict) and "stage" in prog:
                            self._set_progress(
                                prog["stage"],
                                int(prog.get("cur", 0)),
                                int(prog.get("total", 0)),
                                **{k: v for k, v in prog.items()
                                   if k not in ("stage", "cur", "total")},
                            )
                    except (json.JSONDecodeError, ValueError, TypeError):
                        pass
                    continue
                logger.info("[岩神·skill/{}] {}", skill_tag, line[:500])

        async def _watchdog() -> None:
            """每 30s 检查一次活性 + 打心跳；连续 _SKILL_IDLE_TIMEOUT 秒无 stderr 活动 → kill。"""
            while True:
                try:
                    await asyncio.sleep(30)
                except asyncio.CancelledError:
                    return
                idle = time.time() - last_activity_ts
                elapsed = time.time() - start_ts
                if idle > _SKILL_IDLE_TIMEOUT:
                    logger.error(
                        "[岩神·skill/{}] {:.0f}s 无 stderr 活动，判定卡死，kill",
                        skill_tag, idle,
                    )
                    proc.kill()
                    return
                logger.info(
                    "[岩神·skill/{}] 仍在运行 {:.0f}s（{:.0f}s 前最后活动；空闲超 {:.0f}s 即 kill）",
                    skill_tag, elapsed, idle, _SKILL_IDLE_TIMEOUT,
                )

        wd_task = asyncio.create_task(_watchdog())
        try:
            await asyncio.gather(_pump_stdout(), _pump_stderr(), proc.wait())
        finally:
            wd_task.cancel()
            try:
                await wd_task
            except asyncio.CancelledError:
                pass

        out_b = b"".join(stdout_chunks)
        err_b = b"".join(stderr_chunks)
        elapsed = time.time() - start_ts
        logger.info(
            "[岩神·skill/{}] 结束 rc={} 耗时={:.1f}s stdout={}B stderr={}B",
            skill_tag, proc.returncode, elapsed, len(out_b), len(err_b),
        )

        rc = proc.returncode or 0
        if rc != 0:
            err_txt = (err_b or b"").decode("utf-8", "ignore").strip()
            # watchdog kill 时 returncode 通常为 -9 / -SIGKILL，给明确错误
            if rc < 0:
                raise RuntimeError(
                    f"skill 子进程被活性 watchdog kill（{_SKILL_IDLE_TIMEOUT}s 无活动）: {args}"
                )
            raise RuntimeError(f"skill 退出码 {rc}: {err_txt[:400]}")

        out_txt = (out_b or b"").decode("utf-8", "ignore").strip()
        if not out_txt:
            return {}
        # BaoStock CLI 登录成功时会往 stdout 打 "login success!\n" 污染 JSON，
        # 从首个 '{' 或 '[' 开始解析跳过非 JSON 前缀
        json_start = -1
        for i, ch in enumerate(out_txt):
            if ch in "{[":
                json_start = i
                break
        if json_start < 0:
            return {}
        json_txt = out_txt[json_start:]
        try:
            return json.loads(json_txt)
        except json.JSONDecodeError as e:
            raise RuntimeError(
                f"skill 输出非 JSON: {e}; head={json_txt[:200]}"
            ) from e

    async def _skill_fetch_board(self) -> dict:
        """全市场抓（full_scan 用）。"""
        return await self._run_skill(["fetch-board"])

    async def _skill_fetch_board_by_codes(self, codes: list[str]) -> dict:
        """只抓指定股票行情（daily_update 用，走 skill fetch-board --codes）。"""
        if not codes:
            return {"industry_map": {}, "market_data": {}, "count": 0}
        args = ["fetch-board", "--codes", ",".join(codes)]
        return await self._run_skill(args)

    async def _skill_fetch_dividend(
        self, codes: list[str], cached_only: bool = False,
    ) -> dict[str, dict]:
        if not codes:
            return {}
        args = ["fetch-dividend", "--codes", ",".join(codes)]
        if cached_only:
            args.append("--cached-only")
        data = await self._run_skill(args)
        return data.get('dividends', {})

    async def _skill_fetch_financial(
        self, codes: list[str], cached_only: bool = False,
    ) -> dict[str, dict]:
        if not codes:
            return {}
        args = ["fetch-financial", "--codes", ",".join(codes)]
        if cached_only:
            args.append("--cached-only")
        data = await self._run_skill(args)
        return data.get('financials', {})

    async def _skill_cleanup_cache(self) -> None:
        try:
            await self._run_skill(["cleanup-cache"])
        except Exception as e:
            logger.warning("[岩神·采集] 清缓存失败（可忽略）: {}", e)

    async def _skill_fetch_stock_detail(
        self, codes: list[str], start_date: str, end_date: str,
    ) -> dict[str, dict]:
        """用户关注股：拉 start→end 区间日 K。返回 {code: {"name": str, "rows": [rows]}}。"""
        if not codes:
            return {}
        args = [
            "fetch-stock-detail",
            "--codes", ",".join(codes),
            "--start-date", start_date,
            "--end-date", end_date,
        ]
        data = await self._run_skill(args)
        return data.get('histories', {})
