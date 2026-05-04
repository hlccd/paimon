"""Quick 自检 9 组件探针实现：irminsul/leyline/gnosis/march/...; svc 注入避免循环引用。

每个探针通过 _timed_probe 装饰器统一加超时计量 + 异常兜底；
probe_all 并发跑全部探针，整体 < 1s。
"""
from __future__ import annotations

import asyncio
import time
from typing import TYPE_CHECKING

from loguru import logger

from ._models import ComponentProbe, QuickSnapshot

if TYPE_CHECKING:
    from .service import SelfCheckService


def _timed_probe(name: str):
    """装饰器：try/except + 测延时 + 构造 ComponentProbe。"""
    def wrapper(fn):
        async def inner(svc: "SelfCheckService") -> ComponentProbe:
            t = time.time()
            try:
                details = await fn(svc) or {}
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
async def _probe_irminsul(svc: "SelfCheckService") -> dict:
    """探 SQLite 连通性 + 12 域行数 + db 文件大小。"""
    db = svc._irminsul._db
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

    db_path = svc._irminsul._db_path
    db_bytes = db_path.stat().st_size if db_path.exists() else 0

    return {"tables": counts, "db_bytes": db_bytes}


@_timed_probe("leyline")
async def _probe_leyline(svc: "SelfCheckService") -> dict:
    """探地脉事件总线：循环是否在跑 + 各 topic 订阅者数。"""
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
async def _probe_gnosis(svc: "SelfCheckService") -> dict:
    """探 LLM provider 池：每个 provider 健康度 + 连续失败次数。"""
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
async def _probe_march(svc: "SelfCheckService") -> dict:
    """探三月调度：轮询是否在跑 + 当前任务数 + 生命周期清扫年龄。"""
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
    deep_running = svc._deep_busy
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
async def _probe_session_mgr(svc: "SelfCheckService") -> dict:
    """探会话管理器：活跃会话数 + 绑定数。"""
    from paimon.state import state
    sm = state.session_mgr
    if not sm:
        return {"status": "critical", "error": "session_mgr 未初始化"}
    return {
        "active_sessions": len(sm.sessions),
        "bindings": len(sm.bindings),
    }


@_timed_probe("skill_registry")
async def _probe_skill_registry(svc: "SelfCheckService") -> dict:
    """探 Skill 注册表：总数 + 名字列表（前 50）。"""
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
async def _probe_authz_cache(svc: "SelfCheckService") -> dict:
    """探授权缓存：永久授权数 + 会话级条目数。"""
    from paimon.state import state
    ac = state.authz_cache
    if not ac:
        return {"status": "degraded", "error": "authz_cache 未初始化"}
    return {
        "permanent_entries": len(ac._map),
        "session_scope_entries": len(ac._session_scope),
    }


@_timed_probe("channels")
async def _probe_channels(svc: "SelfCheckService") -> dict:
    """探所有渠道注册：列名 + supports_push 能力。"""
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
async def _probe_paimon_home(svc: "SelfCheckService") -> dict:
    """轻量版：O(1) 读主 DB 文件大小 + 顶层 entry 数。

    早期版本用 `rglob("*")` 全量扫，paimon_home 大了以后会 100ms~数秒，
    单个探针就能把"秒级"预算吃光。Quick 的承诺是秒级，这里不做细粒度统计——
    要看磁盘用量请用 `du`。
    """
    home = svc._cfg.paimon_home
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


async def probe_all(svc: "SelfCheckService") -> QuickSnapshot:
    """9 组件探针并发 + 收集。整体 < 1s。"""
    t0 = time.time()
    probes = await asyncio.gather(
        _probe_irminsul(svc),
        _probe_leyline(svc),
        _probe_gnosis(svc),
        _probe_march(svc),
        _probe_session_mgr(svc),
        _probe_skill_registry(svc),
        _probe_authz_cache(svc),
        _probe_channels(svc),
        _probe_paimon_home(svc),
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
