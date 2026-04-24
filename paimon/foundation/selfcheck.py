"""三月·自检系统 —— 服务层

docs/foundation/march.md §自检体系

两档自检：
- Quick：秒级纯代码组件探针，零 LLM；每次写 audit + 归档到世界树域 12
- Deep ：调 check skill（参数模式 project-health）跑项目体检，产物 .check/report.md
         快照进归档目录供面板查看；独立 asyncio.Task，全局单例锁防并发

归档：元数据 → selfcheck_runs 表；原始产物（report.md / candidates.jsonl / state.json /
quick_snapshot.json）→ <paimon_home>/irminsul/selfcheck/{run_id}/
"""
from __future__ import annotations

import asyncio
import json
import platform
import shutil
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from loguru import logger

if TYPE_CHECKING:
    from paimon.config import Config
    from paimon.foundation.irminsul import Irminsul
    from paimon.foundation.irminsul.selfcheck import SelfcheckRun
    from paimon.foundation.march import MarchService
    from paimon.llm.model import Model


# check skill 在 target 路径写 .check/ 目录；Deep selfcheck 的 target 是项目根
_CHECK_DIR_NAME = ".check"
_CHECK_FILES = ("report.md", "candidates.jsonl", "state.json")

# 进度 watcher 轮询间隔（秒）；check skill 每轮都会重写 state.json
_PROGRESS_POLL_INTERVAL = 5.0


def _platform_exec_hint() -> str:
    """按当前平台返回给 LLM 的 shell 使用提示。

    不同平台 LLM 默认偏好的命令不同：LLM 常用 Unix 风格（find/ls/grep），
    在 Windows 下这些要么不存在要么语义迥异 → 失败 → 无法列文件 → Deep 跑空。
    在 Linux/macOS 下 Unix 命令全可用，但仍建议优先 `file_ops(list)` 获得结构化输出。
    """
    sysname = platform.system()  # 'Windows' / 'Linux' / 'Darwin'
    if sysname == "Windows":
        return (
            "当前运行环境: **Windows**（shell = PowerShell 或 cmd）\n"
            "- **列目录用 `file_ops(action=\"list\", path=...)`，禁用 shell `find`/`ls`**\n"
            "  Windows 的 `find` 语义与 Unix 完全不同（`FIND: Parameter format not correct`），\n"
            "  `cmd` 没 `ls`，PowerShell 的 `ls -la` 语法也不对 → 只会返回错误文本\n"
            "- **避免 Unix-only 命令**：find / ls -la / mkdir -p / date -u / `&&`\n"
            "  需要链式用 `;`；需要时间戳直接取消（不重要）\n"
            "- **多行 Python 脚本用文件**：`python -c \"多行...\"` 在 PowerShell 下引号\n"
            "  转义易坏；复杂逻辑用 `file_ops(write)` 写临时 .py → `exec python xxx.py`"
        )
    # Linux / macOS / 其他 POSIX
    return (
        f"当前运行环境: **{sysname}**（POSIX shell）\n"
        "- Unix 命令全可用：find / ls / grep / rg / mkdir -p / && 等\n"
        "- **列目录仍优先 `file_ops(action=\"list\", path=...)`** —— 返回结构化数组\n"
        "  比解析 shell 输出更可靠；只有需要通配/递归时才走 `find`\n"
        "- 多行 `python -c` 在 POSIX shell 正常工作，可放心用\n"
        "- 能用 `file_ops` 的不要走 `exec`（跨平台一致 + 路径安全检查）"
    )


def _extract_progress(state: Any) -> dict[str, Any]:
    """从 check skill 的 state.json 抽面板展示需要的字段（容错：缺字段默认 0/空）。

    入参容错：若 state 不是 dict（LLM 可能错写成 list/str/null），返回空 dict，
    避免调用方 watcher 打出 AttributeError 噪音日志。

    关键字段：
    - current_iteration / max_iter：当前是第几大轮，上限几轮
    - consecutive_clean / clean_iter：连续 clean 数（达 clean_iter 即停止）
    - iterations_done：已完成迭代数（= iteration_state.iterations 长度）
    - total_candidates / total_confirmed：累计候选/确认
    - severity_counts：实时 P0-P3 计数
    - modules_processed：当前已扫过的 module 列表（进度颗粒度最细的信号）
    - engine_status：哪个引擎在活跃（discovery / alignment / opportunity）
    """
    if not isinstance(state, dict):
        return {}
    it = state.get("iteration_state") or {}
    cfg = state.get("iteration_config") or {}
    cum = state.get("cumulative") or {}
    sev = state.get("severity_counts") or {}
    engines = state.get("engines") or {}
    # 子字段也做 isinstance 兜底（LLM 可能把 iteration_state 写成 list 等）
    if not isinstance(it, dict): it = {}
    if not isinstance(cfg, dict): cfg = {}
    if not isinstance(cum, dict): cum = {}
    if not isinstance(sev, dict): sev = {}
    if not isinstance(engines, dict): engines = {}
    discovery = engines.get("discovery") or {}
    if not isinstance(discovery, dict): discovery = {}

    return {
        "skill_status": state.get("status", "unknown"),  # 不跟 SelfcheckRun.status 混名
        "current_iteration": int(it.get("current_iteration", 0) or 0),
        "consecutive_clean": int(it.get("consecutive_clean", 0) or 0),
        "iterations_done": len(it.get("iterations") or []),
        "max_iter": int(cfg.get("max_iter", 0) or 0),
        "clean_iter": int(cfg.get("clean_iter", 0) or 0),
        "discovery_rounds": int(cfg.get("discovery_rounds", 0) or 0),
        "validation_rounds": int(cfg.get("validation_rounds", 0) or 0),
        "total_candidates": int(cum.get("total_candidates", 0) or 0),
        "total_confirmed": int(cum.get("total_confirmed", 0) or 0),
        "total_rejected": int(cum.get("total_rejected", 0) or 0),
        "total_deferred": int(cum.get("total_deferred", 0) or 0),
        "p0": int(sev.get("p0", 0) or 0),
        "p1": int(sev.get("p1", 0) or 0),
        "p2": int(sev.get("p2", 0) or 0),
        "p3": int(sev.get("p3", 0) or 0),
        "modules_processed": list(discovery.get("modules_processed") or []),
        "updated_at": state.get("updated_at"),
        "polled_at": time.time(),
    }


@dataclass
class ComponentProbe:
    """Quick 探针的单组件结果。"""
    name: str
    status: str = "ok"             # 'ok' | 'degraded' | 'critical'
    latency_ms: float = 0.0
    details: dict[str, Any] = field(default_factory=dict)
    error: str = ""


@dataclass
class QuickSnapshot:
    ts: float = 0.0
    overall: str = "ok"            # 派生：任一 critical → critical；任一 degraded → degraded；否则 ok
    duration_seconds: float = 0.0
    components: list[ComponentProbe] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "ts": self.ts,
            "overall": self.overall,
            "duration_seconds": self.duration_seconds,
            "components": [
                {
                    "name": c.name, "status": c.status,
                    "latency_ms": c.latency_ms,
                    "details": c.details, "error": c.error,
                }
                for c in self.components
            ],
            "warnings": self.warnings,
        }


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
        run_id = uuid4().hex[:12]
        t0 = time.time()

        run = SelfcheckRun(
            id=run_id, kind="quick", triggered_at=t0,
            triggered_by=triggered_by, status="running",
        )
        await self._irminsul.selfcheck_create(run, actor="三月·自检")

        try:
            snapshot = await self._probe_all()
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

    # ---------- Quick 探针 ----------

    async def _probe_all(self) -> QuickSnapshot:
        """9 组件探针并发 + 收集。整体 < 1s。"""
        t0 = time.time()
        probes = await asyncio.gather(
            self._probe_irminsul(),
            self._probe_leyline(),
            self._probe_gnosis(),
            self._probe_march(),
            self._probe_session_mgr(),
            self._probe_skill_registry(),
            self._probe_authz_cache(),
            self._probe_channels(),
            self._probe_paimon_home(),
            return_exceptions=True,
        )
        components: list[ComponentProbe] = []
        for p in probes:
            if isinstance(p, BaseException):
                components.append(ComponentProbe(
                    name="?", status="critical", error=str(p)[:300],
                ))
            else:
                components.append(p)

        # overall 派生
        statuses = {c.status for c in components}
        if "critical" in statuses:
            overall = "critical"
        elif "degraded" in statuses:
            overall = "degraded"
        else:
            overall = "ok"

        # warnings：非 ok 组件名字拼一下
        warnings: list[str] = []
        for c in components:
            if c.status != "ok":
                msg = f"{c.name}: {c.status}"
                if c.error:
                    msg += f" ({c.error[:120]})"
                warnings.append(msg)

        return QuickSnapshot(
            ts=t0, overall=overall,
            duration_seconds=time.time() - t0,
            components=components, warnings=warnings,
        )

    @staticmethod
    def _timed_probe(name: str):
        """装饰器：try/except + 测延时 + 构造 ComponentProbe。"""
        def wrapper(fn):
            async def inner(self) -> ComponentProbe:
                t = time.time()
                try:
                    details = await fn(self) or {}
                    # fn 可以返回 {"status": "degraded", "details": {...}, "error": "..."} 以主动降级
                    if isinstance(details, dict) and "status" in details:
                        status = details.get("status", "ok")
                        err = details.get("error", "")
                        det = details.get("details", {})
                    else:
                        status, err, det = "ok", "", details
                    return ComponentProbe(
                        name=name, status=status,
                        latency_ms=(time.time() - t) * 1000,
                        details=det, error=err,
                    )
                except Exception as e:
                    return ComponentProbe(
                        name=name, status="critical",
                        latency_ms=(time.time() - t) * 1000,
                        error=str(e)[:300],
                    )
            return inner
        return wrapper

    @_timed_probe("irminsul")
    async def _probe_irminsul(self) -> dict:
        db = self._irminsul._db
        if not db:
            return {"status": "critical", "error": "db 未初始化"}
        async with db.execute("SELECT 1") as cur:
            await cur.fetchone()
        # 12 域 count（尽量轻）
        counts: dict[str, int] = {}
        for tbl in (
            "authz_records", "skill_declarations", "memory_index",
            "task_edicts", "task_subtasks", "token_usage", "audit_revisions",
            "scheduled_tasks", "subscriptions", "feed_items",
            "session_records", "selfcheck_runs",
        ):
            try:
                async with db.execute(f"SELECT COUNT(*) FROM {tbl}") as cur:
                    row = await cur.fetchone()
                counts[tbl] = int(row[0]) if row else 0
            except Exception as e:
                counts[tbl] = -1
                logger.debug("[探针·irminsul] 表 {} count 失败: {}", tbl, e)

        db_path = self._irminsul._db_path
        db_bytes = db_path.stat().st_size if db_path.exists() else 0

        return {"tables": counts, "db_bytes": db_bytes}

    @_timed_probe("leyline")
    async def _probe_leyline(self) -> dict:
        from paimon.state import state
        ly = state.leyline
        if not ly:
            return {"status": "critical", "error": "leyline 未初始化"}
        if not getattr(ly, "_running", False):
            return {
                "status": "degraded",
                "error": "事件循环未运行",
                "details": {"subscribers": {}},
            }
        subs: dict[str, int] = {
            topic: len(hs) for topic, hs in ly._handlers.items() if hs
        }
        return {"subscribers": subs, "subscriber_total": sum(subs.values())}

    @_timed_probe("gnosis")
    async def _probe_gnosis(self) -> dict:
        from paimon.state import state
        gn = state.gnosis
        if not gn:
            return {"status": "critical", "error": "gnosis 未初始化"}
        providers: list[dict] = []
        degraded = False
        for name, ph in gn._providers.items():
            providers.append({
                "name": name,
                "healthy": ph.healthy,
                "failure_count": ph.failure_count,
                "model": getattr(ph.provider, "model_name", ""),
            })
            if not ph.healthy:
                degraded = True
        status = "degraded" if degraded else "ok"
        return {
            "status": status,
            "details": {"providers": providers, "total": len(providers)},
        }

    @_timed_probe("march")
    async def _probe_march(self) -> dict:
        from paimon.state import state
        m = state.march
        if not m:
            return {"status": "critical", "error": "march 未初始化"}
        if not getattr(m, "_running", False):
            return {
                "status": "critical",
                "error": "轮询循环已停止",
                "details": {"running": False},
            }
        sweep_age = time.time() - m._last_lifecycle_sweep
        # Deep 是否在跑（用 busy 标志，与 is_deep_running() 一致）
        deep_running = self._deep_busy
        return {
            "details": {
                "running": True,
                "running_scheduled_tasks": len(m._running_tasks),
                "lifecycle_sweep_age_seconds": round(sweep_age, 1),
                "lifecycle_sweep_running": m._lifecycle_sweep_running,
                "event_rate_limit_keys": len(m._event_rate_limit),
                "deep_selfcheck_running": deep_running,
            }
        }

    @_timed_probe("session_mgr")
    async def _probe_session_mgr(self) -> dict:
        from paimon.state import state
        sm = state.session_mgr
        if not sm:
            return {"status": "critical", "error": "session_mgr 未初始化"}
        try:
            from paimon.channels.webui.channel import PUSH_SESSION_ID
        except Exception:
            PUSH_SESSION_ID = "push"
        has_push = PUSH_SESSION_ID in sm.sessions
        return {
            "active_sessions": len(sm.sessions),
            "bindings": len(sm.bindings),
            "push_session_present": has_push,
        }

    @_timed_probe("skill_registry")
    async def _probe_skill_registry(self) -> dict:
        from paimon.state import state
        sr = state.skill_registry
        if not sr:
            return {"status": "degraded", "error": "skill_registry 未初始化"}
        skills = list(sr.skills.values())
        return {
            "total": len(skills),
            "names": [getattr(s, "name", "?") for s in skills][:50],
        }

    @_timed_probe("authz_cache")
    async def _probe_authz_cache(self) -> dict:
        from paimon.state import state
        ac = state.authz_cache
        if not ac:
            return {"status": "degraded", "error": "authz_cache 未初始化"}
        return {
            "permanent_entries": len(ac._map),
            "session_scope_entries": len(ac._session_scope),
        }

    @_timed_probe("channels")
    async def _probe_channels(self) -> dict:
        from paimon.state import state
        chs: list[dict] = []
        for name, ch in state.channels.items():
            chs.append({
                "name": name,
                "supports_push": getattr(ch, "supports_push", True),
            })
        if not chs:
            return {"status": "degraded", "error": "无任何频道注册",
                    "details": {"channels": []}}
        return {"channels": chs, "total": len(chs)}

    @_timed_probe("paimon_home")
    async def _probe_paimon_home(self) -> dict:
        """轻量版：O(1) 读主 DB 文件大小 + 顶层 entry 数。

        早期版本用 `rglob("*")` 全量扫，paimon_home 大了以后会 100ms~数秒，
        单个探针就能把"秒级"预算吃光。Quick 的承诺是秒级，这里不做细粒度统计——
        要看磁盘用量请用 `du`。
        """
        home = self._cfg.paimon_home
        if not home.exists():
            return {"status": "critical", "error": f"paimon_home 不存在: {home}"}

        db_path = home / "irminsul.db"
        db_bytes = db_path.stat().st_size if db_path.exists() else 0
        db_wal = home / "irminsul.db-wal"
        wal_bytes = db_wal.stat().st_size if db_wal.exists() else 0

        try:
            top_entries = sum(1 for _ in home.iterdir())
        except OSError:
            top_entries = -1

        return {
            "path": str(home),
            "db_bytes": db_bytes,
            "wal_bytes": wal_bytes,
            "top_entries": top_entries,
        }

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
            task = asyncio.create_task(
                self._run_deep_inner(run_id, use_args, triggered_by=triggered_by),
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

    async def _run_deep_inner(
        self, run_id: str, args: str, *, triggered_by: str,
    ) -> None:
        """Deep 实际执行：入 running 记录 → 跑 check → 归档快照 → 解析 → 更新 → 推送。

        **关键约束**：完成判定必须基于 blob 目录里真的有 `candidates.jsonl`。
        LLM 可能没按指令生成 .check/（幻觉 / 提前结束 / 路径错位）——
        若产物缺失，标 failed 而不是 completed，避免面板显示"0 findings 全绿"误导用户。

        完成后**必须**把 _deep_busy 置回 False + 从 state.session_tasks 清理，
        走 finally 保障即便 cancel / 异常路径也能释放。
        """
        from paimon.foundation.irminsul import SelfcheckRun
        from paimon.shades._check_parser import (
            count_severity, parse_candidates_file,
        )
        from paimon.state import state

        t0 = time.time()
        task_key = f"selfcheck_deep_{run_id}"

        try:
            run = SelfcheckRun(
                id=run_id, kind="deep", triggered_at=t0,
                triggered_by=triggered_by, status="running",
                check_args=args,
            )
            await self._irminsul.selfcheck_create(run, actor="三月·自检")
            logger.info(
                "[三月·自检·Deep] 启动 run={} args='{}' by={}",
                run_id, args, triggered_by,
            )

            project_root = Path(__file__).resolve().parent.parent.parent
            root_check = project_root / _CHECK_DIR_NAME
            state_path = root_check / "state.json"

            # 清掉可能的旧 .check/ 避免混入别轮产物
            if root_check.exists():
                shutil.rmtree(root_check, ignore_errors=True)

            # 启动进度 watcher（后台轮询 state.json 写 DB）
            stop_watcher = asyncio.Event()
            watcher_task = asyncio.create_task(
                self._progress_watcher(run_id, state_path, stop_watcher),
                name=f"selfcheck_watcher_{run_id}",
            )

            try:
                # 调 check skill（超时保护）
                timeout = max(60, int(self._cfg.selfcheck_deep_timeout_seconds))
                await asyncio.wait_for(
                    self._invoke_check_skill(args, project_root),
                    timeout=timeout,
                )

                # 快照 .check/ → blob
                blob = self._irminsul.selfcheck_ensure_blob_dir(run_id)
                snapshotted: list[str] = []
                for fname in _CHECK_FILES:
                    src = root_check / fname
                    if src.exists():
                        try:
                            shutil.copy2(src, blob / fname)
                            snapshotted.append(fname)
                        except OSError as e:
                            logger.warning(
                                "[三月·自检·Deep] 快照 {} 失败: {}", fname, e,
                            )

                # 清理 <root>/.check/（产物已快照，不留原地）
                shutil.rmtree(root_check, ignore_errors=True)

                # **产物存在性校验**：candidates.jsonl 必须存在才算成功
                # 若 LLM 未按指令执行，标 failed 避免 UI 误导
                cand_path = blob / "candidates.jsonl"
                if not cand_path.exists():
                    await self._mark_deep_failed(
                        run_id, t0,
                        "check skill 未生成 candidates.jsonl —— "
                        f"可能 LLM 偷懒 / 执行路径不对 / 提前终止。"
                        f"已快照 {len(snapshotted)} 个文件: {snapshotted}",
                    )
                    return

                findings = parse_candidates_file(cand_path)
                sev = count_severity(findings)
                total = len(findings)

                duration = time.time() - t0
                await self._irminsul.selfcheck_update(
                    run_id, actor="三月·自检",
                    status="completed",
                    duration_seconds=duration,
                    p0_count=sev["P0"], p1_count=sev["P1"],
                    p2_count=sev["P2"], p3_count=sev["P3"],
                    findings_total=total,
                )
                await self._irminsul.audit_append(
                    event_type="selfcheck_deep_completed",
                    payload={
                        "run_id": run_id,
                        "args": args,
                        "duration_seconds": round(duration, 2),
                        "severity_counts": sev,
                        "findings_total": total,
                        "snapshotted": snapshotted,
                    },
                    actor="三月·自检",
                )
                logger.info(
                    "[三月·自检·Deep] 完成 run={} P0={} P1={} P2={} P3={} "
                    "耗时={:.1f}s",
                    run_id, sev["P0"], sev["P1"], sev["P2"], sev["P3"], duration,
                )

                # 推送通知（如果 march 在）
                await self._notify_deep_result(run_id, sev, total, duration)

                # GC
                try:
                    await self._irminsul.selfcheck_gc(
                        kind="deep",
                        keep_n=max(1, int(self._cfg.selfcheck_deep_retention)),
                        actor="三月·自检",
                    )
                except Exception as e:
                    logger.warning("[三月·自检·Deep] GC 失败: {}", e)

            except asyncio.TimeoutError:
                await self._mark_deep_failed(
                    run_id, t0,
                    f"超时 ({self._cfg.selfcheck_deep_timeout_seconds}s)",
                )
            except asyncio.CancelledError:
                await self._mark_deep_failed(run_id, t0, "被取消")
                raise
            except Exception as e:
                logger.exception("[三月·自检·Deep] 异常 run={}: {}", run_id, e)
                await self._mark_deep_failed(run_id, t0, str(e))
            finally:
                # 停 watcher（成功/失败/取消都要停；让它自己退出循环，不强杀）
                stop_watcher.set()
                try:
                    await asyncio.wait_for(watcher_task, timeout=3.0)
                except (asyncio.TimeoutError, asyncio.CancelledError):
                    watcher_task.cancel()

        finally:
            # 始终释放 busy + 清理 task 引用，即便 cancel / 异常路径
            self._deep_busy = False
            state.session_tasks.pop(task_key, None)

    async def _progress_watcher(
        self, run_id: str, state_path: Path, stop: asyncio.Event,
    ) -> None:
        """后台轮询 `.check/state.json`，抽进度字段写 DB。

        - 间隔 5s；stop event 触发立刻退出
        - 所有 IO 异常都吞（文件可能不存在、写到一半、JSON 不完整）
        - 同一进度快照不重复写 DB（polled_at 之外字段相同则跳过）
        """
        last_snapshot: dict[str, Any] = {}
        while not stop.is_set():
            try:
                if state_path.exists():
                    raw = state_path.read_text(encoding="utf-8")
                    data = json.loads(raw)
                    progress = _extract_progress(data)
                    # 空 progress（非 dict 入参 / 全字段缺省）→ 不触发 update
                    if progress:
                        # 对比时剔除 polled_at（每次都变），看实质是否变化
                        cur_sig = {k: v for k, v in progress.items() if k != "polled_at"}
                        last_sig = {k: v for k, v in last_snapshot.items() if k != "polled_at"}
                        if cur_sig != last_sig:
                            await self._irminsul.selfcheck_update(
                                run_id, actor="三月·自检·进度",
                                progress=progress,
                            )
                            last_snapshot = progress
            except (OSError, json.JSONDecodeError):
                # 文件不存在 / 写到一半 / 格式损坏：本轮略过，下轮再试
                pass
            except Exception as e:
                # 非预期异常（DB 连接断等）：记一下继续轮询，不拖垮主流程
                logger.debug("[三月·自检·进度] watcher 异常（吞）: {}", e)

            # 睡眠 + 可响应 stop：用 wait_for 让 5s 轮询兼 stop 信号
            try:
                await asyncio.wait_for(stop.wait(), timeout=_PROGRESS_POLL_INTERVAL)
            except asyncio.TimeoutError:
                continue  # 正常超时 → 进下一轮
        logger.debug("[三月·自检·进度] watcher 退出 run={}", run_id)

    async def _invoke_check_skill(self, args: str, project_root: Path) -> None:
        """复用 Archon 基类的 _invoke_skill_workflow 跑 check skill。

        借一个临时 Archon 外壳（不登记 state.channels，仅作 workflow 驱动）。
        """
        from paimon.archons.base import Archon

        class _SelfCheckArchon(Archon):
            name = "派蒙·自检"
            description = "三月·Deep selfcheck（调 check skill）"
            # file_ops 文件读写、glob 跨平台文件查找、exec 兜底复杂命令
            allowed_tools = {"file_ops", "glob", "exec"}

            async def execute(self, *a, **k) -> str:
                return ""

        archon = _SelfCheckArchon()
        platform_hint = _platform_exec_hint()
        framing = (
            f"【三月·Deep 自检 · paimon 适配层】\n"
            f"目标路径: 项目根 {project_root}\n"
            f"产物位置: {project_root}/.check/（必须写齐 "
            f"candidates.jsonl + report.md + state.json 三件套）\n"
            "\n"
            "## ⚠️ 强制启动顺序（违反会失败）\n"
            "你可用的 tool 名字**必须**严格对照下面列表（大小写敏感，注意"
            "`glob` 是 paimon 的原生工具，不是 Python 的 import glob 模块）：\n"
            "\n"
            f"**第一步**：跑 `glob(pattern=\"paimon/**/*.py\", path=\"{project_root}\")`\n"
            "  拿到 paimon 目录下所有 Python 文件的相对路径列表（每行一个）。\n"
            "  这是 check skill 「第二步初始化 → 扫描目标」的正确实现。\n"
            "\n"
            "**禁止的替代写法**（以下任何一种都会导致失败，请严格避免）：\n"
            "  ❌ `exec(\"find ... -name *.py\")` —— Windows 下 find 语义不同会返错\n"
            "  ❌ `exec(\"ls ... / dir ...\")` —— shell 解析差异大\n"
            "  ❌ `exec(\"python -c \\\"import os.walk / glob / fnmatch...\\\"\")` \n"
            "       —— 多行字符串在 PowerShell 转义常坏，已观测到返 5 字符空输出\n"
            "  ❌ 自己拼 `file_ops(list)` 递归各个子目录 —— 慢、易遗漏\n"
            "  ✅ 直接 `glob(pattern=\"paimon/**/*.py\")` —— 一次调用拿全列表\n"
            "\n"
            "## 工具映射（Claude Code 原生 → paimon 工具）\n"
            "check SKILL.md 里写的是 Claude Code 的原生工具名，你在 paimon 里只能用：\n"
            "  - Read          → file_ops(action=\"read\", path=...)\n"
            "  - Write         → file_ops(action=\"write\", path=..., content=...)\n"
            "  - Edit          → file_ops(action=\"write\", ...) 整文件覆写（无 edit 模式）\n"
            "  - Glob          → **glob(pattern=\"**/*.py\", path=...)** ← 原生工具\n"
            "                    跨平台；一次拿完整匹配列表；支持 `**`、`*`、`?`、`[...]`\n"
            "                    例: glob(pattern=\"paimon/**/*.py\") 拿 paimon 子树所有 py\n"
            "  - Grep          → exec(command=...) 按当前平台见下方「执行环境」\n"
            "  - Bash(*)       → exec(command=...) 按当前平台见下方「执行环境」\n"
            "  - AskUserQuestion → 不可用（非交互模式本来就不需要）\n"
            "\n"
            f"## 执行环境（重要 — 决定你能用哪些命令）\n"
            f"{platform_hint}\n"
            "\n"
            "## 执行约束\n"
            "- 参数模式 = 零交互，不要等用户答复，直接执行\n"
            "- ${CLAUDE_SKILL_DIR} 已被替换成 skill 绝对路径，Read references/* 直接读即可\n"
            "- 若某轮扫描出错，记录到 state.json errors 字段后继续，不中止\n"
            "- 所有 finding 都要完整写入 candidates.jsonl（每行 JSON）\n"
            "\n"
            "## 优先级原则（LLM 执行时必记）\n"
            "1. **按模式找文件 → glob(pattern=...)**（最常用，递归、跨平台）\n"
            "2. **列单层目录 → file_ops(action=\"list\", path=...)**\n"
            "3. **读文件 → file_ops(action=\"read\", path=...)**（不要 exec cat）\n"
            "4. **写文件 → file_ops(action=\"write\", ...)**（不要 exec echo/heredoc）\n"
            "5. **exec 只用于**: 运行单个 python 脚本、跑测试命令等 file_ops/glob 办不到的活\n"
            "\n"
            "这是 paimon 内部体检，不是用户交互；最终输出只要简短 severity 统计即可，"
            "真正的产物由 paimon 从 .check/ 目录读取归档。"
        )
        user_msg = (
            f"请按参数模式调用 check skill：\n\n"
            f"```\ncheck {args}\n```\n\n"
            "严格遵循 SKILL.md 第一步「参数模式」→ 第二步初始化 → 第三步执行 → "
            "第四步生成报告的完整流程。\n"
            "\n"
            "### 立即执行的第一个工具调用\n"
            "请**立刻**调用 paimon 的 `glob` 工具拿项目 Python 文件列表：\n\n"
            "```json\n"
            "tool_name: glob\n"
            "arguments: {\n"
            f'  "pattern": "paimon/**/*.py",\n'
            f'  "path": "{project_root}"\n'
            "}\n"
            "```\n"
            "然后按返回的文件列表分组扫描。**不要**用 exec/python/find 等替代 —— "
            "glob 是为此专门提供的工具。\n"
            "\n"
            "**关键产物**：candidates.jsonl（finding 原始数据，每行 JSON）+ "
            "report.md（汇总报告）+ state.json（执行状态）——必须都写到 "
            f"{project_root}/.check/。\n"
            "\n"
            "执行完毕后只要用一两行汇总 severity 计数即可（P0=? P1=? P2=? P3=?），"
            "paimon 会自己读 .check/ 里的产物做持久化。"
        )
        await archon._invoke_skill_workflow(
            skill_name="check",
            user_message=user_msg,
            model=self._model,
            session_name=f"selfcheck-deep-{int(time.time())}",
            component="三月·自检",
            purpose="Deep·code-health",
            allowed_tools={"file_ops", "glob", "exec"},
            framing=framing,
        )

    async def _notify_deep_result(
        self, run_id: str, sev: dict[str, int], total: int, duration: float,
    ) -> None:
        """Deep 完成后推📨 推送（失败静默）。"""
        if not self._march:
            return
        try:
            from paimon.state import state
            webui = state.channels.get("webui")
            if not webui:
                return
            from paimon.channels.webui.channel import PUSH_CHAT_ID
            head = "🩺" if sev["P0"] == 0 else "🚨"
            msg = (
                f"{head} Deep 自检完成 run={run_id[:8]}\n"
                f"  耗时 {duration:.0f}s · 共 {total} 条\n"
                f"  P0={sev['P0']} P1={sev['P1']} P2={sev['P2']} P3={sev['P3']}\n"
                f"  详情 → /selfcheck"
            )
            await self._march.ring_event(
                channel_name="webui", chat_id=PUSH_CHAT_ID,
                source="三月·自检", message=msg,
            )
        except Exception as e:
            logger.debug("[三月·自检·Deep] 推送失败（静默）: {}", e)

    async def _mark_deep_failed(
        self, run_id: str, t0: float, reason: str,
    ) -> None:
        duration = time.time() - t0
        try:
            await self._irminsul.selfcheck_update(
                run_id, actor="三月·自检",
                status="failed", error=reason[:500],
                duration_seconds=duration,
            )
            await self._irminsul.audit_append(
                event_type="selfcheck_deep_failed",
                payload={
                    "run_id": run_id,
                    "reason": reason[:500],
                    "duration_seconds": round(duration, 2),
                },
                actor="三月·自检",
            )
        except Exception as e:
            logger.error("[三月·自检·Deep] 标失败记录本身失败: {}", e)

    # ==================== 查询（供命令 / 面板 ====================

    async def list_runs(
        self, *, kind: str | None = None, limit: int = 50, offset: int = 0,
    ) -> list["SelfcheckRun"]:
        return await self._irminsul.selfcheck_list(
            kind=kind, limit=limit, offset=offset,
        )

    async def count_runs(self, *, kind: str | None = None) -> int:
        return await self._irminsul.selfcheck_count(kind=kind)

    async def latest_run(self, kind: str) -> "SelfcheckRun | None":
        return await self._irminsul.selfcheck_latest(kind)

    async def get_run(self, run_id: str) -> "SelfcheckRun | None":
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
        return await self._irminsul.selfcheck_delete(run_id, actor="三月·自检")

    def is_deep_running(self) -> bool:
        return self._deep_busy
