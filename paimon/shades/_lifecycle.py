"""时执 · 生命周期闭环（docs/shades/istaroth.md §核心能力）

由三月定时触发（docs/foundation/march.md §核心能力 "定时调度 · 时执过期数据清理"）。

三条推进链（全部由时执作为 actor 落盘；调用方给内存同步用的 id 列表）：

  会话：  hot ──[N 小时无 updated & 无 channel 绑定]──► archived
         archived ──[M 天]──► 物理删除

  任务运行时超时（docs "复杂任务默认 1 小时"）：
         running ──[P 小时无 updated]──► failed + cold

  任务归档推进：
         cold ──[T1 天]──► archived
         archived ──[T2 天]──► 物理删除（级联 subtasks/flow/progress）

所有阈值都从 config 读取，便于 .env 覆盖。sweep 失败只记 warning + audit，
不抛给调用方——三月下轮（默认 6h 后）会重试。
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from loguru import logger

if TYPE_CHECKING:
    from paimon.foundation.irminsul import Irminsul
    from paimon.session import SessionManager


@dataclass
class SweepReport:
    """一次清扫的汇总，写 audit + 日志用。"""
    session_archived: list[str] = field(default_factory=list)
    session_purged: list[str] = field(default_factory=list)
    task_stuck: list[str] = field(default_factory=list)
    task_promoted: list[str] = field(default_factory=list)
    task_purged: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    duration_ms: float = 0.0

    def to_audit_payload(self) -> dict:
        return {
            "session_archived_count": len(self.session_archived),
            "session_purged_count": len(self.session_purged),
            "task_stuck_count": len(self.task_stuck),
            "task_promoted_count": len(self.task_promoted),
            "task_purged_count": len(self.task_purged),
            "errors": self.errors[:20],
            "duration_ms": round(self.duration_ms, 1),
        }

    @property
    def total_changes(self) -> int:
        return (
            len(self.session_archived) + len(self.session_purged)
            + len(self.task_stuck) + len(self.task_promoted) + len(self.task_purged)
        )


async def sweep_sessions(
    irminsul: "Irminsul",
    *,
    now: float,
    inactive_hours: float,
    archived_ttl_days: float,
    session_mgr: "SessionManager | None" = None,
) -> tuple[list[str], list[str], list[str]]:
    """扫会话：归档不活跃的 + 删除超过 TTL 的。

    返回 (archived_ids, purged_ids, errors)。失败计入 errors 不抛。
    """
    archived: list[str] = []
    purged: list[str] = []
    errors: list[str] = []

    inactive_seconds = inactive_hours * 3600.0
    archived_ttl_seconds = archived_ttl_days * 86400.0

    # 1) 不活跃 → archived（护栏：generating / 有 channel 绑定的都跳过，SQL 内实现）
    try:
        archived = await irminsul.session_archive_if_idle(
            now=now, inactive_seconds=inactive_seconds, actor="时执",
        )
    except Exception as e:
        errors.append(f"session_archive_if_idle: {e}")
        logger.warning("[时执·生命周期] 会话归档失败: {}", e)

    # 2) archived 过期 → 物理删除
    try:
        purged = await irminsul.session_purge_expired(
            now=now, archived_ttl_seconds=archived_ttl_seconds, actor="时执",
        )
    except Exception as e:
        errors.append(f"session_purge_expired: {e}")
        logger.warning("[时执·生命周期] 会话过期清理失败: {}", e)

    # 3) SessionManager 内存同步
    # 归档 + 删除 都要从内存移除：
    #   - SessionManager.load 启动时只加载 archived_at IS NULL 的活跃会话，
    #     为保持重启前后语义一致，运行期归档也应立即从内存移除
    #   - 归档会话仍可通过 session_list(archived=True) 查 DB 看到
    if session_mgr is not None:
        ids_to_invalidate = list(archived) + list(purged)
        if ids_to_invalidate:
            try:
                session_mgr.invalidate_removed(ids_to_invalidate)
            except Exception as e:
                errors.append(f"session_mgr.invalidate_removed: {e}")
                logger.warning("[时执·生命周期] 内存同步失败: {}", e)

    return archived, purged, errors


async def sweep_tasks(
    irminsul: "Irminsul",
    *,
    now: float,
    running_timeout_hours: float,
    cold_ttl_days: float,
    archived_ttl_days: float,
) -> tuple[list[str], list[str], list[str], list[str]]:
    """扫任务：卡死超时 + 推进 cold→archived + 清理过期 archived。

    返回 (stuck_ids, promoted_ids, purged_ids, errors)。
    """
    stuck: list[str] = []
    promoted: list[str] = []
    purged: list[str] = []
    errors: list[str] = []

    running_timeout_seconds = running_timeout_hours * 3600.0
    cold_ttl_seconds = cold_ttl_days * 86400.0
    archived_ttl_seconds = archived_ttl_days * 86400.0

    # 1) 运行中卡死 → failed + cold
    try:
        stuck = await irminsul.task_stuck_running_timeout(
            now=now, timeout_seconds=running_timeout_seconds, actor="时执",
        )
        for tid in stuck:
            try:
                await irminsul.audit_append(
                    event_type="task_stuck_timeout",
                    payload={
                        "task_id": tid,
                        "timeout_hours": running_timeout_hours,
                    },
                    task_id=tid, actor="时执",
                )
            except Exception as e:
                errors.append(f"audit(task_stuck {tid}): {e}")
    except Exception as e:
        errors.append(f"task_stuck_running_timeout: {e}")
        logger.warning("[时执·生命周期] 卡死任务清理失败: {}", e)

    # 2) cold → archived
    try:
        promoted = await irminsul.task_promote_lifecycle(
            now=now, cold_ttl_seconds=cold_ttl_seconds, actor="时执",
        )
    except Exception as e:
        errors.append(f"task_promote_lifecycle: {e}")
        logger.warning("[时执·生命周期] cold→archived 推进失败: {}", e)

    # 3) archived → 删除（级联子任务/流转/进度）
    try:
        purged = await irminsul.task_purge_expired(
            now=now, archived_ttl_seconds=archived_ttl_seconds, actor="时执",
        )
    except Exception as e:
        errors.append(f"task_purge_expired: {e}")
        logger.warning("[时执·生命周期] 任务过期清理失败: {}", e)

    return stuck, promoted, purged, errors


async def run_lifecycle_sweep(
    irminsul: "Irminsul",
    cfg,
    *,
    session_mgr: "SessionManager | None" = None,
    now: float | None = None,
) -> SweepReport:
    """三月调用的清扫入口。只读 config，不依赖任何其他服务。"""
    if not getattr(cfg, "lifecycle_sweep_enabled", True):
        logger.debug("[时执·生命周期] 已禁用（lifecycle_sweep_enabled=false），跳过")
        return SweepReport()

    start = time.monotonic()
    if now is None:
        now = time.time()

    report = SweepReport()

    session_archived, session_purged, session_errors = await sweep_sessions(
        irminsul,
        now=now,
        inactive_hours=cfg.session_inactive_hours,
        archived_ttl_days=cfg.session_archived_ttl_days,
        session_mgr=session_mgr,
    )
    report.session_archived = session_archived
    report.session_purged = session_purged
    report.errors.extend(session_errors)

    stuck, promoted, purged, task_errors = await sweep_tasks(
        irminsul,
        now=now,
        running_timeout_hours=cfg.task_running_timeout_hours,
        cold_ttl_days=cfg.task_cold_ttl_days,
        archived_ttl_days=cfg.task_archived_ttl_days,
    )
    report.task_stuck = stuck
    report.task_promoted = promoted
    report.task_purged = purged
    report.errors.extend(task_errors)

    report.duration_ms = (time.monotonic() - start) * 1000.0

    # 只在有变更或出错时才写 audit + INFO 日志，避免轻扫刷屏
    if report.total_changes > 0 or report.errors:
        try:
            await irminsul.audit_append(
                event_type="lifecycle_sweep_report",
                payload=report.to_audit_payload(),
                actor="时执·生命周期",
            )
        except Exception as e:
            logger.warning("[时执·生命周期] audit 写入失败: {}", e)
        logger.info(
            "[时执·生命周期] 清扫完成（耗时 {:.1f}ms）"
            " | 会话：归档 {} / 删除 {}"
            " | 任务：卡死 {} / 推进 {} / 删除 {}"
            " | 错误 {}",
            report.duration_ms,
            len(report.session_archived), len(report.session_purged),
            len(report.task_stuck), len(report.task_promoted), len(report.task_purged),
            len(report.errors),
        )
    else:
        logger.debug(
            "[时执·生命周期] 清扫完成（无变更，{:.1f}ms）",
            report.duration_ms,
        )

    return report
