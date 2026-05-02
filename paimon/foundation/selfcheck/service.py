"""三月自检服务主类 SelfCheckService：Quick 探针 + Deep skill 触发器 + 查询 API。

state.selfcheck 单例。Quick/Deep 实现委托到 _probes.py / _deep.py 子模块；
本文件只负责薄入口 + 单例锁 + 查询。
"""
from __future__ import annotations

import asyncio
import json
import time
from typing import TYPE_CHECKING
from uuid import uuid4

from loguru import logger

if TYPE_CHECKING:
    from paimon.config import Config
    from paimon.foundation.irminsul import Irminsul
    from paimon.foundation.irminsul.selfcheck import SelfcheckRun
    from paimon.foundation.march import MarchService
    from paimon.llm.model import Model


class SelfCheckService:
    """三月自检服务。state.selfcheck 单例。"""

    def __init__(
        self, cfg: "Config", irminsul: "Irminsul",
        model: "Model", march: "MarchService | None" = None,
    ):
        self._cfg = cfg
        self._irminsul = irminsul
        self._model = model
        self._march = march
        # Deep 全局单例占用标志（手动 + cron + 面板共用）
        # 用同步 bool 而非 asyncio.Lock：确保"已在跑 → 立即拒绝"语义，
        # 避免 Lock 的 acquire 排队导致第 2 次触发仍会在第 1 次完成后继续跑。
        self._deep_busy: bool = False

    # ==================== Quick ====================

    async def run_quick(self, *, triggered_by: str = "user") -> "SelfcheckRun":
        """秒级组件探针。不抛异常，失败组件标 critical。

        写 selfcheck_runs + blob quick_snapshot.json + audit；触发 GC。
        """
        from paimon.foundation.irminsul import SelfcheckRun
        from ._probes import probe_all

        run_id = uuid4().hex[:12]
        t0 = time.time()

        run = SelfcheckRun(
            id=run_id, kind="quick", triggered_at=t0,
            triggered_by=triggered_by, status="running",
        )
        await self._irminsul.selfcheck_create(run, actor="三月·自检")

        try:
            snapshot = await probe_all(self)
            run.duration_seconds = snapshot.duration_seconds
            run.status = "completed"
            run.quick_summary = {
                "overall": snapshot.overall,
                "warnings": snapshot.warnings,
                "components": [
                    {"name": c.name, "status": c.status,
                     "latency_ms": c.latency_ms}
                    for c in snapshot.components
                ],
            }

            # blob 落盘完整快照
            blob = self._irminsul.selfcheck_ensure_blob_dir(run_id)
            try:
                (blob / "quick_snapshot.json").write_text(
                    json.dumps(snapshot.to_dict(), ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
            except OSError as e:
                logger.warning("[三月·自检] blob 写失败 {}: {}", run_id, e)

            await self._irminsul.selfcheck_update(
                run_id, actor="三月·自检",
                status="completed",
                duration_seconds=run.duration_seconds,
                quick_summary=run.quick_summary,
            )
            await self._irminsul.audit_append(
                event_type="selfcheck_quick",
                payload={
                    "run_id": run_id,
                    "overall": snapshot.overall,
                    "duration_seconds": round(snapshot.duration_seconds, 3),
                    "warnings": snapshot.warnings,
                },
                actor="三月·自检",
            )

            # 保留策略 GC（失败不影响主流程）
            try:
                await self._irminsul.selfcheck_gc(
                    kind="quick",
                    keep_n=max(1, int(self._cfg.selfcheck_quick_retention)),
                    actor="三月·自检",
                )
            except Exception as e:
                logger.warning("[三月·自检] Quick GC 失败: {}", e)

            logger.info(
                "[三月·自检] Quick 完成 run={} overall={} 耗时={:.3f}s",
                run_id, snapshot.overall, snapshot.duration_seconds,
            )
            return run

        except Exception as e:
            # 罕见：探针调度本身异常；单组件异常不会走到这里
            logger.exception("[三月·自检] Quick 调度异常 run={}: {}", run_id, e)
            run.status = "failed"
            run.error = str(e)[:500]
            run.duration_seconds = time.time() - t0
            await self._irminsul.selfcheck_update(
                run_id, actor="三月·自检",
                status="failed", error=run.error,
                duration_seconds=run.duration_seconds,
            )
            return run

    # ==================== Deep ====================

    async def run_deep(
        self, args: str | None = None, *, triggered_by: str = "user",
    ) -> dict:
        """启动 Deep 自检。并发触发返 already_running=True 立即拒绝。

        返回 {"run_id": ..., "started": True/False, "reason": ...}
        实际跑在独立 asyncio.Task 里，不阻塞调用者。

        并发保护用同步 bool（不是 asyncio.Lock）：入口就占坑，避免 Lock
        acquire 排队——两个并发调用如果用 Lock，第 2 个会被阻塞排队而不是拒绝。
        """
        # 同步占坑：入口 check+set 之间没有 await，single-threaded asyncio 下原子
        if self._deep_busy:
            return {
                "run_id": "", "started": False,
                "reason": "already_running",
            }
        self._deep_busy = True

        try:
            use_args = args or self._cfg.selfcheck_deep_check_args
            run_id = uuid4().hex[:12]
            from ._deep import run_deep_inner
            task = asyncio.create_task(
                run_deep_inner(self, run_id, use_args, triggered_by=triggered_by),
                name=f"selfcheck_deep_{run_id}",
            )
            # 挂到 state.session_tasks 便于 shutdown 取消（_run_deep_inner finally 里清理）
            from paimon.state import state
            state.session_tasks[f"selfcheck_deep_{run_id}"] = task
            return {"run_id": run_id, "started": True, "reason": ""}
        except Exception:
            # create_task 失败（罕见）或 uuid 生成失败，立即释放 busy
            self._deep_busy = False
            raise

    # ==================== 查询（供命令 / 面板 ====================

    async def list_runs(
        self, *, kind: str | None = None, limit: int = 50, offset: int = 0,
    ) -> list["SelfcheckRun"]:
        """分页列 run 记录（kind 过滤可选）。"""
        return await self._irminsul.selfcheck_list(
            kind=kind, limit=limit, offset=offset,
        )

    async def count_runs(self, *, kind: str | None = None) -> int:
        """count 总数；面板分页用。"""
        return await self._irminsul.selfcheck_count(kind=kind)

    async def latest_run(self, kind: str) -> "SelfcheckRun | None":
        """单 kind 最新一条 run。"""
        return await self._irminsul.selfcheck_latest(kind)

    async def get_run(self, run_id: str) -> "SelfcheckRun | None":
        """按 id 取详情。"""
        return await self._irminsul.selfcheck_get(run_id)

    async def get_report(self, run_id: str) -> str | None:
        """读归档目录的 report.md；不存在返 None。"""
        blob = self._irminsul.selfcheck_blob_dir(run_id)
        p = blob / "report.md"
        try:
            return p.read_text(encoding="utf-8") if p.exists() else None
        except OSError:
            return None

    async def get_findings(self, run_id: str) -> list[dict]:
        """读归档 candidates.jsonl 并解析为 findings 列表。"""
        from paimon.shades._check_parser import (
            parse_candidates_file, sort_by_severity,
        )
        blob = self._irminsul.selfcheck_blob_dir(run_id)
        p = blob / "candidates.jsonl"
        if not p.exists():
            return []
        return sort_by_severity(parse_candidates_file(p))

    async def get_quick_snapshot(self, run_id: str) -> dict | None:
        """读 quick 归档 JSON。"""
        blob = self._irminsul.selfcheck_blob_dir(run_id)
        p = blob / "quick_snapshot.json"
        if not p.exists():
            return None
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None

    async def delete_run(self, run_id: str) -> bool:
        """删 run 记录 + blob 目录（不可逆）。"""
        return await self._irminsul.selfcheck_delete(run_id, actor="三月·自检")

    def is_deep_running(self) -> bool:
        """Deep 是否在跑（面板 / cron 用来判是否能再触发）。"""
        return self._deep_busy
